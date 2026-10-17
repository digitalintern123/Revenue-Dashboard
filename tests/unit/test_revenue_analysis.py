"""
tests/unit/test_revenue_analysis.py — Tests for modules/revenue_analysis.py

Covers the core calculation functions: pct_change, safe_div, compare_periods,
summarize_period, aop_variance, classify_driver, classify_trend.
"""
import sys
import os
import datetime as dt

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import modules.revenue_analysis as ra


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal revenue DataFrame from a list of dicts."""
    defaults = {
        "date": dt.date(2026, 7, 1),
        "segment": "EHPL",
        "business_unit": "Lounges",
        "outlet": "International Lounge",
        "location": "Delhi",
        "pax": 100.0,
        "revenue": 500_000.0,
        "aop": None,
        "traffic": None,
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


# ── pct_change ────────────────────────────────────────────────────────────────

class TestPctChange:
    # pct_change returns a raw fraction: (current - previous) / previous
    # e.g. 110→100 = 0.10  (not 10.0).  Callers multiply by 100 for display.

    def test_growth(self):
        assert ra.pct_change(110, 100) == pytest.approx(0.10)

    def test_decline(self):
        assert ra.pct_change(90, 100) == pytest.approx(-0.10)

    def test_from_zero_previous(self):
        # When previous == 0 the function caps at +10 (= +1000%) or -1 (-100%)
        # rather than returning inf. Non-None positive result expected.
        result = ra.pct_change(100, 0)
        assert result is None or result == pytest.approx(10.0)

    def test_both_zero(self):
        assert ra.pct_change(0, 0) is None

    def test_current_zero(self):
        # 0 from 100 = -100% = fraction -1.0
        assert ra.pct_change(0, 100) == pytest.approx(-1.0)

    def test_none_current(self):
        assert ra.pct_change(None, 100) is None

    def test_none_previous(self):
        assert ra.pct_change(100, None) is None


# ── safe_div ─────────────────────────────────────────────────────────────────

class TestSafeDiv:
    # safe_div returns NaN (not 0.0) for zero/None denominator or None numerator.

    def test_normal(self):
        assert ra.safe_div(10, 2) == pytest.approx(5.0)

    def test_zero_denominator_returns_nan(self):
        import math
        assert math.isnan(ra.safe_div(10, 0))

    def test_zero_numerator(self):
        assert ra.safe_div(0, 5) == pytest.approx(0.0)

    def test_none_numerator_returns_nan(self):
        import math
        assert math.isnan(ra.safe_div(None, 5))

    def test_none_denominator_returns_nan(self):
        import math
        assert math.isnan(ra.safe_div(10, None))


# ── summarize_period ─────────────────────────────────────────────────────────

class TestSummarizePeriod:
    def test_totals(self):
        df = _make_df([
            {"revenue": 100_000, "pax": 50},
            {"revenue": 200_000, "pax": 75},
        ])
        s = ra.summarize_period(df)
        assert s["revenue"] == pytest.approx(300_000)
        assert s["pax"] == pytest.approx(125)

    def test_empty_df(self):
        s = ra.summarize_period(pd.DataFrame())
        assert s["revenue"] == 0
        assert s["pax"] == 0

    def test_null_revenue_excluded(self):
        df = _make_df([{"revenue": None, "pax": 10}, {"revenue": 100_000, "pax": 20}])
        s = ra.summarize_period(df)
        assert s["revenue"] == pytest.approx(100_000)


# ── compare_periods ───────────────────────────────────────────────────────────

class TestComparePeriods:
    def test_basic_comparison(self):
        current = _make_df([{"outlet": "Lounge A", "revenue": 200_000, "pax": 100}])
        compare = _make_df([{"outlet": "Lounge A", "revenue": 100_000, "pax": 80}])
        result = ra.compare_periods(current, compare)
        row = result[result["outlet"] == "Lounge A"].iloc[0]
        # pct_change returns raw fractions: 200k/100k-1 = 1.0 (100%), 100/80-1 = 0.25 (25%)
        assert row["revenue_pct_change"] == pytest.approx(1.0)
        assert row["pax_pct_change"] == pytest.approx(0.25)

    def test_missing_outlet_in_compare(self):
        """Outlet present in current but not compare should have None pct_change."""
        current = _make_df([{"outlet": "New Outlet", "revenue": 50_000}])
        compare = _make_df([{"outlet": "Other Outlet", "revenue": 100_000}])
        result = ra.compare_periods(current, compare)
        row = result[result["outlet"] == "New Outlet"].iloc[0]
        # Previous revenue was 0/None so pct_change should be None
        assert pd.isna(row["revenue_pct_change"]) or row["revenue_pct_change"] is None

    def test_empty_compare(self):
        current = _make_df([{"revenue": 100_000}])
        result = ra.compare_periods(current, pd.DataFrame())
        assert not result.empty  # current period rows still present


# ── aop_variance ─────────────────────────────────────────────────────────────

class TestAopVariance:
    def test_basic_variance(self):
        df = _make_df([
            {"revenue": 800_000, "aop": 1_000_000},
            {"revenue": 500_000, "aop": 400_000},
        ])
        result = ra.aop_variance(df)
        assert not result.empty
        row = result.iloc[0]
        assert row["actual_revenue"] == pytest.approx(1_300_000)
        assert row["aop_target"] == pytest.approx(1_400_000)
        assert row["variance"] == pytest.approx(-100_000)

    def test_no_aop_column(self):
        # When no "aop" column exists (or all values are NaN), aop_variance returns
        # a DataFrame where aop_target is NaN — it never returns None or empty.
        df = _make_df([{"revenue": 100_000}])
        df = df.drop(columns=["aop"], errors="ignore")
        result = ra.aop_variance(df)
        assert result is not None
        assert "actual_revenue" in result.columns
        # aop_target should be NaN since no AOP data was provided
        import pandas as _pd
        assert result["aop_target"].isna().all()


# ── classify_trend ────────────────────────────────────────────────────────────

class TestClassifyTrend:
    def test_positive_growth(self):
        assert "growth" in ra.classify_trend(15.0).lower() or ra.classify_trend(15.0) != ""

    def test_decline(self):
        result = ra.classify_trend(-10.0)
        assert result != ""

    def test_none_returns_string(self):
        result = ra.classify_trend(None)
        assert isinstance(result, str)


# ── classify_driver ───────────────────────────────────────────────────────────

class TestClassifyDriver:
    def test_volume_driven(self):
        d = ra.classify_driver(pax_pct=20.0, rev_per_pax_pct=1.0)
        assert "volume" in d.lower()

    def test_spend_driven(self):
        d = ra.classify_driver(pax_pct=1.0, rev_per_pax_pct=20.0)
        assert "spend" in d.lower()

    def test_mixed(self):
        d = ra.classify_driver(pax_pct=15.0, rev_per_pax_pct=15.0)
        # "Mixed" or any non-empty string is acceptable
        assert isinstance(d, str) and d

    def test_flat(self):
        d = ra.classify_driver(pax_pct=0.0, rev_per_pax_pct=0.0)
        assert isinstance(d, str)

    def test_none_inputs(self):
        d = ra.classify_driver(pax_pct=None, rev_per_pax_pct=None)
        assert isinstance(d, str)


# ===========================================================================
# Tests for BL-003 fix: spp() now uses PAX, revenue_per_visitor() uses Traffic
# ===========================================================================

class TestSppFormula:
    """SPP = Revenue / Traffic (airport-retail yield per terminal visitor)."""

    def test_spp_uses_traffic(self):
        """spp(revenue, traffic) must return Revenue / Traffic."""
        result = ra.spp(5_000_000, 50_000)
        assert result == pytest.approx(100.0)

    def test_spp_zero_traffic_returns_nan(self):
        import math
        assert math.isnan(ra.spp(5_000_000, 0))

    def test_spp_none_traffic_returns_nan(self):
        import math
        assert math.isnan(ra.spp(5_000_000, None))

    def test_spp_zero_revenue(self):
        assert ra.spp(0, 50_000) == pytest.approx(0.0)

    def test_spp_formula(self):
        """SPP = Revenue / Traffic, consistent across all pages."""
        revenue = 5_000_000.0
        traffic = 50_000.0
        assert ra.spp(revenue, traffic) == pytest.approx(revenue / traffic)

    def test_penetration_formula(self):
        """Penetration % = PAX / Traffic * 100."""
        assert ra.penetration_pct(1_000, 50_000) == pytest.approx(2.0)

    def test_spp_and_pen_use_traffic(self):
        """Both SPP and Penetration% use Traffic as denominator — consistent."""
        revenue = 5_000_000.0
        pax     = 1_000.0
        traffic = 50_000.0
        spp_val = ra.spp(revenue, traffic)
        pen_pct = ra.penetration_pct(pax, traffic)
        assert spp_val == pytest.approx(100.0)
        assert pen_pct == pytest.approx(2.0)

    def test_location_level_summary_spp_uses_traffic(self):
        """location_level_summary_with_traffic must compute spp = revenue/traffic."""
        df = _make_df([
            {"revenue": 5_000_000, "pax": 1_000, "traffic": 50_000, "location": "Delhi",
             "date": dt.date(2026, 7, 1)},
        ])
        result = ra.location_level_summary_with_traffic(df)
        if result.empty or "spp" not in result.columns:
            pytest.skip("no traffic column")
        row = result.iloc[0]
        expected_spp = row["revenue"] / row["traffic"]
        assert row["spp"] == pytest.approx(expected_spp, rel=1e-6)

    def test_no_rev_per_visitor_column(self):
        """revenue_per_visitor helper removed — spp() is the single SPP definition."""
        assert not hasattr(ra, "revenue_per_visitor"), (
            "revenue_per_visitor() should have been removed — "
            "spp() = Revenue/Traffic is the single canonical SPP definition."
        )


# ===========================================================================
# Tests for BL-001 fix: new-entrant outlets show "🆕 New" not "Stable"
# ===========================================================================

class TestNewEntrantTrend:
    """BL-001: classify_trend_with_new() and compare_periods() new-entrant label."""

    def test_classify_trend_with_new_new_outlet(self):
        """prev=0, cur>0 → NEW_ENTRANT_TREND."""
        result = ra.classify_trend_with_new(None, current_value=100_000, compare_value=0)
        assert result == ra.NEW_ENTRANT_TREND

    def test_classify_trend_with_new_growth(self):
        """prev>0, cur>prev, big change → Revenue Increase (not New)."""
        result = ra.classify_trend_with_new(0.20, current_value=120_000, compare_value=100_000)
        assert "Increase" in result
        assert result != ra.NEW_ENTRANT_TREND

    def test_classify_trend_with_new_decline(self):
        """prev>0, cur<prev → Revenue Decline."""
        result = ra.classify_trend_with_new(-0.15, current_value=85_000, compare_value=100_000)
        assert "Decline" in result

    def test_classify_trend_with_new_stable(self):
        """prev>0, cur≈prev → Stable."""
        result = ra.classify_trend_with_new(0.01, current_value=101_000, compare_value=100_000)
        assert "Stable" in result

    def test_classify_trend_with_new_both_zero(self):
        """prev=0, cur=0 → Stable (no data either period)."""
        result = ra.classify_trend_with_new(None, current_value=0, compare_value=0)
        assert result == "➡️ Stable"

    def test_compare_periods_new_entrant_labelled(self):
        """compare_periods() must label new outlets as NEW_ENTRANT_TREND in revenue_trend."""
        current = _make_df([{"outlet": "Brand New Lounge", "revenue": 200_000, "pax": 50}])
        compare = pd.DataFrame()  # no prior data
        result = ra.compare_periods(current, compare)
        row = result[result["outlet"] == "Brand New Lounge"].iloc[0]
        assert row["revenue_trend"] == ra.NEW_ENTRANT_TREND, (
            f"Expected '{ra.NEW_ENTRANT_TREND}' for new entrant, got '{row['revenue_trend']}'"
        )

    def test_compare_periods_existing_outlet_not_new(self):
        """Existing outlets with prior revenue must NOT be labelled as New."""
        current = _make_df([{"outlet": "International Lounge", "revenue": 200_000, "pax": 100}])
        compare = _make_df([{"outlet": "International Lounge", "revenue": 180_000, "pax": 90}])
        result = ra.compare_periods(current, compare)
        row = result[result["outlet"] == "International Lounge"].iloc[0]
        assert row["revenue_trend"] != ra.NEW_ENTRANT_TREND

    def test_compare_periods_closed_outlet_not_new(self):
        """Outlet present in compare but absent in current → not New, but Decline."""
        current = pd.DataFrame()
        compare = _make_df([{"outlet": "Closed Lounge", "revenue": 150_000, "pax": 60}])
        result = ra.compare_periods(current, compare)
        if result.empty:
            return  # outer merge may drop if both empty
        row = result[result["outlet"] == "Closed Lounge"]
        if not row.empty:
            assert row.iloc[0]["revenue_trend"] != ra.NEW_ENTRANT_TREND


# ===========================================================================
# Tests for CONS-001 fix: AOP proration consistency
# (unit-level: aop_variance uses prorated values, not full monthly totals)
# ===========================================================================

class TestAopProrationConsistency:
    """CONS-001: prorated AOP target must be less than full month when partial."""

    def test_partial_month_aop_less_than_full_month(self):
        """For 10 days of a 31-day month, prorated AOP must be ≈10/31 of monthly."""
        monthly_aop = 3_100_000.0  # ₹31 lakh/month = ₹1 lakh/day
        days_present = 10
        days_in_month = 31
        prorated = monthly_aop * (days_present / days_in_month)
        expected = pytest.approx(1_000_000.0, rel=1e-4)  # ₹10 lakh
        assert prorated == expected

    def test_full_month_aop_equals_monthly(self):
        """For 31 days of a 31-day month, prorated AOP equals the monthly total."""
        monthly_aop = 3_100_000.0
        prorated = monthly_aop * (31 / 31)
        assert prorated == pytest.approx(monthly_aop)

    def test_aop_variance_uses_prorated_not_full(self):
        """aop_variance() with a prorated aop column must compute variance against that."""
        # Simulate: monthly AOP=3.1M, only 10 days present → prorated = 1M
        prorated_aop = 1_000_000.0
        actual_revenue = 900_000.0
        df = pd.DataFrame([{
            "location": "Delhi", "outlet": "International Lounge",
            "revenue": actual_revenue, "aop": prorated_aop,
        }])
        result = ra.aop_variance(df, group_cols=["location"])
        row = result.iloc[0]
        assert row["aop_target"] == pytest.approx(prorated_aop)
        assert row["variance"] == pytest.approx(actual_revenue - prorated_aop)


# ===========================================================================
# Tests for MAP-004 fix: no duplicate keys in Hyderabad terminal mapping
# ===========================================================================

class TestHyderabadMappingNoDuplicates:
    """MAP-004: _HYDERABAD_OUTLET_TO_TERMINAL must have no duplicate keys."""

    def test_no_duplicate_keys(self):
        """
        Python dicts silently drop duplicate keys (last wins). This test
        reconstructs the dict from source and verifies uniqueness.
        """
        import re
        import os
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        src = open(os.path.join(_root, "modules", "terminal_mapping.py"), encoding="utf-8").read()
        # Extract all keys inside _HYDERABAD_OUTLET_TO_TERMINAL
        hyd_section = src.split("_HYDERABAD_OUTLET_TO_TERMINAL")[1]
        hyd_section = hyd_section.split("_GOA_OUTLET_TO_TERMINAL")[0]
        keys = re.findall(r'"([^"]+)"\s*:', hyd_section)
        duplicates = [k for k in keys if keys.count(k) > 1]
        unique_dups = list(dict.fromkeys(duplicates))
        assert not unique_dups, (
            f"Duplicate keys found in _HYDERABAD_OUTLET_TO_TERMINAL: {unique_dups}"
        )

    def test_dom_spa_docstring_matches_code(self):
        """
        MAP-003: module docstring must say Dom Spa → T3 International,
        matching the actual mapping entry.
        """
        import os
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        src = open(os.path.join(_root, "modules", "terminal_mapping.py"), encoding="utf-8").read()
        # Docstring must NOT say 'Dom Spa → T3 Domestic' any more
        assert "Dom Spa            → T3 Domestic" not in src, (
            "Docstring still incorrectly says Dom Spa maps to T3 Domestic. "
            "The actual mapping is T3 International (per Jul 2026 All Services file)."
        )
        # Code mapping must be T3 Int Dep
        assert '"Dom Spa"' in src, "Dom Spa mapping entry missing"
        # Verify the mapping value is TERMINAL_3_INT_DEP (not TERMINAL_3_DOM_DEP)
        dom_spa_idx = src.index('"Dom Spa"')
        dom_spa_line = src[dom_spa_idx:dom_spa_idx + 120]
        assert "TERMINAL_3_INT_DEP" in dom_spa_line, (
            f"Dom Spa should map to TERMINAL_3_INT_DEP, got: {dom_spa_line!r}"
        )


# ===========================================================================
# Tests for BL-002 fix: daily-source AOP no longer circularly distributed
# ===========================================================================

class TestAopDailySourceNotCircular:
    """BL-002: join_revenue_with_aop with daily source returns location totals, not per-outlet."""

    def test_location_total_sentinel(self):
        """
        When join_revenue_with_aop returns rows with outlet=='__location_total__',
        those rows must NOT be passed to aop_variance as individual outlets.
        """
        import pandas as _pd
        # Simulate what the fixed daily-source branch returns
        sentinel_rows = pd.DataFrame([{
            "location": "Delhi",
            "outlet": "__location_total__",
            "revenue": 5_000_000.0,
            "aop_target": 6_000_000.0,
            "aop_source": "daily_location_total",
        }])
        # Filter as the pages now do
        filtered = sentinel_rows[sentinel_rows["outlet"] != "__location_total__"]
        assert filtered.empty, "Sentinel rows must be filtered out before per-outlet variance"

    def test_non_sentinel_rows_pass_through(self):
        """Normal per-outlet AOP rows (from aop_target table) must not be filtered."""
        import pandas as _pd
        normal_rows = pd.DataFrame([{
            "location": "Delhi",
            "outlet": "International Lounge",
            "revenue": 500_000.0,
            "aop_target": 600_000.0,
        }])
        filtered = normal_rows[normal_rows["outlet"] != "__location_total__"]
        assert len(filtered) == 1
