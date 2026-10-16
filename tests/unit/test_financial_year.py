"""Year-wise comparison uses the Indian financial year (1 April – 31 March)."""

import datetime as dt

import pytest

from modules import revenue_analysis as ra

D = dt.date


@pytest.mark.parametrize("day,fy", [
    (D(2026, 4, 1), 2026), (D(2026, 10, 15), 2026), (D(2027, 3, 31), 2026), (D(2026, 3, 31), 2025),
])
def test_fy_start_year(day, fy):
    assert ra.fy_start_year(day) == fy


def test_fy_label():
    assert ra.fy_label(2026) == "FY 2026-27"
    assert ra.fy_label(2099) == "FY 2099-00"


def test_to_date_runs_from_1_april_to_same_day_last_fy():
    r = ra.resolve_comparison_ranges("Year-wise", D(2026, 10, 15), mode="To-Date")
    assert (r["current_start"], r["current_end"]) == (D(2026, 4, 1), D(2026, 10, 15))
    assert (r["compare_start"], r["compare_end"]) == (D(2025, 4, 1), D(2025, 10, 15))
    assert r["current_label"] == "FY 2026-27 (1 Apr–15 Oct)"
    assert r["compare_label"] == "FY 2025-26 (1 Apr–15 Oct)"


def test_to_date_in_january_to_march_stays_in_the_same_fy():
    r = ra.resolve_comparison_ranges("Year-wise", D(2026, 2, 10), mode="To-Date")
    assert (r["current_start"], r["current_end"]) == (D(2025, 4, 1), D(2026, 2, 10))
    assert (r["compare_start"], r["compare_end"]) == (D(2024, 4, 1), D(2025, 2, 10))


def test_to_date_leap_day_maps_to_28_feb():
    r = ra.resolve_comparison_ranges("Year-wise", D(2024, 2, 29), mode="To-Date")
    assert r["compare_end"] == D(2023, 2, 28)


def test_full_period_and_chosen_compare_fy():
    r = ra.resolve_comparison_ranges("Year-wise", D(2026, 10, 15), compare_year=2023)
    assert (r["current_start"], r["current_end"]) == (D(2026, 4, 1), D(2027, 3, 31))
    assert (r["compare_start"], r["compare_end"]) == (D(2023, 4, 1), D(2024, 3, 31))
    assert ra.short_period_label(r["compare_start"], r["compare_end"], "Year-wise") == "FY 2023-24"
