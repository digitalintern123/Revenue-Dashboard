"""Same-key revenue lines (month-end adjustments, canonical-name collisions) are summed, not dropped."""

import datetime as dt

import pandas as pd

from modules.database import combine_duplicate_revenue_rows
from modules import data_processor


def _df(rows):
    return pd.DataFrame(rows, columns=["date", "segment", "outlet", "location", "pax", "revenue", "aop", "traffic"])


def test_month_end_second_line_is_added():
    d = dt.date(2026, 9, 30)
    df = _df([
        (d, "Lounges", "INL 5&6", "Delhi", 2867, 5694320.0, 5452582.0, 1000),
        (d, "Lounges", "INL 5&6", "Delhi", None, 23435677.64, None, 1000),
        (d, "Atithya", "Porter", "Delhi", 10, 500.0, None, None),
    ])
    out = combine_duplicate_revenue_rows(df, ["date", "segment", "outlet", "location"])
    assert len(out) == 2
    inl = out[out["outlet"] == "INL 5&6"].iloc[0]
    assert inl["revenue"] == 5694320.0 + 23435677.64
    assert inl["pax"] == 2867 and inl["aop"] == 5452582.0
    assert inl["traffic"] == 1000                      # not doubled
    assert out["revenue"].sum() == df["revenue"].sum()


def test_exact_duplicate_rows_are_not_double_counted():
    d = dt.date(2026, 9, 1)
    row = (d, "Lounges", "T2 Domestic", "Delhi", 100, 1000.0, 900.0, None)
    out = combine_duplicate_revenue_rows(_df([row, row]), ["date", "segment", "outlet", "location"])
    assert len(out) == 1 and out["revenue"].iloc[0] == 1000.0


def test_all_blank_aop_stays_blank():
    d = dt.date(2026, 9, 2)
    df = _df([(d, "Lounges", "X", "Goa", 1, 10.0, None, None),
              (d, "Lounges", "X", "Goa", 2, 20.0, None, None)])
    out = combine_duplicate_revenue_rows(df, ["date", "segment", "outlet", "location"])
    assert pd.isna(out["aop"].iloc[0]) and out["pax"].iloc[0] == 3


def test_validate_and_clean_sums_instead_of_keeping_last():
    d = dt.date(2026, 8, 31)
    df = _df([(d, "Atithya", "Buggy Service", "Delhi", 40, 10000.0, 46271.9, None),
              (d, "Atithya", "Buggy Service", "Delhi", 8, 1256000.0, None, None)])
    out = data_processor._validate_and_clean(df)
    assert len(out) == 1
    assert out["revenue"].iloc[0] == 1266000.0 and out["pax"].iloc[0] == 48
