# Data Mappings — from file lines to dashboard rows

How a line in an uploaded file ends up as a stored outlet, and which row it
appears on in the app. Source of truth is the code named in each section.

---

## 1. Stored names

### Location
Title-cased (`delhi` → `Delhi`). Locations: Delhi, Hyderabad, Goa, Bhogapuram.

### Segment and business unit — `database.canonicalize_segment_and_business_unit`

| File "Business" / outlet | Stored segment | Business unit |
|---|---|---|
| Outlet *Encalm Sky Plates* / *Sky Plates* (any Business) | Sky Plates | Sky Plates |
| Outlet *Encalm Eats* (any Business) | Encalm Eats | Encalm Eats |
| Lounges / Atithya / Others | EHPL | the Business value |
| EHPL | EHPL | inferred from the outlet (`_CANONICAL_OUTLET_TO_BU`, default Lounges) |
| anything else | passed through unchanged | |

### Outlet — `database.canonicalize_outlet_name` (`_OUTLET_NAME_CANONICAL`)
Every known spelling maps to one stored name, e.g. `INL 5&6` → *International
Lounge*, `T1D Lounge` / `T1D L4&5 Lounge` / `Regular Lounge` → *Domestic Lounge -
T1 L4&5*, `Transit Lounge` → *Transit Hotel*, `Dom Prive` / `Prive` →
*Domestic Lounge - Prive*. Lines that map to the same date + outlet + location
are **added together** at save time.

---

## 2. How an EHPL table row is built

`business_dashboard._build_location_report` (then `ehpl_layout._build_table_rows`):

1. Take every outlet **present in the data** for the current or comparison
   period, plus every AOP line for the location.
2. Find its **group** (`outlet_groups.<LOC>_GROUPS`) — first an exact member
   name, then a member's canonical name, then a member's display name.
   No match → group **"Other outlets"** (shown under TOTAL OTHERS — never dropped).
3. Find its **display name** — `outlet_groups.get_display_name(outlet, location)`:
   `LOCATION_DISPLAY_OVERRIDES[location]` first, then `OUTLET_DISPLAY_NAMES`;
   an outlet with no display name of its own takes its group member's.
4. Outlets with the **same display name are added together** into one row.
5. AOP lines attach to the row holding that outlet (each AOP line once).
6. Rows in `ALWAYS_SHOW_ROWS[location]` are added even with no figures.
7. Rows with no revenue, PAX, comparison figures or AOP are hidden (except 6).
8. Section totals come from their rows; **TOTAL EHPL = all rows**, so it always
   equals the location's EHPL total in the database.
9. `ehpl_layout.<LOC>_SECTIONS` places groups in sections (LOUNGES, SPA,
   NAP & SHOWER, ATITHYA SERVICES, ENWRAP, PORTER, BAR, OTHERS); unknown groups
   go to OTHERS.

AOP for EHPL excludes Sky Plates and Encalm Eats targets.

---

## 3. Encalm Eats / Sky Plates rows

`business_dashboard._render_subsidiary_table`: one row per stored outlet.
Revenue uploads carry one *Encalm Eats* / *Encalm Sky Plates* row per location
per day; the DSR carries real outlets. `eats_skyplates_aop_parser.align_aop_to_outlets`
lines AOP up with the outlets shown (single-outlet data takes the whole
location AOP; combined AOP lines are split by revenue share). AOP for outlets
with no sales is shown as **Other planned outlets – no sales (n)**.

---

## 4. Outlet rows per location (EHPL)

Generated from the code with the Aug-2026 revenue workbook (all 68 line items,
2022–2026). Several names on one line = renamed outlets or items the
management report adds together. Rows marked "always shown" are in
`ALWAYS_SHOW_ROWS`; for Hyderabad, Goa and Bhogapuram that list is the full
outlet list agreed with the business.

### Delhi

| Section | Row in the app | Sub-Business names in the revenue file |
|---|---|---|
| LOUNGES | AI International | AI International Lounge |
| LOUNGES | Air India Lounge (T3 Dom) | Air India |
| LOUNGES | Amex Lounge T1 | T1D new Amex Lounge (level 4) |
| LOUNGES | Arrival Lounge- ( T3 LA22) | Arrival Lounge LA 22, Delhi - T3 - LA 22, LA 22 |
| LOUNGES | Encalm Lounge (T1 D) | Regular Lounge, T1D L4&5 Lounge, T1D Lounge |
| LOUNGES | Encalm Lounge (T2, D) | T2 Domestic |
| LOUNGES | Encalm Lounge (T3 DL023 &4) | Lounge DL 02&03, Lounge DL 02,03,04 |
| LOUNGES | Encalm Lounge (T3 INT) | INL 5&6 |
| LOUNGES | Encalm Lounge (T3 –D 49) | T3 D49 |
| LOUNGES | Encalm Prive (T1) | T1D new premium lounge 2 (level 5) |
| LOUNGES | Encalm Prive (T3) | Premium Lounge |
| LOUNGES | Encalm Xenia | First Class - Xenia Lounge |
| LOUNGES | Lounge Amex Centurion | Centurion Lounge |
| LOUNGES | Lounge Rupay | Rupay |
| LOUNGES | RL Delhi | Reserved Lounge, Visitor Lounge |
| SPA | Encalm Spa (T1 Dom) | T1D SPA |
| SPA | Encalm Spa (T3 Dom) | SPA Domestic |
| SPA | Encalm Spa (T3 INT) | Spa - International |
| NAP & SHOWER | Nap Rooms LA01 | Nap & Shower LA01 |
| NAP & SHOWER | Nap Rooms LA12 | LA 12, Nap & Shower LA12 |
| ATITHYA SERVICES | Atithya | Meet & Greet |
| ATITHYA SERVICES | Buggy | Buggy Service |
| ATITHYA SERVICES | CIP Lounge | CIP Lounge |
| ATITHYA SERVICES | Porter | Porter |
| ATITHYA SERVICES | Special Events | Special Events |
| ENWRAP | Enwrap | Baggage Wrapping |
| OTHERS | Bar | Bar |
| OTHERS | Business Centre | Business Center |
| OTHERS | MLCP | MLCP |
| OTHERS | Round D Clock (RDC) | Round D Clock (RDC) |

### Hyderabad

| Section | Row in the app | Sub-Business names in the revenue file |
|---|---|---|
| LOUNGES | Domestic Lounge | Domestic Lounge, Domestic Lounge (New) |
| LOUNGES | Encalm Prive | Dom Prive, Prive |
| LOUNGES | GAT | GAT |
| LOUNGES | International Lounge | International Lounge, International Lounge (New) |
| LOUNGES | Reserved Lounge | Reserved Lounge |
| ATITHYA SERVICES | Atithya | Meet & Greet |
| ENWRAP | Enwrap | Baggage Wrapping |
| OTHERS | Airport Lodge / Dormitory | Airport Lodge |
| OTHERS | Transit Hotel | Transit Hotel, Transit Lounge |

### Goa

| Section | Row in the app | Sub-Business names in the revenue file |
|---|---|---|
| LOUNGES | CIP Lounge | CIP Lounge |
| LOUNGES | Domestic Lounge | Domestic Lounge |
| LOUNGES | International Lounge | International Lounge |
| LOUNGES | Reserved Lounge | Reserved Lounge |
| ATITHYA SERVICES | Atithya | Meet & Greet |
| ENWRAP | Enwrap | Baggage Wrapping |
| PORTER | Porter | Porter |

### Bhogapuram

| Section | Row in the app | Sub-Business names in the revenue file |
|---|---|---|
| LOUNGES | Domestic Lounge | Domestic Lounge |
| LOUNGES | International Lounge | International Lounge |
| LOUNGES | Reserved Lounge | Reserved Lounge |
| SPA | Spa Domestic | — (always shown; no line in the file yet) |
| ATITHYA SERVICES | Atithya | Meet & Greet |
| ENWRAP | Enwrap | Baggage Wrapping |
| PORTER | Porter | Porter |

Sky Plates and Encalm Eats lines of the revenue file go to their own pages
(one row per location).

---

## 5. Encalm Eats AOP → DSR outlets

`eats_skyplates_aop_parser.py` reads the AOP master's **IFK** rows (→ Sky
Plates, one target per location, outlet *Encalm Sky Plates*) and **F&B** rows
(→ Encalm Eats, the outlet rows under each section head; heads are subtotals
and are only used to check the outlets add up).

`_DSR_OUTLET_MAP` — key (location, section, AOP name, occurrence):

| Location / section | AOP line | DSR outlet |
|---|---|---|
| Delhi T3 Departures | Chaayos 42A | Chaayos T3 Gate No. 42A |
| Delhi T3 Departures | Chaayos 54-55 | Chaayos T3 Gate No 54 |
| Delhi T3 Departures | IndiSip 44 | IndiSip T3 - Mezzanine Gate 44 |
| Delhi T3 Departures | IndiSip 3 | IndiSip T3 - Int. IFK 02, Gate 03 |
| Delhi T3 Departures | IndiSip 32-34 | IndiSip T3 - Int. Gate no 32 |
| Delhi T3 Arrivals | CDH | Cafe Delhi Heights T3 Domestic Arrival |
| Delhi T2 Departures | IndiSip SHA | IndiSip T2 - Bus Gate |
| Delhi T2 Departures | Indisip PreChk | IndiSip T2 - Pre Checkin |
| Delhi T2 Departures | Haldiram PreChk | Haldiram T2 Pre Check-in |
| Delhi T2 Departures | Indisip Bar PESC | J&B Pour House T2 |
| Delhi Events & ODCs | Events & ODCs | Event/ODC |
| Bhogapuram | Mc Donald's | McDonald's- Bhogapuram |
| Bhogapuram | IndiSip (1st) | IndiSip Café |
| Bhogapuram | IndiSip (2nd) | Indisip Bistro |
| Bhogapuram | Starbucks (2nd line) | Starbucks Departure **+** Starbucks Arrival (split by revenue) |
| Bhogapuram | South Indian Culinary House | Svara |
| Bhogapuram | Multi-Cuisine Concept | Totally Desi |

- **Not matched yet** (kept as "*Name (Section)*", shown as planned outlets):
  BAR SHA, Walkway, Carnatic Café, Chaayos (T3 Arrivals), Subway, KFC, Popeyes,
  Fly High BAR, GMR, IROP.
- **DSR outlets with no AOP line:** ALD, VTZ INN, Cafeteria Admin Block.
- **Lines with a note** in the Business Segment column (e.g. "Put in as other
  rev", "Change as per actual") are **not imported** (provisional figures) and
  are listed as *Not imported* in the upload's mapping table. In the current
  master: Star Bucks (T2), Starbucks (Bhogapuram, 1st), Events & ODCs,
  Institutional Catering.
- Location "All" (Events & ODCs) is stored under Delhi.

To map a new line: add an entry to `_DSR_OUTLET_MAP` with the exact DSR
outlet name (as stored by the DSR parser) and re-import the AOP master with
*Replace* ticked.

---

## 6. Encalm Eats DSR parser — `encalm_eats_dsr_parser.py`

- One sheet per day (`DD-MM-YYYY`); outlet rows follow "Outlet Wise Detail".
- Section headers set the location and are never stored as outlets:
  *Delhi Store's* / *Delhi* → Delhi; *Bhogapuram* / *Bhogapuram Store's* →
  Bhogapuram. *Encalm Eats* (grand total) is skipped.
- Names are trimmed and repeated spaces collapsed; `_CANONICAL` fixes known
  spellings (e.g. *Events/ODC* → *Event/ODC*).
- Rows with no covers and no revenue are skipped; MTD/YTD columns are stored
  for reference only.
- Saving skips rows already stored for the same date + outlet + location.

---

## 7. Adding a new EHPL outlet

1. `modules/database.py` — add its spellings to `_OUTLET_NAME_CANONICAL`
   (and `_CANONICAL_OUTLET_TO_BU` if the business unit is not Lounges).
2. `modules/terminal_mapping.py` — map it to its terminal (for traffic, PEN %, SPP).
3. `modules/outlet_groups.py` — add it to the location's `*_GROUPS` (new group
   or existing), give it a display name (`OUTLET_DISPLAY_NAMES` or
   `LOCATION_DISPLAY_OVERRIDES`), and to `ALWAYS_SHOW_ROWS` if it should
   always be listed.
4. `modules/ehpl_layout.py` — put a new group into the right section.
5. Run the tests. Without steps 3–4 the outlet still shows (under OTHERS, with
   its stored name) and is counted in the totals.
