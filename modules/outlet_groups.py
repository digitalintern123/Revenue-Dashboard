"""
modules/outlet_groups.py — Outlet grouping and display name configuration.

Defines the exact row order for the Business Performance MIS report,
matching the Excel management report structure for Delhi, Hyderabad, and Goa.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Display name overrides — raw outlet name → display name shown in UI
# ---------------------------------------------------------------------------
OUTLET_DISPLAY_NAMES: dict[str, str] = {
    # Delhi — T1 Domestic
    "T1D Lounge":                              "Encalm Lounge (T1 D)",
    "T1D L4&5 Lounge":                         "Encalm Lounge (T1 D)",
    "T1D Lounge-1 Node L4&5 Card":             "Encalm Lounge (T1 D)",
    "Domestic Lounge - T1 L4&5":              "Encalm Lounge (T1 D)",
    # "Regular Lounge" was the name used Dec 2022–Mar 2023 for the same T1D outlet.
    # No separate row needed — merges into Encalm Lounge (T1 D).
    "Regular Lounge":                          "Encalm Lounge (T1 D)",
    "T1D new premium lounge 2 (level 5)":      "Encalm Prive (T1)",
    "Domestic Lounge - T1 Prive":             "Encalm Prive (T1)",
    "Dom Prive":                               "Encalm Prive (T1)",
    "T1D new Amex Lounge (level 4)":           "Amex Lounge T1",
    "Centurion Lounge T1":                     "Amex Lounge T1",
    "DomesticLounge- Centurion Amex T1":       "Amex Lounge T1",
    # Delhi — T2
    "T2 Domestic":                             "Encalm Lounge (T2, D)",
    "Domestic Lounge - T2":                   "Encalm Lounge (T2, D)",
    "Domestic Bar - T2":                      "Encalm Lounge (T2, D)",
    # Delhi — T3 Domestic
    "T3 DLO2/03/04":                           "Encalm Lounge (T3 DL023 &4)",
    "T3 DL023 &4":                             "Encalm Lounge (T3 DL023 &4)",
    "T3 DL02/03/04":                           "Encalm Lounge (T3 DL023 &4)",
    "Lounge DL 02,03,04":                      "Encalm Lounge (T3 DL023 &4)",
    "Lounge DL 02&03":                         "Encalm Lounge (T3 DL023 &4)",
    "Domestic Lounge T3":                      "Encalm Lounge (T3 DL023 &4)",
    "Domestic Lounge (DEL DLO2/3/4, HYD)":    "Encalm Lounge (T3 DL023 &4)",
    "Domestic Bar - DLO2/3/4, Hyd & Goa":     "Encalm Lounge (T3 DL023 &4)",
    "T3 Domestic DL02/3/4":                    "Encalm Lounge (T3 DL023 &4)",
    "T3 D49":                                  "Encalm Lounge (T3 –D 49)",
    "T3 Air India Dom":                        "Air India Lounge (T3 Dom)",
    "Domestic Lounge - D49":                  "Encalm Lounge (T3 –D 49)",
    "Domestic Bar - D49":                     "Encalm Lounge (T3 –D 49)",
    "Domestic AI Lounge Del":                  "Air India Lounge (T3 Dom)",
    "Domestic Lounge - Air India":            "Air India Lounge (T3 Dom)",
    "Air India":                               "Air India Lounge (T3 Dom)",
    "Rupay":                                   "Lounge Rupay",
    "Lounge - Rupay":                          "Lounge Rupay",
    "Domestic Lounge - Rupay":                "Lounge Rupay",
    "Domestic Bar - Rupay":                   "Lounge Rupay",
    "Lounge - Amex Centurion":                 "Lounge Amex Centurion",
    "Centurion Lounge":                        "Lounge Amex Centurion",
    "Centurion Lounge T3":                     "Lounge Amex Centurion",
    "DomesticLounge- Centurion Amex T3":       "Lounge Amex Centurion",
    # Delhi — T3 International
    "INL 5&6":                                 "Encalm Lounge (T3 INT)",
    "T3 INL 5&6":                              "Encalm Lounge (T3 INT)",
    "International Lounge":                    "Encalm Lounge (T3 INT)",
    "International Lounge (DEL INL5&6; HYD & GOA)": "Encalm Lounge (T3 INT)",
    # "International Bar - INL5&6, Hyd & Goa" is the bar at Delhi T3 INT (not HYD/GOA).
    # Merges into Encalm Lounge (T3 INT) — no separate row needed.
    "International Bar - INL5&6, Hyd & Goa":  "Encalm Lounge (T3 INT)",
    "Premium Lounge":                          "Encalm Prive (T3)",
    "T3 Premium":                              "Encalm Prive (T3)",
    "International Lounge - Premium":          "Encalm Prive (T3)",
    "International Bar -  Premium Lounge":     "Encalm Prive (T3)",
    "Xenia":                                   "Encalm Xenia",
    "First Class - Xenia Lounge":             "Encalm Xenia",
    "Xenia - INL T3":                          "Encalm Xenia",
    "AI International Lounge":                 "AI International",
    "International Lounge - Air India":       "AI International",
    # Delhi — T3 Arrivals
    "T3 Arrivals LA22":                        "Arrival Lounge- ( T3 LA22)",
    "T3 Nap LA01":                             "Nap Rooms LA01",
    "T3 Nap LA12":                             "Nap Rooms LA12",
    "Arrival Lounge LA 22":                    "Arrival Lounge- ( T3 LA22)",
    "Arrival Lounge - LA22":                  "Arrival Lounge- ( T3 LA22)",
    "LA 22":                                   "Arrival Lounge- ( T3 LA22)",
    "Nap & Shower LA01":                       "Nap Rooms LA01",
    "Transit Lounge - LA01":                  "Nap Rooms LA01",
    "NAP - Premium Lounge":                   "Nap Rooms LA01",
    "Nap & Shower LA12":                       "Nap Rooms LA12",
    "Transit Lounge - LA12":                  "Nap Rooms LA12",
    "Sleeping Pod - Premium Lounge":          "Nap Rooms LA12",
    "Reserved Lounge":                         "RL Delhi",
    "RL Delhi":                                "RL Delhi",
    # Group-key display names (used by page 8 _build_location_report)
    "T1D (Lounges)":                           "Encalm Lounge (T1 D)",
    "Encalm Prive (T1)":                       "Encalm Prive (T1)",
    "Amex Lounge T1":                          "Amex Lounge T1",
    "T2 (Lounges)":                            "Encalm Lounge (T2 D)",
    "T3 International":                        "Encalm Lounge (T3 INT)",
    "Encalm Prive T3":                         "Encalm Prive (T3)",
    "AI International":                        "AI International",
    "Enwrap":                                  "Enwrap",
    "Atithya (M&G)":                           "Atithya",
    "Atithya (Porter)":                        "Porter",
    "Atithya (Buggy)":                         "Buggy",
    "Spa T3 INT":                              "Encalm Spa (T3 INT)",
    "Spa T3 Dom":                              "Encalm Spa (T3 Dom)",
    "Spa T1":                                  "Encalm Spa (T1 Dom)",
    "Encalm Eats (Delhi)":                     "Encalm Eats",
    "Sky Plates (Delhi)":                      "Encalm Sky Plates",
    # Delhi — Atithya / Ancillary
    "Baggage Wrapping":                        "Enwrap",
    "Enwrap Services":                         "Enwrap",
    "Meet & Greet":                            "Atithya",    # Delhi: M&G -> Atithya
    "Welcome & Assist":                        "Atithya",
    "Porter":                                  "Porter",
    "Porter Services- T1":                    "Porter",
    "Porter Services -T2":                    "Porter",
    "Porter Services -T3":                    "Porter",
    "Buggy Service":                           "Buggy",
    "Buggy Services":                          "Buggy",
    "Buggy Del":                               "Buggy",
    "Business Centre":                         "Business Centre",
    "Business Center":                         "Business Centre",
    "Round D Clock (RDC)":                    "Round D Clock (RDC)",
    "Round D Clock (RDC)-Restaurant":         "Round D Clock (RDC)",
    "Round D Clock - Motel":                  "Round D Clock - Motel",
    "Round D Clock -Motel":                   "Round D Clock - Motel",
    # Delhi — Spa
    "T1D SPA":                                 "Encalm Spa (T1 Dom)",
    "Dom Spa":                                 "Encalm Spa (T3 Dom)",
    "SPA Domestic":                            "Encalm Spa (T3 Dom)",
    "Domestic Spa - T1":                      "Encalm Spa (T1 Dom)",
    "Domestic Spa- T1":                       "Encalm Spa (T1 Dom)",
    "INTL Spa":                                "Encalm Spa (T3 INT)",
    "Spa - International":                    "Encalm Spa (T3 INT)",
    "International Spa- INL07 T3":            "Encalm Spa (T3 INT)",
    "SPA - Premium Lounge":                   "Encalm Spa (T3 INT)",
    "Domestic Spa - T3":                      "Encalm Spa (T3 Dom)",
    "Domestic Spa- DPA10 T3":                 "Encalm Spa (T3 Dom)",
    # Hyderabad
    "Meet and Greet":                          "Atithya",
    "GAT":                                     "GAT",
    "Airport Lodge":                           "Airport Lodge",
    "Buggy Service (Hyd)":                     "Buggy",
    "Buggy Service (Hyderabad)":               "Buggy",
    "Buggy Service":                           "Buggy",
    "Porter (Hyderabad)":                      "Porter",
    "Baggage Wrapping (Hyd)":                  "Baggage Wrapping",
    "Domestic Lounge (HYD)":                   "Domestic Lounge",
    "International Lounge (HYD)":             "International Lounge",
    # Goa
    "CIP Lounge":                              "CIP Lounge",
    "Ceremonial(Del)  /  GA (Hyd)  /  CIP(Goa)": "CIP Lounge",
    "Porter (Goa)":                            "Porter",
    "Porter Services- T1":                    "Porter",
    "Domestic Lounge (GOA)":                   "Domestic Lounge",
    "International Lounge (GOA)":             "International Lounge",
}

# Location-specific display name overrides (takes precedence over OUTLET_DISPLAY_NAMES)
LOCATION_DISPLAY_OVERRIDES: dict[str, dict[str, str]] = {
    "Hyderabad": {
        # ── Atithya group ───────────────────────────────────────────────────
        "Meet & Greet":                          "Atithya",
        "Welcome & Assist":                      "Atithya",
        "Meet and Greet":                        "Atithya",
        "Meet & Greet (Hyderabad)":              "Atithya",
        "M&G":                                   "Atithya",
        "M&G Hyd":                               "Atithya",
        "GAT":                                   "Atithya",
        "GAT (Hyderabad)":                       "Atithya",
        "Airport Lodge":                         "Atithya",
        "Airport Lodge (Hyderabad)":             "Atithya",
        "Ceremonial(Del)  /  GA (Hyd)  /  CIP(Goa)": "Atithya",
        "Transit Hotel":                         "Atithya",
        "Transit Lounge":                        "Atithya",
        # ── Domestic Lounge group ───────────────────────────────────────────
        "Domestic Lounge":                       "Domestic Lounge",
        "Domestic Lounge (Hyderabad)":           "Domestic Lounge",
        "Domestic Lounge (New)":                 "Domestic Lounge",
        "Domestic Lounge T3":                    "Domestic Lounge",
        "Domestic Lounge (DEL DLO2/3/4, HYD)":  "Domestic Lounge",
        "Domestic Bar - DLO2/3/4, Hyd & Goa":   "Domestic Lounge",
        "Hyd Dom Lounge":                        "Domestic Lounge",
        "HYD DOM Prive":                         "Domestic Lounge",
        "RL Domestic Arrival D":                 "Domestic Lounge",
        "RL Dom Dep E":                          "Domestic Lounge",
        "RL Dom Dep F":                          "Domestic Lounge",
        # ── International Lounge group ──────────────────────────────────────
        "International Lounge":                  "International Lounge",
        "International Lounge (Hyderabad)":      "International Lounge",
        "International Lounge (New)":            "International Lounge",
        "International Lounge (DEL INL5&6; HYD & GOA)": "International Lounge",
        "International Bar - INL5&6, Hyd & Goa": "International Lounge",
        "Hyd Intl Lounge":                       "International Lounge",
        "Hyd Intl Lounge - Closing":             "International Lounge",
        "INT Card Lounge":                       "International Lounge",
        "INT Card Lounge - new (Level E) - Upcoming": "International Lounge",
        "Hyd GA Lounge":                         "International Lounge",
        "RL Int Arrival D":                      "International Lounge",
        # ── Encalm Prive group ──────────────────────────────────────────────
        "Prive":                                 "Encalm Prive",
        "Dom Prive":                             "Encalm Prive",
        "Prive (Hyderabad)":                     "Encalm Prive",
        "Encalm Prive":                          "Encalm Prive",
        "INT Prive - Mezzanine level":           "Encalm Prive",
        "International Lounge - Premium":        "Encalm Prive",
        "Premium Lounge":                        "Encalm Prive",
        "International Bar -  Premium Lounge":   "Encalm Prive",
        "SPA - Premium Lounge":                  "Encalm Prive",
        # ── Reserved Lounge ─────────────────────────────────────────────────
        "Reserved Lounge":                       "Reserved Lounge",
        # ── Baggage Wrapping group ──────────────────────────────────────────
        "Baggage Wrapping":                      "Baggage Wrapping",
        "Baggage Wrapping (Hyd)":                "Baggage Wrapping",
        "Baggage Wrapping (Hyderabad)":          "Baggage Wrapping",
        "Enwrap Services":                       "Baggage Wrapping",
        "Enwrap":                                "Baggage Wrapping",
        # ── Porter group ────────────────────────────────────────────────────
        "Porter":                                "Porter",
        "Porter (Hyderabad)":                    "Porter",
        # ── Sky Plates group ────────────────────────────────────────────────
        "Encalm Sky Plates":                     "Sky Plates",
        "Sky Plates":                            "Sky Plates",
        "Encalm Sky Plates (Hyderabad)":         "Sky Plates",
        "Sky Plates (Hyderabad)":                "Sky Plates",
        "Sky Plates Hyd":                        "Sky Plates",
        # ── Prevent Delhi display names bleeding into HYD context ────────────
        "Encalm Lounge (T3 DL023 &4)":          "Domestic Lounge",
        "Encalm Lounge (T3 INT)":               "International Lounge",
        "Encalm Prive (T1)":                    "Encalm Prive",
    },
    "Goa": {
        # ── Atithya group ───────────────────────────────────────────────────
        "Meet & Greet":                    "Atithya",
        "Welcome & Assist":                "Atithya",
        "Meet & Greet (Goa)":              "Atithya",
        "M&G Goa":                         "Atithya",
        "M&G":                             "Atithya",
        "Ceremonial(Del)  /  GA (Hyd)  /  CIP(Goa)": "Atithya",
        "CIP Lounge":                      "Atithya",
        # ── Porter group ────────────────────────────────────────────────────
        "Porter":                          "Porter",
        "Porter (Goa)":                    "Porter",
        "Porter Services- T1":             "Porter",
        # ── Domestic Lounge group ───────────────────────────────────────────
        "Domestic Lounge":                 "Domestic Lounge",
        "Domestic Lounge (Goa)":           "Domestic Lounge",
        "Goa Lounge Dom":                  "Domestic Lounge",
        "RL Dom Departure":                "Domestic Lounge",
        "RL Dom Arrival":                  "Domestic Lounge",
        "Domestic Lounge T3":              "Domestic Lounge",
        "Domestic Lounge (DEL DLO2/3/4, HYD)": "Domestic Lounge",
        "Domestic Bar - DLO2/3/4, Hyd & Goa":  "Domestic Lounge",
        # ── International Lounge group ──────────────────────────────────────
        "International Lounge":            "International Lounge",
        "International Lounge (Goa)":      "International Lounge",
        "Goa Lounge INTL":                 "International Lounge",
        "Reserve Lounges":                 "International Lounge",
        "Reserved Lounge":                 "International Lounge",
        "RL Int Arrival":                  "International Lounge",
        "Prive (Goa)":                     "International Lounge",
        "International Lounge (DEL INL5&6; HYD & GOA)": "International Lounge",
        "International Bar - INL5&6, Hyd & Goa":        "International Lounge",
        # ── Baggage Wrapping group ──────────────────────────────────────────
        "Baggage Wrapping":                "Baggage Wrapping",
        "Baggage Wrapping (Goa)":          "Baggage Wrapping",
        "Enwrap Services":                 "Baggage Wrapping",
        "Enwrap":                          "Baggage Wrapping",
        # ── Prevent Delhi display names bleeding into Goa context ───────────
        "Encalm Lounge (T3 DL023 &4)":    "Domestic Lounge",
        "Encalm Lounge (T3 INT)":          "International Lounge",
    },
}

# ---------------------------------------------------------------------------
# Delhi groups — EXACT Excel row order
# ---------------------------------------------------------------------------
DELHI_GROUPS: dict[str, list[str]] = {
    # Each group = one individual outlet row in the MIS table.
    # Raw DB name variants listed so _cur()/_cmp() fallback chain finds revenue.
    # ── T1 ─────────────────────────────────────────────────────────────────
    "T1D (Lounges)": [
        "T1D Lounge", "T1D L4&5 Lounge", "T1D Lounge-1 Node L4&5 Card",
        "Domestic Lounge - T1 L4&5", "Regular Lounge",
        "Domestic Bar - T1 L5", "Domestic Bar - T1 L4", "Domestic Bar - T1",
    ],
    "Encalm Prive (T1)": [
        "T1D new premium lounge 2 (level 5)", "Domestic Lounge - T1 Prive", "Dom Prive",
    ],
    "Amex Lounge T1": [
        "T1D new Amex Lounge (level 4)", "Centurion Lounge T1", "DomesticLounge- Centurion Amex T1",
    ],
    # ── T2 ─────────────────────────────────────────────────────────────────
    "T2 (Lounges)": [
        "T2 Domestic", "T2 Lounge", "Domestic Lounge - T2",
    ],
    # ── T3 Domestic ────────────────────────────────────────────────────────
    "T3 Domestic DL02/3/4": [
        "T3 DLO2/03/04", "T3 DL023 &4", "T3 DL02/03/04", "Lounge DL 02,03,04",
        "Lounge DL 02&03", "Domestic Lounge T3", "Domestic Lounge (DEL DLO2/3/4, HYD)",
    ],
    "T3 D49": [
        "T3 D49", "Domestic Lounge - D49",
    ],
    "T3 Air India Dom": [
        "Domestic AI Lounge Del", "Air India", "Domestic Lounge - Air India",
    ],
    "Lounge Rupay": [
        "Rupay", "Lounge - Rupay", "Domestic Lounge - Rupay",
    ],
    "Lounge Amex Centurion": [
        "Lounge - Amex Centurion", "Centurion Lounge", "Centurion Lounge T3",
        "DomesticLounge- Centurion Amex T3",
    ],
    # ── T3 International ───────────────────────────────────────────────────
    "T3 International": [
        "INL 5&6", "T3 INL 5&6", "International Lounge",
        "International Lounge (DEL INL5&6; HYD & GOA)",
    ],
    "Encalm Prive T3": [
        "Premium Lounge", "T3 Premium", "International Lounge - Premium",
    ],
    "Encalm Xenia": [
        "Xenia", "First Class - Xenia Lounge", "Xenia - INL T3",
    ],
    "AI International": [
        "AI International Lounge", "International Lounge - Air India",
    ],
    "Reserved Lounge": [
        "Reserved Lounge", "Reserve Lounges", "Reserved Lounges",
    ],
    # ── T3 Arrivals ────────────────────────────────────────────────────────
    "T3 Arrivals LA22": [
        "Arrival Lounge LA 22", "Arrival Lounge - LA22", "LA 22",
    ],
    "T3 Nap LA01": [
        "Nap & Shower LA01", "Transit Lounge - LA01", "NAP - Premium Lounge",
    ],
    "T3 Nap LA12": [
        "Nap & Shower LA12", "Transit Lounge - LA12", "Sleeping Pod - Premium Lounge",
    ],
    # ── Atithya / Ancillary ────────────────────────────────────────────────
    "Enwrap": [
        "Baggage Wrapping", "Enwrap Services",
    ],
    "Atithya (Porter)": [
        "Porter", "Porter Services- T1", "Porter Services -T2", "Porter Services -T3",
    ],
    "Atithya (Buggy)": [
        "Buggy Service", "Buggy Services", "Buggy Del",
    ],
    "Atithya (M&G)": [
        "Meet & Greet", "Welcome & Assist", "CIP Lounge", "Special Events",
        "GAT", "Ceremonial(Del) / GA (Hyd) / CIP(Goa)", "Atithya",
    ],
    # ── Spa ────────────────────────────────────────────────────────────────
    "Spa T3 INT": [
        "INTL Spa", "Spa - International", "International Spa- INL07 T3",
        "SPA - Premium Lounge",
    ],
    "Spa T3 Dom": [
        "Domestic Spa - T3", "Domestic Spa- DPA10 T3", "SPA Domestic", "Dom Spa",
    ],
    "Spa T1": [
        "T1D SPA", "Domestic Spa - T1", "Domestic Spa- T1",
    ],
    # ── Bar outlets (revenue-only, no PAX) ────────────────────────────────
    "Bar T3 Dom": [
        "Domestic Bar - DLO2/3/4, Hyd & Goa", "Domestic Bar - DLO2/3/4",
    ],
    "Bar T3 INT": [
        "International Bar - INL5&6, Hyd & Goa", "International Bar - INL5&6",
    ],
    "Bar T3 Prive": [
        "International Bar -  Premium Lounge", "International Bar - Premium Lounge",
    ],
    "Bar T2": ["Domestic Bar - T2"],
    "Bar T1": ["Domestic Bar - T1 L5", "Domestic Bar - T1"],
    "Bar D49": ["Domestic Bar - D49"],
    "Bar Rupay": ["Domestic Bar - Rupay"],
    # ── Others ─────────────────────────────────────────────────────────────
    "Airport Lodge": [
        "Airport Lodge", "Airport Lodge (Delhi)",
    ],
    "Business Centre": [
        "Business Centre", "Business Center",
    ],
    "RDC": [
        "Round D Clock (RDC)", "Round D Clock -Motel",
        "Round D Clock (RDC)-Restaurant", "RDC",
    ],
    # ── Subsidiaries (excluded from EHPL page) ─────────────────────────────
    "Encalm Eats (Delhi)": ["Encalm Eats"],
    "Sky Plates (Delhi)":  ["Encalm Sky Plates"],
}

DELHI_SUBTOTALS: list[tuple[str, list[str]]] = [
    ("Total T1",                  ["T1D (Lounges)", "Encalm Prive (T1)", "Amex Lounge T1"]),
    ("Total T2",                  ["T2 (Lounges)"]),
    ("Total(T1+T2)",              ["T1D (Lounges)", "Encalm Prive (T1)", "Amex Lounge T1", "T2 (Lounges)"]),
    ("Total (T3 Domestic)",       ["T3 Domestic DL02/3/4", "T3 D49", "T3 Air India Dom",
                                   "Lounge Rupay", "Lounge Amex Centurion"]),
    ("T1 + T2 + T3 Dom",         ["T1D (Lounges)", "Encalm Prive (T1)", "Amex Lounge T1",
                                   "T2 (Lounges)", "T3 Domestic DL02/3/4", "T3 D49",
                                   "T3 Air India Dom", "Lounge Rupay", "Lounge Amex Centurion"]),
    ("Total (T3 International)",  ["T3 International", "Encalm Prive T3", "Encalm Xenia", "AI International"]),
    ("Total Arrivals",            ["T3 Arrivals LA22", "T3 Nap LA01", "T3 Nap LA12"]),
    ("Atithya (M&G, Porter, Buggy)", ["Atithya (M&G)", "Atithya (Porter)", "Atithya (Buggy)"]),
    ("TOTAL EHPL",                ["T1D (Lounges)", "Encalm Prive (T1)", "Amex Lounge T1",
                                   "T2 (Lounges)", "T3 Domestic DL02/3/4", "T3 D49",
                                   "T3 Air India Dom", "Lounge Rupay", "Lounge Amex Centurion",
                                   "T3 International", "Encalm Prive T3", "Encalm Xenia",
                                   "AI International", "T3 Arrivals LA22", "T3 Nap LA01",
                                   "T3 Nap LA12", "Enwrap", "Atithya (M&G)", "Atithya (Porter)",
                                   "Atithya (Buggy)", "Spa T3 INT", "Spa T3 Dom", "Spa T1"]),
]

DELHI_ROW_ORDER: list[str] = [
    "T1D (Lounges)",
    "Encalm Prive (T1)",
    "Amex Lounge T1",
    "Total T1",
    "T2 (Lounges)",
    "Total T2",
    "Total(T1+T2)",
    "T3 Domestic DL02/3/4",
    "T3 D49",
    "T3 Air India Dom",
    "Lounge Rupay",
    "Lounge Amex Centurion",
    "Total (T3 Domestic)",
    "T1 + T2 + T3 Dom",
    "T3 International",
    "Encalm Prive T3",
    "Encalm Xenia",
    "AI International",
    "Total (T3 International)",
    "T3 Arrivals LA22",
    "Reserved Lounge",
    "T3 Nap LA01",
    "T3 Nap LA12",
    "Total Arrivals",
    "Enwrap",
    "Atithya (Porter)",
    "Atithya (Buggy)",
    "Atithya (M&G)",
    "Atithya (M&G, Porter, Buggy)",
    "Spa T3 INT",
    "Spa T3 Dom",
    "Spa T1",
    # Bar outlets
    "Bar T3 Dom",
    "Bar T3 INT",
    "Bar T3 Prive",
    "Bar T2",
    "Bar T1",
    "Bar D49",
    "Bar Rupay",
    # Others
    "Airport Lodge",
    "Business Centre",
    "RDC",
    # Subsidiaries (excluded from EHPL page display but needed for calculation)
    "Encalm Eats (Delhi)",
    "Sky Plates (Delhi)",
    "TOTAL EHPL",
]

# ---------------------------------------------------------------------------
# Hyderabad groups — exact Excel row order
# ---------------------------------------------------------------------------
HYD_GROUPS: dict[str, list[str]] = {
    "Atithya": [
        "Atithya", "Meet & Greet", "Welcome & Assist", "Meet and Greet",
        "Meet & Greet (Hyderabad)", "M&G", "M&G Hyd",
        "GAT", "GAT (Hyderabad)", "Airport Lodge", "Airport Lodge (Hyderabad)",
        "Ceremonial(Del)  /  GA (Hyd)  /  CIP(Goa)",
        "Transit Hotel", "Transit Lounge",
    ],
    "Domestic Lounge": [
        "Domestic Lounge (DEL DLO2/3/4, HYD)", "Domestic Lounge",
        "Domestic Lounge T3", "Domestic Bar - DLO2/3/4, Hyd & Goa",
        "Domestic Lounge (New)", "Domestic Lounge (Hyderabad)", "Hyd Dom Lounge",
        "HYD DOM Prive", "RL Domestic Arrival D", "RL Dom Dep E", "RL Dom Dep F",
    ],
    "International Lounge": [
        "International Lounge (DEL INL5&6; HYD & GOA)", "International Lounge",
        "International Lounge (Hyderabad)",
        "International Bar - INL5&6, Hyd & Goa",
        "International Lounge (New)", "Hyd Intl Lounge",
        "Hyd Intl Lounge - Closing", "INT Card Lounge",
        "INT Card Lounge - new (Level E) - Upcoming",
        "Hyd GA Lounge", "RL Int Arrival D",
        "Reserved Lounge",
    ],
    "Encalm Prive": [
        "International Lounge - Premium", "Premium Lounge",
        "International Bar -  Premium Lounge",
        "SPA - Premium Lounge",
        "Dom Prive", "Prive", "Prive (Hyderabad)", "Encalm Prive",
        "INT Prive - Mezzanine level",
    ],
    "Baggage Wrapping": [
        "Baggage Wrapping", "Enwrap Services",
        "Baggage Wrapping (Hyderabad)", "Baggage Wrapping (Hyd)", "Enwrap",
    ],
    "Porter": [
        "Porter", "Porter (Hyderabad)",
    ],
    "Sky Plates": [
        "Encalm Sky Plates", "Sky Plates",
        "Encalm Sky Plates (Hyderabad)", "Sky Plates (Hyderabad)", "Sky Plates Hyd",
    ],
}

HYD_SUBTOTALS: list[tuple[str, list[str]]] = [
    ("Total (International + Prive)", ["International Lounge", "Encalm Prive"]),
    ("TOTAL", ["Atithya", "Domestic Lounge", "International Lounge",
               "Encalm Prive", "Baggage Wrapping", "Porter", "Sky Plates"]),
]

HYD_ROW_ORDER: list[str] = [
    "Atithya",
    "Domestic Lounge",
    "International Lounge",
    "Encalm Prive",
    "Total (International + Prive)",
    "Baggage Wrapping",
    "Porter",
    "Sky Plates",
    "TOTAL",
]

# ---------------------------------------------------------------------------
# Goa groups — exact Excel row order
# ---------------------------------------------------------------------------
GOA_GROUPS: dict[str, list[str]] = {
    "Atithya": [
        "Atithya", "Meet & Greet", "Welcome & Assist", "Meet & Greet (Goa)", "M&G", "M&G Goa",
        "Ceremonial(Del)  /  GA (Hyd)  /  CIP(Goa)", "CIP Lounge",
    ],
    "Porter": [
        "Porter", "Porter (Goa)", "Porter Services- T1",
    ],
    "Domestic Lounge": [
        "Domestic Lounge (DEL DLO2/3/4, HYD)", "Domestic Lounge",
        "Domestic Lounge (Goa)", "Domestic Lounge T3",
        "Domestic Bar - DLO2/3/4, Hyd & Goa",
        "Goa Lounge Dom", "RL Dom Departure", "RL Dom Arrival",
    ],
    "International Lounge": [
        "International Lounge (DEL INL5&6; HYD & GOA)", "International Lounge",
        "International Lounge (Goa)",
        "International Bar - INL5&6, Hyd & Goa", "Reserve Lounges",
        "Reserved Lounge", "CIP Lounge", "Prive (Goa)",
        "Goa Lounge INTL", "RL Int Arrival",
    ],
    "Baggage Wrapping": [
        "Baggage Wrapping", "Enwrap Services",
        "Baggage Wrapping (Goa)", "Enwrap",
    ],
}

GOA_SUBTOTALS: list[tuple[str, list[str]]] = [
    ("Total (Atithya + Porter)", ["Atithya", "Porter"]),
    ("Total", ["Atithya", "Porter", "Domestic Lounge",
               "International Lounge", "Baggage Wrapping"]),
]

GOA_ROW_ORDER: list[str] = [
    "Atithya",
    "Porter",
    "Total (Atithya + Porter)",
    "Domestic Lounge",
    "International Lounge",
    "Baggage Wrapping",
    "Total",
]


# ---------------------------------------------------------------------------
# Bhogapuram — only the outlets actually present at Bhogapuram airport
# ---------------------------------------------------------------------------

BHOGAPURAM_GROUPS: dict[str, list[str]] = {
    "Domestic Lounge": [
        "Domestic Lounge", "Domestic Lounge T3",
    ],
    "International Lounge": [
        "International Lounge",
    ],
    "Atithya": [
        "Atithya", "Meet & Greet", "Welcome & Assist",
    ],
    "Porter": [
        "Porter",
    ],
    "Baggage Wrapping": [
        "Baggage Wrapping", "Enwrap",
    ],
}

BHOGAPURAM_SUBTOTALS: list[tuple] = [
    ("TOTAL EHPL", ["Domestic Lounge", "International Lounge",
                    "Atithya", "Porter", "Baggage Wrapping"]),
]

BHOGAPURAM_ROW_ORDER: list[str] = [
    "Atithya",
    "Porter",
    "Domestic Lounge",
    "International Lounge",
    "Baggage Wrapping",
    "TOTAL EHPL",
]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_display_name(outlet: str, location: str = "") -> str:
    """Return the UI display name for a raw outlet name, location-aware."""
    if location and location in LOCATION_DISPLAY_OVERRIDES:
        loc_overrides = LOCATION_DISPLAY_OVERRIDES[location]
        if outlet in loc_overrides:
            return loc_overrides[outlet]
    return OUTLET_DISPLAY_NAMES.get(outlet, outlet)


def get_outlet_group(outlet: str, groups: dict[str, list[str]]) -> str | None:
    """Return the group key for an outlet, or None if unmatched."""
    for group, outlets in groups.items():
        if outlet in outlets:
            return group
    return None
