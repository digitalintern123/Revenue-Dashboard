"""
modules/lounge_capacity.py — Physical seating capacity (Covers) per lounge,
sourced from "ALL Services (Area and Covers).xlsx" — the updated, more
complete capacity reference (68 rows across Delhi/Hyderabad/Goa, replacing
the earlier "Lounge_Covers.xlsx" source). Used to compute
Turnaround = PAX ÷ Covers, i.e. how many times a lounge's seats get
reused in a day.

CAPACITY_MAP is keyed by (location, canonical_outlet_name) — the same
canonical outlet names produced by database.canonicalize_outlet_name(), so
it lines up directly with the outlet/location columns already in every
revenue row.

Judgment calls made while mapping this file (documented here so they're
easy to revisit):
  • "Reserved Lounge" combines every "RL ..." row for a given location
    (T1/T3 departure/arrival at Delhi; domestic/international arrival/
    departure splits at Hyderabad and Goa) into one total, matching how
    the revenue database tracks Reserved Lounge as a single outlet.
  • Rows explicitly marked "Upcoming" (5 F&B outlets at T2, Amex Lounge at
    Hyderabad, the new Hyderabad International Card Lounge, MLCP, 8 F&B
    outlets at T3) are NOT yet operational, so they're excluded rather
    than counted — their seats don't exist in the revenue data yet.
  • Hyderabad International Lounge currently uses the "Hyd Intl Lounge -
    Closing" figure (155) — the lounge still operating today — not the
    323-seat "new (Level E) - Upcoming" replacement, since that hasn't
    opened yet. Update this once the new lounge goes live.
  • Round D Clock (RDC) at Delhi uses only the "RDC F&B" seating (122) —
    the actual dine-in covers. "RDC - Room" (27 rooms) and "RDC Dorm" (12
    beds) are overnight-stay units, not seats, so they're excluded rather
    than mixed into a seat-turnover metric; "RDC - F&B + Rooms" (27) looks
    like a legacy/duplicate line against the same facility and is skipped
    to avoid double-counting.
  • Goa's CIP Lounge has no covers figure in this file (shown as "-"), so
    it's intentionally left unmapped here even though the previous source
    file had a number for it — this file is the more current one.
  • Business Centre (Delhi) has a genuine 0 in the source file (not a
    missing value) — kept as 0, which naturally produces a "—" Turnaround
    rather than a divide-by-zero.

Coverage: every currently-operational lounge/service with a real seat
count in the source file. Ancillary services with no fixed seating (Meet
& Greet, Porter, Buggy Service, Baggage Wrapping, Sky Plates) are handled
separately — see NON_LOUNGE_KEYWORDS below — since Covers isn't a
meaningful concept for them at all, not just "unmapped."

To add or correct a lounge: insert/edit its (location, outlet) -> covers
entry below. No other code changes needed.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

CAPACITY_MAP: dict[tuple[str, str], int] = {
    # ── Delhi ────────────────────────────────────────────────────────────
    ("Delhi", "Domestic Lounge - T1 L4&5"): 424,
    ("Delhi", "Domestic Lounge - T1 Prive"):  101,
    ("Delhi", "Centurion Lounge T1"):          77,
    ("Delhi", "Domestic Spa - T1"):            16,
    ("Delhi", "Domestic Lounge - T2"):        110,
    ("Delhi", "Domestic Lounge - D49"):       109,
    ("Delhi", "Domestic Lounge T3"):          266,   # DLO2/03/04, combined
    ("Delhi", "Centurion Lounge T3"):          36,
    ("Delhi", "Domestic Lounge - Rupay"):      81,
    ("Delhi", "Domestic Lounge - Air India"):  87,
    ("Delhi", "International Lounge"):        300,   # T3 INL 5&6
    ("Delhi", "Premium Lounge"):              528,   # T3 Premium (Prive)
    ("Delhi", "First Class - Xenia Lounge"):   53,
    ("Delhi", "International Lounge - Air India"): 286,
    ("Delhi", "NAP - Premium Lounge"):          6,   # LA-01
    ("Delhi", "Sleeping Pod - Premium Lounge"): 14,  # LA-12
    ("Delhi", "Arrival Lounge - LA22"):        53,
    ("Delhi", "Spa - International"):          12,   # INTL Spa
    ("Delhi", "Domestic Spa - T3"):            10,   # "Dom Spa Transitioning to INL"
    ("Delhi", "CIP Lounge"):                  214,
    ("Delhi", "Business Centre"):               0,
    ("Delhi", "Reserved Lounge"):              225,  # RL T1 Dep(73)+T1 Arr(34)+T3 Dep(65)+T3 Dom Arr(33)+T3 Intl Arr(20)
    ("Delhi", "Round D Clock (RDC)"):         122,   # RDC F&B seating only

    # ── Hyderabad ────────────────────────────────────────────────────────
    ("Hyderabad", "Domestic Lounge T3"):      402,
    ("Hyderabad", "Domestic Lounge - Prive"):  182,   # Prive lounge at Hyderabad
    ("Hyderabad", "International Lounge"):    155,   # "Closing" lounge, still operating
    ("Hyderabad", "Premium Lounge"):          170,   # INT Prive - Mezzanine
    ("Hyderabad", "Hyd GA Lounge"):            31,
    ("Hyderabad", "Transit Hotel"):            57,
    ("Hyderabad", "Airport Lodge"):            54,
    ("Hyderabad", "Reserved Lounge"):         176,   # Dom Arrival D(24)+Dom Dep E(45)+Dom Dep F(79)+Int Arrival D(28)

    # ── Goa ──────────────────────────────────────────────────────────────
    ("Goa", "Domestic Lounge T3"):            129,
    ("Goa", "International Lounge"):           40,
    ("Goa", "Reserved Lounge"):                46,   # Dom Departure(16)+Dom Arrival(16)+Int Arrival(14)
}


def get_capacity(outlet: str, location: str) -> Optional[int]:
    """Covers (seat capacity) for a given (outlet, location), or None if not mapped."""
    location_key = str(location).strip().title()
    outlet_key = str(outlet).strip()
    return CAPACITY_MAP.get((location_key, outlet_key))


def add_capacity_column(df: pd.DataFrame) -> pd.DataFrame:
    """Add a `capacity` column (Covers), NaN where the outlet isn't mapped."""
    if df is None or df.empty:
        return df
    out = df.copy()
    out["capacity"] = out.apply(
        lambda r: get_capacity(r["outlet"], r["location"]), axis=1
    )
    return out


def turnaround(avg_daily_pax: float, capacity: Optional[float]) -> Optional[float]:
    """
    Turnaround = average daily PAX ÷ Covers (seat capacity) — how many
    times the lounge's seats are reused per day. None if capacity is
    unknown or zero (rather than a misleading 0 or inf).
    """
    if capacity is None or pd.isna(capacity) or capacity == 0:
        return None
    if avg_daily_pax is None or pd.isna(avg_daily_pax):
        return None
    return float(avg_daily_pax) / float(capacity)


# Ancillary services that are never seated lounges — no Covers concept
# applies to them at all (not "capacity unknown", but "capacity doesn't
# mean anything here"). Matched by substring, case-insensitive, so both
# "Sky Plates" and "Encalm Sky Plates" (and Hyderabad/Goa variants like
# "Meet & Greet (Hyderabad)") are caught regardless of exact naming.
NON_LOUNGE_KEYWORDS: tuple[str, ...] = (
    "meet & greet",
    "porter",
    "baggage wrapping",
    "sky plates",
    "buggy",
    "encalm eats",   # restaurant — no fixed seating capacity in capacity file
)

# Outlets excluded by exact name match (not substring) — used for short
# acronym-style names like "GAT" where a substring match would risk false
# positives against unrelated outlet names.
EXACT_EXCLUDE_OUTLETS: frozenset[str] = frozenset({
    "gat",
    "cip lounge",   # no capacity data available in source file for Goa CIP Lounge
})


def is_non_lounge_service(outlet: str) -> bool:
    """True if this outlet should not appear on the Covers page at all —
    either an ancillary service with no Covers concept (Meet & Greet,
    Porter, Baggage Wrapping, Sky Plates, Buggy Service), or explicitly
    excluded by name (GAT), rather than a seated lounge that simply has
    no capacity figure mapped yet."""
    outlet_lower = str(outlet).strip().lower()
    if outlet_lower in EXACT_EXCLUDE_OUTLETS:
        return True
    return any(keyword in outlet_lower for keyword in NON_LOUNGE_KEYWORDS)
