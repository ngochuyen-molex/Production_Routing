# Production version checks

Production versions live in SAP table `MKAL` (material + plant + version `VERID`), each pointing to
one routing (`PLNNR` group + `ALNAL` group counter) and one alternative BOM (`STLAL`).
Code: `src/routing/data/production_version.py` (queries), `src/routing/checks/` (logic).

All queries only return versions still in SAP (`DW_SOFT_DELETE_FLAG = 0`). Permanently deleted
versions stay in the data lake as history; e.g. 5013300800 has 12 rows in `MKAL` but only
0001-0005 are in SAP.

## Commands

| Command | What it does |
|---|---|
| `pv-count` | number of production versions per material |
| `pv-by-group` | version(s) of the row's group + group counter |
| `pv-by-attributes` | versions whose routing uses the row's Resource (+ Tool / Lubricant as PRT) |
| `pv-fallback` | group first, then attributes |
| `pv-exist` | does the version for the row's routing + Alt Bom already exist? |

## pv-exist

Input: `Material`, `group`, `group counter` (from the routing condition check), `Alt Bom`.

| Alt Bom | Check | PV_CHECK |
|---|---|---|
| a number (1, 2, ...) | version with that alt BOM on the row's routing | `Exists` / `Missing` |
| `ALL BOM` | not checked for now | `ALL BOM - not checked` |
| blank group / counter | - | `No routing (group / group counter blank)` |
| anything else | - | `Invalid Alt Bom` |

`PV_FOUND` lists the matching versions, e.g. `0004 (B1)` (`locked` added when locked). For ALL BOM
rows it lists every version already on the routing, so partly existing routings can be spotted.

## Open concern: ALL BOM (logged 2026-11-16)

A request with `Alt Bom = ALL BOM` normally means the routing has **no** production version yet,
so creating one version per alternative BOM (count 3 -> B1, B2, B3) is fine.

But a routing can already have a version for some alt BOMs and not others. Example: 5013300800,
M5013300 / 34 has 0004 (B1) while the material has 3 active alt BOMs. Creating "all" there would
duplicate B1. This is why ALL BOM rows are not checked automatically yet: look at `PV_FOUND` and
create only the missing ones.

If this gets automated later:
- check each alt BOM separately and report which exist / are missing;
- take the actual active alt BOM numbers from `MAST` / `STKO`, not `ALT_BOM_COUNT`: a material with
  active alt BOMs 1 and 3 has count 2, which would wrongly expect B1 + B2.

### Output layout options (not decided)

Example: M0133008 / 92, ALL BOM, alt BOMs B1-B3, only 0003 (B1) exists.

**A. One row, combined cells** - row count unchanged; hard to filter (B2 is inside a text cell).

| group | GC | Alt Bom | PV_EXPECTED | PV_FOUND | PV_MISSING | PV_CHECK |
|---|---|---|---|---|---|---|
| M0133008 | 92 | ALL BOM | B1, B2, B3 | 0003 (B1) | B2, B3 | Missing B2, B3 |

**B. One column per alt BOM** - row count unchanged, easy to filter (`PV_B2 = MISSING`); column count
follows the highest alt BOM count in the file (plant 1901: 6,060 materials have 1, 740 have 2,
169 have 3, 57 have 4-9). Cell: version number, `MISSING`, or blank when not required.

| group | GC | Alt Bom | PV_B1 | PV_B2 | PV_B3 | PV_CHECK |
|---|---|---|---|---|---|---|
| M0133008 | 92 | ALL BOM | 0003 | MISSING | MISSING | Missing B2, B3 |

**C. Detail sheet, one row per routing x alt BOM** - cleanest to-do list for SAP / UiPath; must be a
separate sheet because the main sheet keeps one row per input row.

| group | GC | Alt BOM | Production version | Status |
|---|---|---|---|---|
| M0133008 | 92 | B1 | 0003 | Exists |
| M0133008 | 92 | B2 | | Missing |
| M0133008 | 92 | B3 | | Missing |

Suggested combination: A or B on the main sheet + C as a detail sheet.
