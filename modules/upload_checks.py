"""
upload_checks.py — checks run on a parsed upload BEFORE it is saved.

Shown on the upload "Analyse" panel. They never change the data: the file
is the single source of truth, so every finding is a message for the person
uploading (to check the file, or to tick Replace), not a correction.

Revenue:  reconcile with the file, new outlets, what changes vs stored,
          copied days, PAX with no revenue, revenue per PAX far from usual.
Traffic:  what changes vs stored, copied days, days far from the month's
          usual, month total far from the stored previous month.

The pure functions take DataFrames (unit-testable); the `*_for_upload`
wrappers load the stored data they need through modules/database.py.
"""
from __future__ import annotations

import datetime as dt
import difflib
import io
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from modules import import_report

OK, INFO, WARN = "ok", "info", "warn"
MAX_ROWS_SHOWN = 50


@dataclass
class Check:
    level: str                     # ok / info / warn
    title: str
    detail: str = ""
    table: Optional[pd.DataFrame] = None
    count: int = 0                 # number of items behind the finding


@dataclass
class Analysis:
    """Everything the Analyse panel shows for one file."""
    checks: list[Check] = field(default_factory=list)
    confidence: Optional[float] = None     # overall, 0..1 (None = not scored)

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.level == WARN)


def _money(v: float) -> str:
    from modules.formatting import format_money
    return format_money(v)


def _num(v) -> str:
    from modules.formatting import format_pax
    return format_pax(v)


# ---------------------------------------------------------------------------
# Revenue: reconcile parsed totals with the file
# ---------------------------------------------------------------------------
def _figure_column(columns, name: str) -> Optional[str]:
    for c in columns:
        if str(c).strip().lower() == name:
            return c
    return None


def reconcile_long_sheet(file_bytes: bytes, sheet: str, header_row_idx: int,
                         parsed_revenue: float, parsed_pax: float,
                         skipped_rows: Optional[pd.DataFrame]) -> Check:
    """File total = imported + listed in "rows not imported". Any other
    difference means the parser lost or invented figures."""
    raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=header_row_idx,
                        engine="openpyxl")
    rev_col, pax_col = _figure_column(raw.columns, "revenue"), _figure_column(raw.columns, "pax")
    if rev_col is None:
        return Check(INFO, "Totals not reconciled", "No 'Revenue' column found to add up.")
    file_rev = float(pd.to_numeric(raw[rev_col], errors="coerce").sum())
    file_pax = float(pd.to_numeric(raw[pax_col], errors="coerce").sum()) if pax_col else 0.0
    left_rev = left_pax = 0.0
    if skipped_rows is not None and not skipped_rows.empty:
        out = skipped_rows[skipped_rows["Result"] == import_report.NOT_IMPORTED]
        left_rev = float(pd.to_numeric(out["Revenue"], errors="coerce").sum())
        left_pax = float(pd.to_numeric(out["PAX"], errors="coerce").sum())
    gap_rev = file_rev - parsed_revenue - left_rev
    gap_pax = file_pax - parsed_pax - left_pax
    detail = (f"File: {_money(file_rev)} / {_num(file_pax)} PAX. Imported: "
              f"{_money(parsed_revenue)} / {_num(parsed_pax)} PAX. Listed in "
              f"'rows not imported': {_money(left_rev)} / {_num(left_pax)} PAX.")
    if abs(gap_rev) <= 1 and abs(gap_pax) <= 0.5:
        return Check(OK, "Every figure in the file is accounted for", detail)
    return Check(WARN, "Totals do not reconcile with the file",
                 detail + f" Unexplained: {_money(gap_rev)} / {_num(gap_pax)} PAX — "
                          "do not save until this is understood.")


# ---------------------------------------------------------------------------
# Revenue: new outlets, what changes, anomalies
# ---------------------------------------------------------------------------
def new_outlets(file_keys: pd.DataFrame, stored_outlets: pd.DataFrame) -> Check:
    """Outlets in the file never stored for that location, with the closest
    stored name (a likely spelling variant)."""
    stored = {}
    for r in stored_outlets.itertuples():
        stored.setdefault(str(r.location), set()).add(str(r.outlet))
    if not stored:
        return Check(INFO, "First upload — no stored outlets to compare with")
    rows = []
    grp = file_keys.groupby(["location", "outlet"]).agg(
        lines=("date", "size"), revenue=("revenue", "sum"), pax=("pax", "sum")).reset_index()
    for r in grp.itertuples():
        known = stored.get(r.location, set())
        if r.outlet in known:
            continue
        close = difflib.get_close_matches(r.outlet.lower(), [k.lower() for k in known], n=1, cutoff=0.75)
        match = next((k for k in known if close and k.lower() == close[0]), "")
        rows.append({"Location": r.location, "Outlet in file": r.outlet, "Lines": r.lines,
                     "Revenue": _money(r.revenue or 0), "Possibly the same as": match})
    if not rows:
        return Check(OK, "No new outlets")
    t = pd.DataFrame(rows)
    return Check(WARN if (t["Possibly the same as"] != "").any() else INFO,
                 f"{len(t)} outlet(s) never seen before",
                 "Imported exactly as written; they show under 'Others' until placed. "
                 "A name next to 'Possibly the same as' may be a spelling variant — "
                 "check the file.", t.head(MAX_ROWS_SHOWN), len(t))


def changes_vs_stored(file_keys: pd.DataFrame, stored_keys: pd.DataFrame) -> Check:
    """How the file differs from what is stored for the same keys."""
    k = ["date", "location", "outlet"]
    m = file_keys.merge(stored_keys, on=k, how="left", suffixes=("", "_stored"), indicator=True)
    new = m[m["_merge"] == "left_only"]
    both = m[m["_merge"] == "both"]

    def _diff(a, b):
        return (a.fillna(0) - b.fillna(0)).abs()
    differ = both[(_diff(both["revenue"], both["revenue_stored"]) > 0.5)
                  | (_diff(both["pax"], both["pax_stored"]) > 0.5)]
    same = len(both) - len(differ)
    detail = f"{len(new):,} new line(s), {same:,} already stored with the same figures"
    if differ.empty:
        return Check(OK if len(new) else INFO, "Nothing stored would change", detail + ".",
                     count=0)
    t = differ.assign(**{"Revenue diff": differ["revenue"].fillna(0) - differ["revenue_stored"].fillna(0)})
    by_month = (t.assign(Month=pd.to_datetime(t["date"]).dt.strftime("%Y-%m"))
                 .groupby("Month").agg(Lines=("outlet", "size"), **{"Revenue diff": ("Revenue diff", "sum")})
                 .reset_index())
    by_month["Revenue diff"] = by_month["Revenue diff"].map(_money)
    return Check(WARN, f"{len(differ):,} stored line(s) have different figures in this file",
                 detail + f", {len(differ):,} different (net {_money(t['Revenue diff'].sum())}). "
                 "Stored lines are kept unless you tick **Replace** — tick it if this file is "
                 "the corrected version.", by_month, len(differ))


def copied_days(file_keys: pd.DataFrame, min_outlets: int = 5) -> Check:
    """Two dates of one location with exactly the same PAX and revenue for
    every outlet (at least `min_outlets` with revenue) — a day pasted twice."""
    rows = []
    for loc, g in file_keys[file_keys["revenue"].fillna(0) != 0].groupby("location"):
        sig = (g.sort_values("outlet").groupby("date")
                .apply(lambda d: tuple(zip(d["outlet"], d["pax"].fillna(0).round(2),
                                           d["revenue"].round(2))) if len(d) >= min_outlets else None))
        sig = sig.dropna()
        for _, dates in sig.groupby(sig).groups.items():
            if len(dates) > 1:
                ds = sorted(dates)
                rows.append({"Location": loc, "Dates with identical figures": ", ".join(ds),
                             "Outlets": len(sig[ds[0]])})
    if not rows:
        return Check(OK, "No copied days")
    t = pd.DataFrame(rows)
    return Check(WARN, f"{len(t)} set(s) of dates with identical figures",
                 "Every outlet has exactly the same PAX and revenue on these dates — "
                 "usually a day copied by mistake in the file.", t.head(MAX_ROWS_SHOWN), len(t))


def pax_without_revenue(file_keys: pd.DataFrame, min_days: int = 5) -> Check:
    """Outlets with PAX but no revenue on several days."""
    f = file_keys[(file_keys["pax"].fillna(0) > 0) & (file_keys["revenue"].fillna(0) == 0)]
    if f.empty:
        return Check(OK, "No outlet has PAX without revenue")
    g = (f.groupby(["location", "outlet"])
          .agg(Days=("date", "nunique"), PAX=("pax", "sum"), First=("date", "min"), Last=("date", "max"))
          .reset_index())
    g = g[g["Days"] >= min_days].sort_values("Days", ascending=False)
    if g.empty:
        return Check(OK, "No outlet has PAX without revenue on several days")
    g["PAX"] = g["PAX"].map(_num)
    return Check(WARN, f"{len(g)} outlet(s) with PAX but no revenue on {min_days}+ days",
                 "Revenue is 0 or blank while PAX is not — check whether revenue is missing "
                 "from the file.", g.rename(columns={"location": "Location", "outlet": "Outlet"})
                 .head(MAX_ROWS_SHOWN), len(g))


def revenue_per_pax_outliers(file_keys: pd.DataFrame, history: Optional[pd.DataFrame] = None,
                             factor: float = 3.0, min_pax: float = 10) -> Check:
    """Days where revenue per PAX is more than `factor`x above or below the
    outlet's median (file + stored history)."""
    base = pd.concat([file_keys, history]) if history is not None and not history.empty else file_keys
    base = base[(base["pax"].fillna(0) >= min_pax) & (base["revenue"].fillna(0) > 0)]
    if base.empty:
        return Check(OK, "Revenue per PAX looks usual")
    med = (base.assign(rpp=base["revenue"] / base["pax"])
               .groupby(["location", "outlet"])["rpp"].median().rename("median"))
    f = file_keys[(file_keys["pax"].fillna(0) >= min_pax) & (file_keys["revenue"].fillna(0) > 0)]
    f = f.join(med, on=["location", "outlet"]).assign(rpp=lambda d: d["revenue"] / d["pax"])
    out = f[(f["rpp"] > f["median"] * factor) | (f["rpp"] < f["median"] / factor)]
    if out.empty:
        return Check(OK, "Revenue per PAX looks usual")
    t = out.sort_values("date").assign(
        **{"Revenue / PAX": out["rpp"].map(_money), "Usual": out["median"].map(_money)})
    t = t.rename(columns={"date": "Date", "location": "Location", "outlet": "Outlet"})
    return Check(INFO, f"{len(t):,} line(s) with unusual revenue per PAX",
                 f"Revenue ÷ PAX is more than {factor:g}× above or below the outlet's usual "
                 "value — a typo, a missing PAX figure, or a genuine one-off.",
                 t[["Date", "Location", "Outlet", "Revenue / PAX", "Usual"]].head(MAX_ROWS_SHOWN),
                 len(t))


def analyse_revenue(result, file_bytes: Optional[bytes] = None,
                    stored_keys: Optional[pd.DataFrame] = None,
                    stored_outlets: Optional[pd.DataFrame] = None) -> Analysis:
    """All revenue checks for a ProcessResult parsed with save_to_db=False."""
    from modules import data_processor, database
    a = Analysis(confidence=result.confidence)
    if not result.success or result.df is None or result.df.empty:
        return a
    keys = database.normalise_revenue_keys(result.df)

    if (file_bytes is not None and result.layout == data_processor.LAYOUT_LONG
            and result.source_sheet and result.header_row_idx is not None):
        try:
            c = reconcile_long_sheet(file_bytes, result.source_sheet, result.header_row_idx,
                                     result.total_revenue, result.total_pax, result.skipped_rows)
        except Exception as exc:          # a check must never block the upload
            c = Check(INFO, "Totals not reconciled", f"Could not re-read the sheet: {exc}")
        a.checks.append(c)
        a.confidence = 1.0 if c.level == OK else (0.6 if c.level == WARN else 0.9)
    elif a.confidence is None:
        a.confidence = 0.9            # known layout, not reconcilable

    if stored_outlets is None:
        stored_outlets = database.get_stored_outlets()
    a.checks.append(new_outlets(keys, stored_outlets))
    if stored_keys is None:
        d0, d1 = pd.to_datetime(keys["date"]).min().date(), pd.to_datetime(keys["date"]).max().date()
        stored_keys = database.normalise_revenue_keys(database.load_for_date_range(d0, d1))
    if not stored_keys.empty:
        a.checks.append(changes_vs_stored(keys, stored_keys))
    else:
        a.checks.append(Check(OK, "All lines are new", f"{len(keys):,} line(s), none stored yet."))
    a.checks.append(copied_days(keys))
    a.checks.append(pax_without_revenue(keys))
    a.checks.append(revenue_per_pax_outliers(keys, stored_keys))
    return a


# ---------------------------------------------------------------------------
# Traffic
# ---------------------------------------------------------------------------
def _traffic_keys(df: pd.DataFrame) -> pd.DataFrame:
    t = df[["date", "location", "terminal", "granularity", "traffic"]].copy()
    t["date"] = pd.to_datetime(t["date"]).dt.strftime("%Y-%m-%d")
    t["terminal"] = t["terminal"].fillna("").astype(str)
    t["traffic"] = pd.to_numeric(t["traffic"], errors="coerce")
    return t


def traffic_changes_vs_stored(file_t: pd.DataFrame, stored_t: pd.DataFrame) -> Check:
    k = ["date", "location", "terminal", "granularity"]
    m = file_t.merge(stored_t[k + ["traffic"]], on=k, how="left", suffixes=("", "_stored"),
                     indicator=True)
    new = (m["_merge"] == "left_only").sum()
    both = m[m["_merge"] == "both"]
    differ = both[(both["traffic"].fillna(0) - both["traffic_stored"].fillna(0)).abs() > 0.5]
    detail = f"{new:,} new row(s), {len(both) - len(differ):,} already stored with the same figure"
    if differ.empty:
        return Check(OK if new else INFO, "Nothing stored would change", detail + ".")
    t = (differ.groupby(["location", "terminal"])
               .agg(Rows=("date", "size"), File=("traffic", "sum"), Stored=("traffic_stored", "sum"))
               .reset_index())
    t["File"], t["Stored"] = t["File"].map(_num), t["Stored"].map(_num)
    return Check(WARN, f"{len(differ):,} stored traffic row(s) differ from this file",
                 detail + f", {len(differ):,} different. Keep **Replace** ticked to use this "
                 "file's figures.", t, len(differ))


def traffic_copied_days(file_t: pd.DataFrame, min_terminals: int = 2) -> Check:
    """Two days of one airport with identical traffic in every terminal."""
    daily = file_t[(file_t["granularity"] == "daily") & (file_t["traffic"].fillna(0) > 0)]
    rows = []
    for loc, g in daily.groupby("location"):
        sig = g.sort_values("terminal").groupby("date").apply(
            lambda d: tuple(zip(d["terminal"], d["traffic"])) if len(d) >= min_terminals else None).dropna()
        for _, dates in sig.groupby(sig).groups.items():
            if len(dates) > 1:
                rows.append({"Location": loc, "Dates with identical traffic": ", ".join(sorted(dates))})
    if not rows:
        return Check(OK, "No copied traffic days")
    t = pd.DataFrame(rows)
    return Check(WARN, f"{len(t)} set(s) of days with identical traffic",
                 "Every terminal has exactly the same traffic on these days — usually a day "
                 "copied by mistake.", t, len(t))


def traffic_unusual_days(file_t: pd.DataFrame, low: float = 0.5, high: float = 2.0,
                         min_usual: float = 2000) -> Check:
    """Daily rows below `low`x or above `high`x their month's median. Pools
    whose usual day is under `min_usual` (a few flights) swing too much to judge."""
    d = file_t[(file_t["granularity"] == "daily") & file_t["traffic"].notna()].copy()
    if d.empty:
        return Check(OK, "Daily traffic looks usual")
    d["month"] = d["date"].str[:7]
    d["median"] = d.groupby(["location", "terminal", "month"])["traffic"].transform("median")
    out = d[(d["median"] >= min_usual)
            & ((d["traffic"] < d["median"] * low) | (d["traffic"] > d["median"] * high))]
    if out.empty:
        return Check(OK, "Daily traffic looks usual")
    t = out.assign(Traffic=out["traffic"].map(_num), Usual=out["median"].map(_num)).rename(
        columns={"date": "Date", "location": "Location", "terminal": "Terminal"})
    return Check(WARN, f"{len(t)} day(s) with unusual traffic",
                 f"Below {low:.0%} or above {high:.0%} of the month's usual day — check the file.",
                 t[["Date", "Location", "Terminal", "Traffic", "Usual"]].head(MAX_ROWS_SHOWN), len(t))


def traffic_vs_previous_month(file_t: pd.DataFrame, stored_prev: pd.DataFrame,
                              limit: float = 0.4) -> Check:
    """Month totals per airport/terminal vs the stored month before, flagging
    changes over `limit` (e.g. a column read as the wrong terminal)."""
    if stored_prev is None or stored_prev.empty:
        return Check(INFO, "No stored earlier month to compare traffic with")
    f = file_t.assign(month=file_t["date"].str[:7])
    cur = f.groupby(["location", "terminal", "month"])["traffic"].sum().reset_index()
    s = stored_prev.assign(month=pd.to_datetime(stored_prev["date"]).dt.strftime("%Y-%m"),
                           terminal=stored_prev["terminal"].fillna("").astype(str))
    prev = s.groupby(["location", "terminal", "month"])["traffic"].sum().reset_index()
    rows = []
    for r in cur.itertuples():
        p = prev[(prev["location"] == r.location) & (prev["terminal"] == r.terminal)
                 & (prev["month"] < r.month)]
        if p.empty:
            continue
        last = p.sort_values("month").iloc[-1]
        if last["traffic"] > 0 and abs(r.traffic / last["traffic"] - 1) > limit:
            rows.append({"Location": r.location, "Terminal": r.terminal, "Month": r.month,
                         "Traffic": _num(r.traffic), "Earlier month": last["month"],
                         "Earlier traffic": _num(last["traffic"]),
                         "Change": f"{r.traffic / last['traffic'] - 1:+.0%}"})
    if not rows:
        return Check(OK, "Month totals in line with the stored earlier month")
    t = pd.DataFrame(rows)
    return Check(WARN, f"{len(t)} airport/terminal month(s) changed by more than {limit:.0%}",
                 "Compared with the latest stored earlier month. A large jump can be real "
                 "(a terminal opening or closing) or a column read wrongly — check the file.",
                 t, len(t))


def analyse_traffic(df: pd.DataFrame, stored: Optional[pd.DataFrame] = None,
                    stored_prev: Optional[pd.DataFrame] = None) -> Analysis:
    from modules import database
    a = Analysis(confidence=0.95)
    if df is None or df.empty:
        return a
    t = _traffic_keys(df)
    d0 = pd.to_datetime(t["date"]).min().date()
    d1 = pd.to_datetime(t["date"]).max().date()
    if stored is None:
        stored = database.load_traffic_for_date_range(d0, d1)
    if stored_prev is None:
        stored_prev = database.load_traffic_for_date_range(d0 - dt.timedelta(days=62),
                                                           d0 - dt.timedelta(days=1))
    if stored is not None and not stored.empty:
        a.checks.append(traffic_changes_vs_stored(t, _traffic_keys(stored)))
    else:
        a.checks.append(Check(OK, "All rows are new", f"{len(t):,} row(s), none stored yet."))
    a.checks.append(traffic_copied_days(t))
    a.checks.append(traffic_unusual_days(t))
    a.checks.append(traffic_vs_previous_month(t, stored_prev))
    skipped = df.attrs.get("skipped_sheets") or []
    if skipped:
        a.checks.append(Check(WARN, f"{len(skipped)} sheet(s) gave no rows", "\n".join(skipped),
                              count=len(skipped)))
        a.confidence = 0.7
    return a


# ---------------------------------------------------------------------------
# AOP
# ---------------------------------------------------------------------------
def analyse_aop(parsed: dict, esp: Optional[dict], stored_months) -> Analysis:
    """Months covered and already stored, totals per month, lines not
    imported. `parsed` = aop_parser.parse_aop_auto; `esp` = Sky Plates /
    Encalm Eats AOP from the same master (or None)."""
    a = Analysis(confidence=0.95)
    rows = parsed.get("aop_rows")
    if rows is None or rows.empty:
        a.checks.append(Check(WARN, "No AOP rows found in the sheet"))
        a.confidence = 0.3
        return a
    frames = [rows.assign(Segment="EHPL")]
    if esp is not None and not esp["aop_rows"].empty:
        frames.append(esp["aop_rows"].assign(Segment=esp["aop_rows"]["segment"]))
    allr = pd.concat(frames, ignore_index=True)
    months = sorted(set(zip(allr["year"], allr["month"])))
    stored = set(tuple(m) for m in (stored_months or []))
    overlap = [m for m in months if m in stored]
    label = lambda ym: dt.date(int(ym[0]), int(ym[1]), 1).strftime("%b %Y")
    detail = f"{len(months)} month(s): {label(months[0])} – {label(months[-1])}."
    if overlap:
        a.checks.append(Check(INFO, f"{len(overlap)} of {len(months)} month(s) already stored",
                              detail + " With **Replace** ticked their stored targets are "
                              "replaced by this file; otherwise stored rows are kept.",
                              count=len(overlap)))
    else:
        a.checks.append(Check(OK, "All months are new", detail))
    mult = parsed.get("units_multiplier", 1) or 1
    a.checks.append(Check(OK if mult != 1 else INFO,
                          f"Units: ×{mult:,.0f}" + (" (lakhs → rupees)" if mult == 100000 else ""),
                          "" if mult != 1 else "No 'in lakhs' note found — figures are taken as rupees."))
    tot = (allr.assign(Month=[label(m) for m in zip(allr["year"], allr["month"])],
                       _o=allr["year"] * 100 + allr["month"])
               .groupby(["_o", "Month", "Segment"])["aop"].sum().unstack("Segment").fillna(0)
               .reset_index(level=0, drop=True).reset_index())
    for c in tot.columns[1:]:
        tot[c] = tot[c].map(_money)
    a.checks.append(Check(INFO, "AOP per month in this file", "", tot, len(tot)))
    sk = parsed.get("skipped_rows")
    if sk is not None and not sk.empty:
        a.checks.append(Check(INFO, f"{len(sk)} line(s) not imported as EHPL AOP",
                              "Lines with no outlet mapping (listed with the reason).",
                              sk.head(MAX_ROWS_SHOWN), len(sk)))
    for w in (esp or {}).get("warnings", []) or []:
        a.checks.append(Check(WARN, "Sky Plates / Encalm Eats AOP", str(w)))
    return a


# ---------------------------------------------------------------------------
# Encalm Eats DSR
# ---------------------------------------------------------------------------
def analyse_dsr(result, stored: Optional[pd.DataFrame] = None) -> Analysis:
    """Days and records in a DSR file, records already stored (skipped on
    save — DSR uploads never overwrite), unknown outlets, and the last day's
    parsed total against the grand total printed in the file."""
    a = Analysis(confidence=0.95)
    recs = pd.DataFrame([{"date": r.date, "outlet": r.outlet, "location": r.location,
                          "covers": r.covers, "net_revenue": r.net_revenue}
                         for r in result.records])
    if recs.empty:
        a.checks.append(Check(WARN, "No outlet rows found"))
        a.confidence = 0.3
        return a
    if stored is not None and not stored.empty:
        k = ["date", "outlet", "location"]
        st_k = stored.assign(date=pd.to_datetime(stored["date"]).dt.date)[k].drop_duplicates()
        m = recs.merge(st_k, on=k, how="left", indicator=True)
        already = int((m["_merge"] == "both").sum())
        if already:
            a.checks.append(Check(WARN if already == len(recs) else INFO,
                                  f"{already:,} of {len(recs):,} record(s) already stored",
                                  "Stored DSR records are kept; these are skipped on save.",
                                  count=already))
        else:
            a.checks.append(Check(OK, "All records are new", f"{len(recs):,} record(s)."))
    else:
        a.checks.append(Check(OK, "All records are new", f"{len(recs):,} record(s)."))

    unknown = [w for w in result.warnings if "unknown outlet" in w.lower()]
    if unknown:
        a.checks.append(Check(WARN, f"{len(unknown)} unknown outlet name(s)",
                              "Imported as written — check the spelling against earlier DSRs.",
                              pd.DataFrame({"Message": unknown}).head(MAX_ROWS_SHOWN), len(unknown)))
    others = [w for w in result.warnings if w not in unknown]
    if others:
        a.checks.append(Check(INFO, f"{len(others)} note(s) from the reader",
                              "", pd.DataFrame({"Message": others}).head(MAX_ROWS_SHOWN), len(others)))

    gt = result.source_grand_total_revenue
    if gt:
        last = recs["date"].max()
        day = float(recs.loc[recs["date"] == last, "net_revenue"].fillna(0).sum())
        if abs(day - gt) <= 1:
            a.checks.append(Check(OK, "Last day matches the file's grand total",
                                  f"{last}: {_money(day)}."))
        else:
            a.checks.append(Check(INFO, "Last day vs the file's grand total",
                                  f"{last}: outlets add up to {_money(day)}; the grand-total line "
                                  f"shows {_money(gt)} (it may be month- or year-to-date)."))
    return a
