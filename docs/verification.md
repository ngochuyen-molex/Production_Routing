# Verification log - routing automation

**The one place** for what has been checked and what is still open. Other docs link here instead
of repeating it. When something is checked, tick it here (with the date) and add the detail below.

`[x]` = checked in code + test (fake SAP or unit test) · `[ ]` = open · "live" = on real SAP.
Nothing has been run against real SAP yet.

## Checklist

### SAP navigation and popups (details: A, B)
- [x] CA02 open routing: group popup 2110 / header list 1200 / neither -> same as
      `SAP_automation/change_bom/routing.py`; neither only with 1 routing in the group (2026-11-18)
- [x] CA01 target group popup 2110 shown / not shown (UiPath `nested_find_copy_routing`) (2026-11-18)
- [x] CA01 copy dialog: "Select Type", "Select Object to be Copied", copy list 2120 each shown or
      not; nothing shown -> only with 1 routing of the material (UiPath `find_valid_routing_tocopy`) (2026-11-18)
- [x] "Choose Alternative BOM": row by AltBOM value; BOM usage other than 1 -> stop (2026-11-18)
- [x] Material refused on the first screen (`MATERIAL STATUS`, `E3`, `NOT EXIST`) -> row Skipped;
      warning -> one extra Enter (2026-11-18)
- [x] MM02 delete version: button `btn[14]`, no confirmation popup; unexpected popup -> stop (2026-11-18)
- [x] All element ids match the UiPath selectors (`docs/uipath/ui_elements.csv`) (2026-11-18)
- [ ] Copy list 2120 group / counter columns (0 / 1) - record with the SAP GUI script recorder
- [ ] BOM popup AltBOM column 19 (SAP_automation) vs 8 (UiPath) - record
- [ ] F12 after the production version Check: wnd[2] or wnd[3] - record
- [ ] Operation overview row numbers per layout (`architecture.md` 6.6) - first live routing per layout
- [ ] First live run: one row with `routing run FILE --rows N --slow`

### Business rules (details: C, D, E, F)
- [x] Copy source: same material, status 4, not flagged, not TRIAL / MDTRIAL (2026-11-17)
- [x] Copy source has the same sorting shape as the request - YMHI step from the **operations**,
      not the name - also for the COPY_FROM override (2026-11-18)
- [x] Blank optional values (no tool, no sorting / lubricant) never break a name or stop the run (2026-11-18)
- [x] Final step = PP94 only; ZP04 = trial routing (2026-11-18)
- [x] Delete / Assign Components never guess between several matching routings (2026-11-17/18)
- [x] ALL BOM creates only the missing production versions (real active alt BOM numbers) (2026-11-17)
- [x] BOM allocation follows `SAP_automation` (same screens, two passes 0030 / 0020); a number =
      that alt BOM only, ALL BOM = every active alt BOM; see F (2026-11-18)
- [ ] Delete order inside a row (routing inactivated first, then versions deleted) - confirm on SAP
- [ ] Packaging -> 0030 also in sorting routings (0030 = YMHI, not the pack step) - confirm
- [ ] More workflow types than AS, PLT, STP, MD, MD_SORTING (AS / STP with sorting, hi-coat,
      regrinding, automation cutting, plating with rewind)? each = one `LAYOUTS` entry

### Scope
- [x] Only the UiPath files that are run (and what they invoke) are migrated (`architecture.md` 0) (2026-11-18)
- [x] Same Info and Change Resource are backlog, not in the code (`architecture.md` 9) (2026-11-18)
- [x] All 15 UiPath risks / defects (former `uipath_flows.md` section 8) handled or out of scope; see G (2026-11-18)
- [ ] Component table: only the visible page is read (as `SAP_automation` and UiPath) - scroll if
      a material has more components than fit on one page (a warning is written today)
- [ ] opc phase (TPM / workflow files) - not built; "files at the end of the run" to be confirmed

---

## A. Popup branching when opening a routing

Each case has a fake-SAP test in `tests/test_routing_run.py`.

| Screen | Shown after Enter / Copy from | Python |
|---|---|---|
| CA02 (`ca02.open_routing`, same as `SAP_automation` `process_routing`) | group popup 2110 -> pick by group; then header list 1200 -> pick by group counter | done |
| | no 2110 (material has one group) -> header list 1200 directly | done |
| | neither -> SAP opened the only routing (operation overview); counter can't be checked | only when Snowflake says the group has 1 routing, else error |
| CA01 target group (`ca01.choose_target_group`, UiPath `nested_find_copy_routing`) | 2110 "Entry Option: Group" -> pick the copy source's group (UiPath: first status-4 non-TRIAL row) | done |
| | not shown -> straight to the copy dialog | done |
| CA01 copy dialog (`ca01.choose_copy_source`, UiPath `find_valid_routing_tocopy`) | "Select Type" (by window title) -> Continue | done |
| | "Select Object to be Copied" -> material + plant, Continue | done, only when shown |
| | copy list 2120 -> pick by group + counter (UiPath: first status-4 non-TRIAL, YMHI in name when sorting) | done |
| | none of them -> SAP copied the only routing and went on (BOM popup / header) | only when the material has 1 routing, else error |
| CA01 / components alt BOM (`ca01.choose_alt_bom`) | "Choose Alternative BOM" -> row by AltBOM value, usage must be 1; not shown -> header | done |
| CA01 / CA02 / MM02 first screen (`SapSession.check_initial`) | `MATERIAL STATUS`, `E3` (as a word), `NOT EXIST` -> step **Skipped** (`SapSkip`); W message -> extra Enter (max 2) | done |
| MM02 delete version (`mm02.delete_version`) | no confirmation popup in UiPath; any popup -> stop with its text | done |

UiPath differences: it typed material / plant only after "Select Type", never checked a missing
list, and has no Try Catch / Retry (only Element Exists + If). Python handles every combination
explicitly.

## B. Element ids (audit against the UiPath exports, 2026-11-18)

Ids: `src/routing/sap/elements.py` (the only place). Sources: `docs/uipath/ui_elements.csv`,
`docs/uipath/raw/*.xaml.txt`. UiPath `sub?N` = `sub/N`; scope `#32770` = popup `wnd[1]`
(`wnd[2]` for production version details).

- All ids match. Confirmed from UiPath: `VERSION_DELETE = wnd[1]/tbar[0]/btn[14]` (4 flows).
- Still `VERIFY` (record): `COPY_LIST_GROUP_COL` / `COPY_LIST_COUNTER_COL` (UiPath reads 2120 by
  header name), `BOM_POPUP_ALT_COL` (19 from SAP_automation, UiPath clicks col 8),
  `PV_CANCEL_CHECK` (SAP_automation presses F12 on wnd[2]; the UiPath scope could be a wnd[3] check popup).
- Not ported on purpose: `delete_routing` (MatAssignment), `delete_all_pd`, `delete_pd_textdesc`,
  `change_resource`.
- Different from UiPath on purpose: lubricant rule uses the routing's 0030 work center (UiPath: the
  input Sorting column) and a substring match; production version text = routing description + ` B<n>`.

## C. Copy source rules (which routing CA01 copies)

A wrong source puts values on the wrong operation rows. Code: `MaterialRoutings.copy_source`,
`CreateRouting.plan`.

| Rule | Check | If no routing passes |
|---|---|---|
| Same material | routings of the row's material only (other materials: backlog) | skip |
| Usable | status 4, deletion flag not set, name without `TRIAL` / `MDTRIAL` | skip |
| **Same sorting shape** | request has `Sorting/ Lubricant` -> source **must have** a YMHI sorting step; request without -> source **must not** have one | skip: `no routing of this material to copy from with a YMHI sorting step` |
| Preference | 1. fits the layout, 2. same resource, 3. same sorting work center, 4. newest group counter | - |
| Override `COPY_FROM_GROUP` / `_GC` | must be usable **and** have the same sorting shape | skip: `COPY_FROM M0527609/15 must be a routing with a YMHI sorting step` |

**Sorting step = an operation, not the name.** A routing has sorting when an operation **after
0020** has a work center starting with `YMHI` (Snowflake PLPO + CRHD, `Routing.has_sorting`). The
name is wrong in both directions (status-4 routings, plant 1901, 2026-11-18):

| Routing | Name | Operations | Truth |
|---|---|---|---|
| M0500308/06 | `MF15-20 - 5050030828 - L5050033` | YMHI step after 0020 | sorting (name doesn't say) |
| M0527610/19 | `5052761089 - MN15-17 - L505276A` | YMHI step after 0020 | sorting (name doesn't say) |
| M5133701/04 | `YMHI - 513370162` | YMHI **is** 0020 (hi-coat) | no sorting |
| M9675000/32 | `YMHI-4 - 967501758` | YMHI-4 **is** 0020 (regrinding) | no sorting |

UiPath matched `YMHI` in the description; Python does not. When the chosen source's name and
operations disagree, the Plan sheet warns (`... the operations were used`). The sorting work center
typed into the new routing is always the request's `Sorting/ Lubricant`, so the same work center
is only preferred.

Tests: `test_copy_source_sorting_shape_comes_from_operations_not_name`,
`test_copy_source_prefers_same_sorting_work_center`, `test_copy_source_check_and_ranking`.

## D. Optional values per department (blank Tool, Sorting / Lubricant)

Molding may or may not have a sorting / lubricant step; plating and assembly usually have no tool.
A blank value must not produce a broken name or stop the run.

1. **Reading the Excel**: empty, `0`, `NULL`, `None`, `NaN` in `Tool` and `Sorting/ Lubricant`
   become "no value" (`core/clean.clean_tool`); no `None` / `nan` text reaches SAP.
2. **Names use only the values that exist**: routing description = the layout's parts joined with
   ` - `, blank parts left out (`layouts/select.description`); production version text = routing
   description + ` B<alt BOM>`.

   | Dept | Request | Routing description | Production version text |
   |---|---|---|---|
   | PLT | PM2-A, no tool | `PM2-A - 5052760989` | `PM2-A - 5052760989 B1` |
   | PLT | PM2-A, tool L505276P | `PM2-A - 5052760989 - L505276P` | `PM2-A - 5052760989 - L505276P B1` |
   | AS | AS-01 | `AS-01 - 5052760989` | `AS-01 - 5052760989 B1` |
   | MD | MN15-20, L505276B, no sorting | `MN15-20 - 5052760989 - L505276B` | `... - L505276B B1` |
   | MD | MN15-20, L505276B, sorting YMHI-1 | `MN15-20 - L505276B - YMHI-1` | `MN15-20 - L505276B - YMHI-1 B1` |

   Before 2026-11-18 a PLT row without a tool gave `PM2-A - 5052760989 - ` (dangling dash).
3. **The value decides the branch**: blank Sorting / Lubricant on molding = layout `MD`, filled =
   `MD_SORTING`; blank efficiency / utilization are not typed (the copied values stay).
4. **A value the layout needs skips only that row**, with the reason in `RESULT_` and the Plan sheet:

   | Missing | Needed for | Result |
   |---|---|---|
   | Tool | MD, MD_SORTING, STP | Skipped: `missing Tool for layout MD` |
   | Tool Cavity | MD, MD_SORTING, STP | Skipped: `missing Tool Cavity for layout STP` |
   | Sorting/ Lubricant Capacity | a Sorting/ Lubricant is given | row invalid: `Sorting/ Lubricant Capacity missing` |
   | Capacity | every Create | row invalid: `Capacity missing` |
   | (description over 40 characters) | any | Skipped with the full text |

Tests: `test_blank_tool_or_sorting_never_breaks_names`,
`test_blank_values_needed_by_the_layout_skip_the_row_not_the_run`.

## E. Final step = PP94 only

ZP04 is the control key of trial routings and is never the final step - in the automation
(`Routing.operation(FINAL)`, copy source check) and in `routing check operation-values`.
What `CHECK_FINAL` values mean for the user: `docs/operation_values.md` ("Result values").

## F. BOM allocation (component allocation in CA02)

Same navigation and UI interaction as `SAP_automation/change_bom/routing.py` (`process_routing`,
`open_component_allocation`, `select_components`, `assign_to_operation`). Code:
`sap/screens/components.py` (screens), `steps/components.py` (`AllocateComponents`, rules).

**Which alt BOMs** (planned from Snowflake before the run):

| `Alt Bom` in the row | Allocated | Not possible -> |
|---|---|---|
| a number, e.g. `2` / `B2` | only that alt BOM | skip `alt BOM 2 not active (active: 1, 3)` |
| `ALL BOM` | every **active** alt BOM, by its real number (1 and 3 when 2 is gone) | skip `no active alt BOM` |
| blank | alt BOM 1 | as for a number |

Active alt BOM = MAST usage `STLAN = 1` (production) + STKO status `STLST = 01` (active) + still in
SAP (`DW_SOFT_DELETE_FLAG = 0` on MAST and STKO; 49 rows at 1901 were gone from SAP but counted
as active before 2026-11-18). Query: `data/bom.SQL_ACTIVE_ALT_BOMS` (also used by the pv phase
and `alt_bom_count`).

**Per alt BOM** (one CA02 pass each, saved each time):

1. CA02 open the routing (popup branching: A).
2. CompAlloc (`btn[7]`) -> "Choose Alternative BOM" -> row by AltBOM **value**, BOM usage must be 1.
   No popup -> only fine when the material has one active alt BOM, else stop.
3. Pass 1: read the visible component rows, tick the unassigned ones planned for **0030** ->
   New Assignment (`btn[5]`) -> `0030` -> Enter.
4. Pass 2: read the rows **again**, tick every row still unassigned -> `0020` -> Enter.
5. Save (also when nothing was unassigned). Result e.g. `B1 0030: 2, 0020: 1; B3 0030: 2, 0020: 1`.

0030 rule (as `SAP_automation`): description contains carton / sheet / bag / silica / bubble / box,
or lubricant when the routing's 0030 work center is `YMHI` / `YMHI-1`; everything else 0020. Rows
that already have an operation are never touched, so a rerun is safe. Only the visible page is read
(as `SAP_automation`); a warning is written when the table has more rows.

Differences from `SAP_automation`: the alt BOM list comes from the row (`Alt Bom`) and Snowflake
instead of one routing x alt BOM input line; the BOM usage check is added (UiPath
`main_bom_assignment`).

Test: `test_bom_allocation_all_bom_two_passes_per_alt_bom`.

## G. UiPath risks and defects - how the Python version handles them

The list found in the UiPath project (formerly `docs/uipath_flows.md` section 8, removed 2026-11-18).

| # | UiPath risk / defect | Python |
|---|---|---|
| 1 | No error handling: an unexpected popup stops the run mid-transaction | Any error in a step -> SAP reset (close popups, `/n`, "data will be lost" -> Yes, **nothing saved**) -> `Failed: <message + SAP screen>` in the row's `RESULT_` column and the Run log -> next row. Later steps of that row are not run; a rerun retries Failed steps and skips Done ones. Only if the reset itself fails (session gone) does the run stop with `RUN STOPPED - stopped after row N ...` - results so far are saved. Test: `test_failed_row_resets_sap_and_run_continues_but_stops_when_reset_fails` |
| 2 | Hard-coded Excel path per file; plt reads the stamping file | No paths in the code: one request file of any name / location, `routing run FILE [--sheet NAME]`, one row per request with an `Action` column (Add / Delete / Assign Components) and `Dept` - all departments in one file. Results are written back into that file |
| 3 | Positional selection: alt BOM row = `Alt Bom - 1`, `FindIndex = -1` clicked without a check | Every list is searched by **value** (group, group counter, AltBOM) and "not found" stops the step with a message; nothing is clicked by position. Operation rows per department are data (`layouts/catalog.py`), still to be verified live (checklist) |
| 4 | `change_wc_sap` invokes a wrong folder | out of scope (not run) |
| 5 | `delete_routing` does not delete; delete calls the chooser without `in_sort_lub` | Delete = `InactivateRouting` (deletion flag + status 1, as `inactive_routing`); the routing is found with resource + tool + sorting (or group / counter) |
| 6 | Single-routing materials: "routing not found" / unchecked "found" | CA02 and CA01 accept "no list shown" only when Snowflake says there is exactly one routing; otherwise the step stops (A) |
| 7 | CA01 lubricant rule gets no `sort_lub` -> lubricant to 0020 | The 0030 work center comes from the routing's operations (or the row's `Sorting/ Lubricant` for a new routing) (F) |
| 8 | `create_routing_as`: alt BOM row off by one, status bar read with the CA02 window title, no transaction call | Alt BOM by value; status bar read from the session (no window title); every row starts with `/nCA01` / `/nCA02` / `/nMM02`. All popup combinations before the alt BOM popup (target group 2110, Select Type, Select Object, copy list 2120, none of them) are handled (A) |
| 9 | ALL BOM only in mold and `add_pd`; `CInt("ALL BOM")` fails in plt / stp | `Alt Bom` is parsed once for every department (number, `B2`, `ALL BOM`, blank = 1; anything else -> row invalid). ALL BOM = every active alt BOM by real number for components (F) and production versions; in the CA01 copy popup the first active alt BOM is chosen |
| 10 | Inconsistent skip / result columns; status bar checks differ (`MATERIAL STATUS` vs `E3`) | One result column per kind of work - `RESULT_ROUTING`, `RESULT_COMPALLOC`, `RESULT_MM02` (`Done` / `Skipped` / `Failed: reason`), `RESULT_INPUT` for unreadable rows - + Plan + Run log sheets (`architecture.md` 7.1); the old UiPath `progress` column is not read; one skip rule for all transactions (`MATERIAL STATUS`, `E3`, `NOT EXIST`) (A) |
| 11 | Switch keys case-sensitive (`Add` vs `CHANGE`); an unknown Action still saves and writes `done mm02` | `Action` is case-insensitive (`Add`, `add`, ` ADD `; `Create` accepted as alias); an unknown value makes the row **invalid before anything runs** (listed on the Plan sheet), SAP is never opened for it. Test: `test_action_is_case_insensitive_and_unknown_action_does_nothing` |
| 12 | PV text not length-checked, warning popup after Check ignored, existing versions not detected | Text checked / shortened to 40 before the run; the Check popup text is kept as a warning; existing versions (Snowflake) are skipped, only missing alt BOMs get a version |
| 13 | Only visible rows read (no scrolling) | Routing, group and version lists are paged (`sap/table.find_row`); the component table still reads the visible page only - open item in the checklist |
| 14 | Status `4` typed although the activity says "status 1" | Status 4 = production on create, 1 = inactive on delete (decided) |
| 15 | `SaveAfterEachRow = False`: progress lost on a crash | The request file is saved after every row; a locked file (open in Excel) is reported |

**Double Enter (UiPath sends a second Enter in CA01 / CA02).** After Enter on the first screen of
CA01 / CA02 / MM02 and after the CA01 header (status 4), a warning (W) in the status bar gets one
more Enter, at most 2 (`SapSession.pass_warnings`); an error (E) stops the step; a material-status
message skips the row. The MM02 "select views" and "organizational levels" popups each get their
own Enter (`mm02.open_versions`). Test: `test_initial_screen_warning_gets_extra_enter`.
