"""EHPL tables show every outlet once: none dropped, none counted twice,
and TOTAL EHPL equals the location's total in the data."""

import datetime as dt
from unittest.mock import patch

import pandas as pd
import pytest

from modules import business_dashboard as bd
from modules import outlet_groups as og
from modules.ehpl_layout import BHOGAPURAM_SECTIONS, HYD_SECTIONS, _build_table_rows

D = dt.date(2026, 8, 1)


def _df(location, rows):
    return pd.DataFrame([{"date": D, "location": location, "segment": "EHPL",
                          "outlet": o, "pax": p, "revenue": r} for o, p, r in rows])


def _report(location, groups, subtotals, order, cur, aop=None):
    with patch.object(bd.database, "join_revenue_with_traffic_by_outlet",
                      return_value=pd.DataFrame()):
        return bd._build_location_report(location, groups, subtotals, order, cur, None, aop)


def _outlets(rows):
    return {r["Performance"].strip(): r for r in rows if not r["_is_subtotal"]}


def _grand(rows):
    return next(r for r in rows if r["_is_grand"])


def test_hyderabad_outlets_sharing_a_name_are_added_not_dropped():
    cur = _df("Hyderabad", [("Atithya", 10, 1000), ("GAT", 5, 500), ("Airport Lodge", 2, 200),
                            ("Domestic Lounge T3", 50, 5000), ("Reserved Lounge", 3, 300),
                            ("Domestic Lounge - Prive", 4, 400)])
    rows = _report("Hyderabad", og.HYD_GROUPS, og.HYD_SUBTOTALS, og.HYD_ROW_ORDER, cur)
    out = _outlets(rows)
    assert out["Atithya"]["cur_rev"] == 1700                 # GAT + Airport Lodge included
    assert out["Reserved Lounge"]["cur_rev"] == 300           # own row, not merged elsewhere
    assert out["Encalm Prive"]["cur_rev"] == 400
    assert _grand(rows)["cur_rev"] == cur["revenue"].sum()


def test_alias_names_do_not_double_count():
    cur = _df("Delhi", [("Round D Clock (RDC)", 6, 4800), ("Reserved Lounge", 13, 50),
                        ("Nap Rooms LA01", 1, 3700)])
    rows = _report("Delhi", og.DELHI_GROUPS, og.DELHI_SUBTOTALS, og.DELHI_ROW_ORDER, cur)
    assert sum(r["cur_rev"] for r in _outlets(rows).values()) == cur["revenue"].sum()
    assert _grand(rows)["cur_rev"] == cur["revenue"].sum()
    assert _outlets(rows)["Nap Rooms LA01"]["_section"] == "T3 Nap LA01"


def test_unlisted_outlet_and_aop_only_line_still_show():
    cur = _df("Bhogapuram", [("Domestic Lounge T3", 10, 1000), ("Brand New Lounge", 1, 99)])
    aop = pd.DataFrame({"location": ["Bhogapuram"] * 2, "outlet": ["Domestic Lounge T3", "MLCP"],
                        "aop": [2000.0, 500.0]})
    rows = _report("Bhogapuram", og.BHOGAPURAM_GROUPS, og.BHOGAPURAM_SUBTOTALS,
                   og.BHOGAPURAM_ROW_ORDER, cur, aop)
    out = _outlets(rows)
    assert set(out) == {"Domestic Lounge", "Brand New Lounge", "MLCP"}   # no Delhi lounge names
    assert out["Domestic Lounge"]["aop"] == 2000 and out["MLCP"]["aop"] == 500
    assert _grand(rows)["cur_rev"] == 1099 and _grand(rows)["aop"] == 2500

    table = _build_table_rows(rows, BHOGAPURAM_SECTIONS)
    shown = {r["Performance"].strip() for r in table if r["_row_type"] == "outlet"}
    assert shown == {"Domestic Lounge", "Brand New Lounge", "MLCP"}
    sections = [r for r in table if r["_row_type"] == "total"]
    assert sum(r["cur_rev"] for r in sections) == pytest.approx(1099)


def test_hyderabad_sections_add_up_to_total():
    cur = _df("Hyderabad", [("Atithya", 1, 10), ("Porter", 1, 20), ("Mystery Outlet", 1, 30),
                            ("International Lounge", 1, 40)])
    rows = _report("Hyderabad", og.HYD_GROUPS, og.HYD_SUBTOTALS, og.HYD_ROW_ORDER, cur)
    table = _build_table_rows(rows, HYD_SECTIONS)
    assert table[0]["cur_rev"] == 100
    assert sum(r["cur_rev"] for r in table if r["_row_type"] == "total") == 100
