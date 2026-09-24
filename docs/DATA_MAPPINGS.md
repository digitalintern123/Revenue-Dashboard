# DATA_MAPPINGS.md
# Encalm Revenue Analytics — Data Mappings

---

## 1. Outlet Name Canonicalization

**Function:** `canonicalize_outlet_name(outlet: str) -> str`
**File:** `database.py:590`
**Applied:** At save time in `save_dataframe()`. Pages always see canonical names.

### Key Mappings (sample — full list in database.py:553)

| Raw name in source file | Canonical name stored in DB |
|---|---|
| `INL 5&6` | `International Lounge` |
| `T3 INL 5&6` | `International Lounge` |
| `Regular Lounge` | `Domestic Lounge - T1 L4&5` |
| `T1D Lounge` | `Domestic Lounge - T1 L4&5` |
| `T2 Domestic` | `Domestic Lounge - T2` |
| `T3 DLO2/03/04` | `T3 DLO2/03/04` (unchanged) |
| `Lounge DL 02,03,04` | `Domestic Lounge T3` |
| `T3 D49` | `Domestic Lounge - D49` |
| `Air India` | `Domestic Lounge - Air India` |
| `Rupay` | `Domestic Lounge - Rupay` |
| `Centurion Lounge T3` | `Centurion Lounge T3` |
| `Dom Prive` | `Domestic Lounge - T1 Prive` |
| `Baggage Wrapping` | `Baggage Wrapping` (unchanged) |
| `Meet & Greet` | `Meet & Greet` (unchanged) |
| `Buggy Service` | `Buggy Service` |
| `Xenia` | `Xenia` |
| `INTL Spa` | `INTL Spa` |
| `SPA Domestic` | `Domestic Spa - T1` |
| `T1D SPA` | `Domestic Spa - T1` |
| `SPA - Premium Lounge` | `Spa - International` |

---

## 2. Delhi MIS Row Structure (Page 8)

**File:** `outlet_groups.py` — `DELHI_GROUPS`, `DELHI_SUBTOTALS`, `DELHI_ROW_ORDER`

### Complete Row Map

| Row # | Display Name | Group Key | Raw DB Variants | Terminal |
|---|---|---|---|---|
| 1 | Encalm Lounge (T1 D) | `T1D (Lounges)` | T1D Lounge, T1D L4&5 Lounge, T1D Lounge-1 Node L4&5 Card, Domestic Lounge - T1 L4&5, Regular Lounge | T1 Dep |
| 2 | Encalm Prive (T1) | `Encalm Prive (T1)` | T1D new premium lounge 2 (level 5), Domestic Lounge - T1 Prive, Dom Prive | T1 Dep |
| 3 | Amex Lounge T1 | `Amex Lounge T1` | T1D new Amex Lounge (level 4), Centurion Lounge T1, DomesticLounge- Centurion Amex T1 | T1 Dep |
| 4 | Encalm Lounge (T2 D) | `T2 (Lounges)` | T2 Domestic, T2 Lounge, Domestic Lounge - T2, Domestic Bar - T2 | T2 Dep |
| **5** | **▶ Total(T1+T2)** | SUBTOTAL | T1D(Lounges)+Prive T1+Amex T1+T2(Lounges) | — |
| 6 | Encalm Lounge (T3 DL023 &4) | `T3 Domestic DL02/3/4` | T3 DLO2/03/04, T3 DL023 &4, T3 DL02/03/04, Lounge DL 02,03,04, Lounge DL 02&03, Domestic Lounge T3, Domestic Lounge (DEL DLO2/3/4, HYD), Domestic Bar - DLO2/3/4 | T3 Dom Dep |
| 7 | Encalm Lounge (T3 –D 49) | `T3 D49` | T3 D49, Domestic Lounge - D49, Domestic Bar - D49 | T3 Dom Dep |
| 8 | Air India Lounge (T3 Dom) | `T3 Air India Dom` | Domestic AI Lounge Del, Air India, Domestic Lounge - Air India | T3 Dom Dep |
| 9 | Lounge Rupay | `Lounge Rupay` | Rupay, Lounge - Rupay, Domestic Lounge - Rupay, Domestic Bar - Rupay | T3 Dom Dep |
| 10 | Lounge Amex Centurion | `Lounge Amex Centurion` | Lounge - Amex Centurion, Centurion Lounge, Centurion Lounge T3, DomesticLounge- Centurion Amex T3 | T3 Dom Dep |
| **11** | **▶ Total (T3 Domestic)** | SUBTOTAL | rows 6-10 | — |
| **12** | **▶ T1 + T2 + T3 Dom** | SUBTOTAL | rows 1-10 | — |
| 13 | Encalm Lounge (T3 INT) | `T3 International` | INL 5&6, T3 INL 5&6, International Lounge, International Lounge (DEL INL5&6; HYD & GOA), International Bar - INL5&6 Hyd & Goa | T3 Int Dep |
| 14 | Encalm Prive (T3) | `Encalm Prive T3` | Premium Lounge, T3 Premium, International Lounge - Premium, International Bar - Premium Lounge | T3 Int Dep |
| 15 | Encalm Xenia | `Encalm Xenia` | Xenia, First Class - Xenia Lounge, Xenia - INL T3 | T3 Int Dep |
| 16 | AI International | `AI International` | AI International Lounge, International Lounge - Air India | T3 Int Dep |
| **17** | **▶ Total (T3 International)** | SUBTOTAL | rows 13-16 | — |
| 18 | Arrival Lounge- ( T3 LA22) | `T3 Arrivals LA22` | Arrival Lounge LA 22, Arrival Lounge - LA22, LA 22, Reserved Lounge | T3 Arr |
| 19 | Nap Rooms LA01 | `T3 Nap LA01` | Nap & Shower LA01, Transit Lounge - LA01, NAP - Premium Lounge | T3 Arr |
| 20 | Nap Rooms LA12 | `T3 Nap LA12` | Nap & Shower LA12, Transit Lounge - LA12, Sleeping Pod - Premium Lounge | T3 Arr |
| **21** | **▶ Total Arrivals** | SUBTOTAL | rows 18-20 | — |
| 22 | Enwrap | `Enwrap` | Baggage Wrapping, Enwrap Services | All Dep |
| 23 | Porter | `Atithya (Porter)` | Porter, Porter Services- T1, Porter Services -T2, Porter Services -T3 | Porter Pool |
| 24 | Buggy | `Atithya (Buggy)` | Buggy Service, Buggy Services, Buggy Del | T3 Total |
| 25 | Atithya | `Atithya (M&G)` | Meet & Greet, Welcome & Assist, CIP Lounge, Special Events | All |
| **26** | **▶ Atithya (M&G, Porter, Buggy)** | SUBTOTAL | rows 22-25 | — |
| 27 | Encalm Spa (T3 INT) | `Spa T3 INT` | INTL Spa, Spa - International, International Spa- INL07 T3, SPA - Premium Lounge | T3 Int Dep |
| 28 | Encalm Spa (T3 Dom) | `Spa T3 Dom` | Domestic Spa - T3, Domestic Spa- DPA10 T3, SPA Domestic, Dom Spa | T3 Int Dep |
| 29 | Encalm Spa (T1 Dom) | `Spa T1` | T1D SPA, Domestic Spa - T1, Domestic Spa- T1 | T1 Dep |
| **30** | **▶ TOTAL EHPL** | SUBTOTAL | all EHPL groups | All |

---

## 3. Hyderabad MIS Row Structure

**File:** `outlet_groups.py` — `HYD_GROUPS`, `HYD_SUBTOTALS`, `HYD_ROW_ORDER`

| Row # | Display Name | Group Key | Raw DB Variants | Terminal |
|---|---|---|---|---|
| 1 | Atithya | `Atithya` | Meet & Greet, Welcome & Assist, Meet and Greet, Meet & Greet (Hyderabad), M&G, M&G Hyd, GAT, GAT (Hyderabad), Airport Lodge, Airport Lodge (Hyderabad), Ceremonial(Del)/GA(Hyd)/CIP(Goa), Transit Hotel, Transit Lounge | All |
| 2 | Domestic Lounge | `Domestic Lounge` | Domestic Lounge (DEL DLO2/3/4, HYD), Domestic Lounge, Domestic Lounge T3, Domestic Bar - DLO2/3/4 Hyd & Goa, Domestic Lounge (New), Domestic Lounge (Hyderabad), Hyd Dom Lounge, HYD DOM Prive, RL Domestic Arrival D, RL Dom Dep E, RL Dom Dep F | Domestic |
| 3 | International Lounge | `International Lounge` | International Lounge (DEL INL5&6; HYD & GOA), International Lounge, International Lounge (Hyderabad), International Bar - INL5&6 Hyd & Goa, International Lounge (New), Hyd Intl Lounge, Hyd Intl Lounge - Closing, INT Card Lounge, INT Card Lounge - new (Level E) - Upcoming, Hyd GA Lounge, RL Int Arrival D, Reserved Lounge | International |
| 4 | Encalm Prive | `Encalm Prive` | International Lounge - Premium, Premium Lounge, International Bar - Premium Lounge, SPA - Premium Lounge, Dom Prive, Prive, Prive (Hyderabad), Encalm Prive, INT Prive - Mezzanine level | International |
| **5** | **▶ Total (International + Prive)** | SUBTOTAL | International Lounge + Encalm Prive | — |
| 6 | Baggage Wrapping | `Baggage Wrapping` | Baggage Wrapping, Enwrap Services, Baggage Wrapping (Hyderabad), Baggage Wrapping (Hyd), Enwrap | All |
| 7 | Porter | `Porter` | Porter, Porter (Hyderabad) | All |
| 8 | Sky Plates | `Sky Plates` | Encalm Sky Plates, Sky Plates, Encalm Sky Plates (Hyderabad), Sky Plates (Hyderabad), Sky Plates Hyd | — |
| **9** | **▶ TOTAL** | SUBTOTAL | Atithya + Domestic + International + Prive + Baggage Wrapping + Porter | — |

---

## 4. Goa MIS Row Structure

**File:** `outlet_groups.py` — `GOA_GROUPS`, `GOA_SUBTOTALS`, `GOA_ROW_ORDER`

| Row # | Display Name | Group Key | Raw DB Variants | Terminal |
|---|---|---|---|---|
| 1 | Atithya | `Atithya` | Meet & Greet, Welcome & Assist, Meet & Greet (Goa), M&G, M&G Goa, Ceremonial(Del)/GA(Hyd)/CIP(Goa), CIP Lounge | All |
| 2 | Porter | `Porter` | Porter, Porter (Goa), Porter Services- T1 | All |
| **3** | **▶ Total (Atithya + Porter)** | SUBTOTAL | Atithya + Porter | — |
| 4 | Domestic Lounge | `Domestic Lounge` | Domestic Lounge (DEL DLO2/3/4, HYD), Domestic Lounge, Domestic Lounge (Goa), Domestic Lounge T3, Domestic Bar - DLO2/3/4 Hyd & Goa, Goa Lounge Dom, RL Dom Departure, RL Dom Arrival | Domestic |
| 5 | International Lounge | `International Lounge` | International Lounge (DEL INL5&6; HYD & GOA), International Lounge, International Lounge (Goa), International Bar - INL5&6 Hyd & Goa, Reserve Lounges, Reserved Lounge, CIP Lounge, Prive (Goa), Goa Lounge INTL, RL Int Arrival | International |
| 6 | Baggage Wrapping | `Baggage Wrapping` | Baggage Wrapping, Enwrap Services, Baggage Wrapping (Goa), Enwrap | All |
| **7** | **▶ Total** | SUBTOTAL | Atithya + Porter + Domestic + International + Baggage Wrapping | — |

---

## 5. Terminal Pool → Composite Sentinel Resolution

**Function:** `database.join_revenue_with_traffic_by_outlet()` — `database.py:1847`

The `airport_traffic` table stores physical terminal labels. Page 8 and traffic calculations need composite totals. Resolution happens inside `_get_traffic()` nested function:

| Sentinel | Resolved as | Outlets that use it |
|---|---|---|
| `T3 Arr` | T3 Dom Arr + T3 Int Arr | LA22, LA01, LA12, RL Delhi |
| `All Dep` | T1 Dep + T2 Dep + T3 Dom Dep + T3 Int Dep | Enwrap |
| `All` | All 8 terminal pools | Atithya/M&G, HYD Atithya, GOA Atithya |
| `T3 Total` | T3 Dom Dep + T3 Int Dep + T3 Dom Arr + T3 Int Arr | Buggy |
| `Porter Pool` | T1 Dep + T1 Arr + T2 Dep + T2 Arr + T3 Dom Dep + T3 Int Dep | Porter |
| `T3 Dom+Int Dep` | T3 Dom Dep + T3 Int Dep | RL T3 Departure |
| `Main Terminal` | Dom + Int + Main Terminal | HYD/GOA fallback |

---

## 6. Display Name Lookup Chain (Page 8)

`get_display_name(outlet, location)` in `outlet_groups.py:443`

```
1. Check LOCATION_DISPLAY_OVERRIDES[location][outlet]  ← location-specific overrides
2. Check OUTLET_DISPLAY_NAMES[outlet]                  ← global display names (124 entries)
3. Return outlet unchanged                             ← no override found
```

**Location-specific overrides** (`LOCATION_DISPLAY_OVERRIDES`):
- Hyderabad: `"International Lounge"` → `"International Lounge"` (prevent Delhi T3 INT override)
- Hyderabad: `"Baggage Wrapping"` → `"Baggage Wrapping"` (not "Enwrap")
- Goa: same as Hyderabad

---

## 7. Revenue Fallback Chain (Page 8 `_cur()` / `_cmp()`)

When looking up revenue for an outlet group in `_build_location_report()`:

```python
def _cur(outlet):
    rows = cur_agg[cur_agg["outlet"] == outlet]      # 1. Try raw group name
    if not rows.empty: return rows
    canon = _co(outlet)                               # 2. Try canonical name
    rows = cur_agg[cur_agg["outlet"] == canon]
    if not rows.empty: return rows
    disp = _gdn(outlet, location)                     # 3. Try display name
    rows = cur_agg[cur_agg["outlet"] == disp]
    return rows
```

This is needed because `DELHI_GROUPS` uses raw/input names as group keys, but `revenue_master` stores canonical names. The chain ensures revenue is always found regardless of which name variant was stored.

---

## 8. Traffic Fallback Chain (Page 8)

```python
traf_c = (
    _traf_cur_lookup.get(outlet) or           # 1. raw name
    _traf_cur_lookup.get(_co(outlet)) or      # 2. canonical
    _traf_cur_lookup.get(_gdn(outlet, loc))   # 3. display name
)
```

`_traf_cur_lookup` is built from `join_revenue_with_traffic_by_outlet(cur_df)` which resolves all composite sentinels.

---

## 9. AOP Fallback Chain (Page 8)

```python
aop = (
    aop_map.get(outlet) or              # 1. raw name
    aop_map.get(_co(outlet)) or         # 2. canonical
    aop_map.get(_gdn(outlet, location)) # 3. display name
)
```

`aop_map` is built from `load_aop_targets_for_range()` directly (not `join_revenue_with_aop()`).
Outlet names in `aop_target` table are canonicalized at save time (`save_aop_targets()` applies `_co_aop`).

---

## 10. How to Add a New Outlet

Edit these files **in order**:

### Step 1 — `modules/database.py`
Add raw name → canonical name mapping in `_OUTLET_NAME_CANONICAL` dict (~line 553):
```python
"new raw name variant":  "Canonical Outlet Name",
```

### Step 2 — `modules/terminal_mapping.py`
Add canonical name → terminal pool in the appropriate location dict:
```python
# _DELHI_OUTLET_TO_TERMINAL (line ~83)
"Canonical Outlet Name":  "T3 Int Dep",   # use the correct terminal constant
```
Also add raw variants if they might appear in traffic lookups.

### Step 3 — `modules/outlet_groups.py`
Add display name in `OUTLET_DISPLAY_NAMES`:
```python
"Canonical Outlet Name":  "Display Name for MIS Table",
```
Add to the correct group in `DELHI_GROUPS` / `HYD_GROUPS` / `GOA_GROUPS`:
```python
"Group Key": [
    ...existing outlets...,
    "new raw name variant",
    "Canonical Outlet Name",
],
```

### Step 4 — `pages/3_Revenue_Comparison.py`
Add to `_OUTLET_MAP` (lowercase) for Tab 5 Dom/Int classification:
```python
"canonical outlet name":  "Domestic",  # or "International" or "Ancillary"
```

### Step 5 — Run tests
```bash
python -m pytest tests/ -v  # must still show 158 passed
```
