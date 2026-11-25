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
- [x] Material status (CA01, CA02, MM02 alike): **E3** (not active in this plant) -> every step of
      the row Skipped **while planning** from Snowflake MARC.MMSTA, SAP is never opened; **S1 / S2**
      (S+E in this / other plants) -> planned normally, their SAP warning gets an extra Enter (max 2);
      safety net in SAP: `E3` / `NOT EXIST` in the status bar -> Skipped (2026-11-18)
- [ ] Material status S1 / S2 on a real SAP screen: confirm they only give a warning (test rows 11-13
      of `add_routing_test.xlsx`); an error message would make the step Failed instead
- [x] MM02 delete version: button `btn[14]`, no confirmation popup; unexpected popup -> stop (2026-11-18)
- [x] **MM02 delete picks the routing's version, not the first row** (bug seen live 2026-11-19: only
      the row was ticked, SAP deleted the row under the cursor = row 0). Now (`mm02.delete_version`):
      row found by the version number Snowflake has for the routing's group + group counter; its text
      must equal the Snowflake text, else nothing is touched; cursor put on that row's cell + row
      ticked, then Delete; afterwards exactly that version must be gone, else Failed and SAP is left
      **without saving** (a delete only counts at Save). Test
      `test_delete_version_deletes_exactly_the_routing_version` (2026-11-19)
- [ ] MM02 delete fix on a real SAP screen; check the materials of the earlier delete run in MM02 /
      Snowflake for a wrongly deleted version
- [x] CA01 "Create Routing: Operation - Check" right after the header Enter (status "Enter standard
      value Setup", copied operation without setup, e.g. AS `C_AUTO` MP03): blank setup `sub/3/txt[6]`
      -> `1`, blank unit (field right of setup, found by position) -> `H`, Enter, per operation (max 20)
      until the operation overview; the header no longer Enter-s this warning away; not reported in the result; see I.4 (2026-11-18)
- [x] Setup check after the header on a real SAP screen: AS `C_AUTO1` rows, 3 operations filled (2026-11-19)
- [ ] Setup check after the **work-center Enter** on a real SAP screen: rerun row 2 of `add_routing_test - Copy.xlsx` (STP 5051070099)
- [x] Error handling: status bar logged before the reset; reset leaves without saving (save question -> No, data lost -> Yes, unknown popup -> run stops); Save never pressed for a failed step; see I.5 (user requirement, 2026-11-18)
- [ ] Exit popup texts on a real SAP screen (CA01, CA02, MM02): confirm they match the save / lost patterns
- [x] All element ids match the UiPath selectors (`docs/uipath/ui_elements.csv`) (2026-11-18)
- [x] Copy list 2120 recorded (material 5051070099): group `ctxt[0,row]` (first row of each group only), GCt `txt[1,row]`, description `txt[7,row]` = the double-clicked cell; description was `2` from UiPath, corrected to `7` (2026-11-19)
- [ ] BOM popup AltBOM column 19 (SAP_automation) vs 8 (UiPath) - record
- [ ] F12 after the production version Check: wnd[2] or wnd[3] - record
- [ ] Operation overview row numbers per layout (`architecture.md` 6.6) - first live routing per layout
- [ ] First live run: one row with `routing run FILE --rows N --slow`

### Business rules (details: C, D, E, F, H, I)
- [x] Copy source: same material, status 4, not flagged; normal resource -> never a TRIAL / MDTRIAL
      routing, trial resource -> only a trial routing (2026-11-17, trial resource rule 2026-11-18)
- [x] Copy source has the same sorting shape as the request - YMHI step from the **operations**,
      not the name - also for the COPY_FROM override (2026-11-18)
- [x] Blank optional values (no tool, no sorting / lubricant) never break a name or stop the run (2026-11-18)
- [x] Final step = PP94 only; ZP04 = trial routing (2026-11-18)
- [x] Delete / Assign Components never guess between several matching routings (2026-11-17/18)
- [x] Which routing a row means: group + group counter given -> exactly that one; else found in
      Snowflake by resource + tool + sorting, exactly one or skip; trial routings only for a trial
      resource; Add writes the new group / counter back; see H (2026-11-18)
- [x] ALL BOM creates only the missing production versions (real active alt BOM numbers) (2026-11-17)
- [x] BOM allocation follows `SAP_automation` (same screens, two passes 0030 / 0020); a number =
      that alt BOM only, ALL BOM = every active alt BOM; see F (2026-11-18)
- [x] Missing setup on a copied operation (CA01 "Operation - Check" after the header): setup =
      `1`, unit = `H`, only where blank, every operation SAP stops on; see I.4 (user rule, 2026-11-18)
- [x] Operation layout per department (rows, work centers, base qty, Operation Details incl. setup
      for MD) written down in one place; see I.2 / I.3 (2026-11-18)
- [ ] Delete order inside a row (routing inactivated first, then versions deleted) - confirm on SAP
- [ ] Packaging -> 0030 also in sorting routings (0030 = YMHI, not the pack step) - confirm
- [ ] More workflow types than AS, PLT, STP, MD, MD_SORTING (AS / STP with sorting, hi-coat,
      regrinding, automation cutting, plating with rewind)? each = one `LAYOUTS` entry
- [ ] **C_AUTO assembly routings do not fit the AS layout** (found 2026-11-18, test rows 16-17).
      AS layout = 0010 XQA, 0020 machine (overview row 1), 0030 PP94 final (row 2). C_AUTO routings
      have extra steps: 0020 `C_AUTO`, 0030 `C_FN` / `C_RN`, 0040 `C_FE` / `C_RE` (MC01), PP94 only at
      0050 / 0060 - so Capacity would be typed into 0030 `C_FN` instead of the final step.
      Proposal: new layout `AS_AUTO` (0020 = Resource, later steps keep the copied work center) and
      a Plan warning when PP94 is not on the row the layout expects. **Decision needed: which rows
      get Capacity** - in Snowflake every step 0020 .. PP94 of these routings has the same base
      quantity (e.g. 332 on 0020, 0030, 0040, 0050), so either type Capacity on every step, or only
      on 0020 + PP94. Until then: run these rows with `--phase routing` and check them in SAP.
- [ ] **Delete after Add on the same rows needs clearing result cells** (found 2026-11-18). Add and
      Delete share `RESULT_ROUTING` / `RESULT_MM02`; a `Done` from the Add run makes the Delete steps
      count as done. Today: clear those cells before the Delete run (H.5). Proposal: a result only
      counts for the Action that wrote it (e.g. `Done (Add): ...`).
- [ ] Production version planned for an **inactive alt BOM** (`Alt Bom` = 1 when only 2 is active):
      component allocation is skipped, the pv step only warns. Proposal: skip it the same way
      (`alt BOM 1 not active (active: 2)`).
- [ ] Dry run does not fix the Delete target (the real run plans again). Proposal: the dry run
      writes the planned group / group counter into Delete rows.
- [ ] `routing check routing-condition` still counts trial routings as existing (H.3) - keep or
      follow the automation's trial rule?
- [ ] Action `Assign Components` on a plating (PLT) row still allocates components (Add excludes
      PLT: plating needs a new BOM). Proposal: skip PLT for Assign Components too.
- [ ] Full SAP flow of `CreateRouting`, `CreateProductionVersion`, `DeleteProductionVersion` is only
      tested at planning level / partly with a fake SAP; the first live runs are the real test.
- [ ] Overlap: `checks/operation_values.py`, `delete_status.py`, `routings_by_tool.py` still have
      their own matching instead of the shared rule (`model/entities.py`) - clean up later.

### Scope
- [x] Only the UiPath files that are run (and what they invoke) are migrated (`architecture.md` 0) (2026-11-18)
- [x] Same Info and Change Resource are backlog, not in the code (`architecture.md` 9) (2026-11-18)
- [x] All 15 UiPath risks / defects (former `uipath_flows.md` section 8) handled or out of scope; see G (2026-11-18)
- [ ] Component table: only the visible page is read (as `SAP_automation` and UiPath) - scroll if
      a material has more components than fit on one page (a warning is written today)
- [ ] opc phase (TPM / workflow files) - not built in `routing run`. **For now run separately**
      with the existing commands (`routing opc add-tpm`, `add-workflow`, `delete-tpm`) after the SAP
      run (decided 2026-11-18); workflow inactivation has no generator yet

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
| CA01 after the header, after the work centers, in Operation Details (`operations.fill_missing_setups`) | "Operation - Check" / "Enter standard value Setup" -> setup `1` + unit `H`, Enter, per operation; screens during the operation entry: see **I** | done (fake SAP), live open |
| CA01 / CA02 / MM02 first screen (`SapSession.check_initial`) | E3 rows never get here (skipped while planning); `E3` (as a word) or `NOT EXIST` in the status bar -> step **Skipped** (`SapSkip`); any other W message, incl. material status S1 / S2 -> extra Enter (max 2) | done |
| MM02 delete version (`mm02.delete_version`) | no confirmation popup in UiPath; any popup -> stop with its text | done |

UiPath differences: it typed material / plant only after "Select Type", never checked a missing
list, and has no Try Catch / Retry (only Element Exists + If). Python handles every combination
explicitly.

## B. Element ids (audit against the UiPath exports, 2026-11-18)

Ids: `src/routing/sap/elements.py` (the only place). Sources: `docs/uipath/ui_elements.csv`,
`docs/uipath/raw/*.xaml.txt`. UiPath `sub?N` = `sub/N`; scope `#32770` = popup `wnd[1]`
(`wnd[2]` for production version details).

- All ids match. Confirmed from UiPath: `VERSION_DELETE = wnd[1]/tbar[0]/btn[14]` (4 flows).
- Recorded 2026-11-19: copy list 2120 = group `ctxt[0]`, GCt `txt[1]`, description `txt[7]` (UiPath's `tableCol='2'` is not the scripting column). Still `VERIFY` (record): (formerly also `COPY_LIST_GROUP_COL` / `COPY_LIST_COUNTER_COL`; UiPath reads 2120 by
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
| Usable | status 4, deletion flag not set; **normal resource -> normal routing only, trial resource (`MDTRIAL`, `PLTTRIAL`, `ASTRIAL`, `ASMTRIAL`, `STPTRIAL`) -> trial routing only** (H) | skip |
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
| 10 | Inconsistent skip / result columns; status bar checks differ (`MATERIAL STATUS` vs `E3`) | One result column per kind of work - `RESULT_ROUTING`, `RESULT_COMPALLOC`, `RESULT_MM02` (`Done` / `Skipped` / `Failed: reason`), `RESULT_INPUT` for unreadable rows - + Plan + Run log sheets (`architecture.md` 7.1); the old UiPath `progress` column is not read; one skip rule for all transactions (E3 skipped while planning; `E3` / `NOT EXIST` in SAP as safety net) (A) |
| 11 | Switch keys case-sensitive (`Add` vs `CHANGE`); an unknown Action still saves and writes `done mm02` | `Action` is case-insensitive (`Add`, `add`, ` ADD `; `Create` accepted as alias); an unknown value makes the row **invalid before anything runs** (listed on the Plan sheet), SAP is never opened for it. Test: `test_action_is_case_insensitive_and_unknown_action_does_nothing` |
| 12 | PV text not length-checked, warning popup after Check ignored, existing versions not detected | Text checked / shortened to 40 before the run; the Check popup text is kept as a warning; existing versions (Snowflake) are skipped, only missing alt BOMs get a version |
| 13 | Only visible rows read (no scrolling) | Routing, group and version lists are paged (`sap/table.find_row`); the component table still reads the visible page only - open item in the checklist |
| 14 | Status `4` typed although the activity says "status 1" | Status 4 = production on create, 1 = inactive on delete (decided) |
| 15 | `SaveAfterEachRow = False`: progress lost on a crash | The request file is saved after every row; a locked file (open in Excel) is reported |

**Double Enter (UiPath sends a second Enter in CA01 / CA02).** After Enter on the first screen of
CA01 / CA02 / MM02 and after the CA01 header (status 4), a warning (W) in the status bar gets one
more Enter, at most 2 (`SapSession.pass_warnings`); an error (E) stops the step; only `E3` /
`NOT EXIST` skip the row (E3 rows are normally skipped while planning already). The MM02 "select views" and "organizational levels" popups each get their
own Enter (`mm02.open_versions`). Test: `test_initial_screen_warning_gets_extra_enter`.

## H. Which routing a row means (Delete, Assign Components, "already exists" on Add)

Code: `steps/routing.py` `matching_routings` / `single_routing`, rule in `model/entities.py`
(`Routing.matches`, `MaterialRoutings.matching`), data from `data/routing.routing_operations`
(one Snowflake query for all materials of the file, read while planning, before SAP is touched).
`checks/routing_condition.py` uses the same matching rule (see the trial exception below).

**1. `group` and `group counter` both filled -> exactly that routing.** The routing with this
material + group + group counter is taken from the Snowflake list; resource / tool are not used.
Group + group counter identify one routing in SAP, so there is never more than one. Not in
Snowflake -> `Skipped: routing not found`; nothing else is chosen instead. In CA02 the same group
is picked in the group popup and the same counter in the header list (never by position).

**2. Blank -> found in Snowflake** by the routing-condition rule: `Resource` is a work center of
one of the routing's operations, `Tool` and `Sorting/ Lubricant` (when filled) are in its name.

| Matches (active routings) | Result |
|---|---|
| exactly 1 | that routing; its group / group counter are written into the row |
| 2 or more | `Skipped: 2 routings match (M0527609/13, M0527609/15), fill group / group counter` - never a guess (common for plating: no tool) |
| none, only a deletion-flagged one | `Skipped: already inactive G/C` |
| none | `Skipped: routing not found` |

Check before a real run: `routing run FILE --dry-run` -> Plan sheet, column **Target routing**
shows the exact group / counter per row (or the skip reason). Type group / group counter into a
row to fix the choice.

**3. Trial routings (decided 2026-11-18).** A trial routing = `TRIAL` in the name or a trial work
center (`MDTRIAL`, `PLTTRIAL`, `ASTRIAL`, `ASMTRIAL`, `STPTRIAL`) in its operations (546 active
status-4 trial routings at plant 1901, 2026-11-18).

| Request `Resource` | Matching / "already exists" / Delete | Copy source on Add |
|---|---|---|
| normal machine (e.g. `MF15-17`) | normal routings only - a TRIAL routing is never deleted or counted | normal routing only |
| trial work center (e.g. `MDTRIAL`) | trial routings only | trial routing only (status 4, not flagged), never a normal one |

`routing check routing-condition` keeps counting trial routings as existing (it reports what is in
SAP); only the routing automation separates them. Production versions are not created for trial
routings (unchanged). Tests: `test_trial_resource_only_finds_and_copies_trial_routings`,
`test_delete_never_picks_a_trial_routing_for_a_normal_resource`.

**4. Production versions of a Delete row** = the versions in Snowflake (MKAL) whose group + group
counter are the chosen routing's, deleted by version number. Versions of other routings are never
touched. None -> `Skipped: no production version on G/C`.

**5. Add -> later Delete of the same test routings** (e.g. `add_routing_test.xlsx`):
1. The Add run reads the **new** group / group counter from the CA01 header screen (not from
   Snowflake) and writes them into the row's `group` / `group counter`.
2. For the Delete run: change `Action` to `Delete` in the same rows (group / counter stay), and
   **clear `RESULT_ROUTING` and `RESULT_MM02`** - Add and Delete share these columns, a `Done` from
   the Add run would make the Delete steps count as already done.
3. Wait ~15 minutes after the Add run: Delete looks the routing and its versions up in Snowflake,
   which lags SAP. Too early -> `Skipped: routing not found` / `no production version` (safe, run
   again later).
4. Delete = deletion flag + status 1 (not a hard delete; the flag can be unticked).

## I. CA01 operations: what each department types, and the screens SAP may stop on

One section for everything between the header and Save in `CreateRouting.run`
(`steps/routing.py`): the per-department operation layout and the screens SAP can put in between.
Layouts: `src/routing/layouts/catalog.py` (`LAYOUTS`); screens: `sap/screens/ca01.py`,
`sap/screens/operations.py`; element ids: `docs/uipath/ui_elements.md` (3.1 and 4).

### I.1 Sequence after the header

| # | Screen | What happens | Code |
|---|---|---|---|
| 1 | Header Data Check / Header Details | description, read group + counter, status `4`, Enter; a W warning gets one more Enter - **except** the setup warning (I.4) | `ca01.fill_header` |
| 2 | **Operation - Check** (only if a copied operation has no setup) | setup `1` + unit `H` per operation, Enter, until SAP moves on (I.4) | `operations.fill_missing_setups` (from `ca01.open_operations`) |
| 3 | Header Details still shown | press Operations `wnd[0]/tbar[1]/btn[7]` | `ca01.open_operations` |
| 4 | Operation Overview | work centers per layout row, Enter; **setup check again** (I.4); SAP errors stop the row; must be back on the overview | `operations.set_work_center`, `operations.fill_missing_setups` |
| 5 | Operation Overview | base quantity (col 5) per layout row | `operations.set_base_quantity` |
| 6 | Operation Details (double-click description col 6) | detail fields per layout row, Enter, **setup check again** (I.4), Back; machine name from Display Work Center (MD) | `operations.set_details`, `operations.machine_name` |
| 7 | Operation Overview | Save | `ca02.save` |

### I.2 Operation layout per department

Rows = 0-based visible rows of the operation overview (0 = 0005, 1 = 0010, 2 = 0020, ...).
"keep" = the copy source's work center stays. Not verified on SAP yet (`verified = False`).

| Layout (when) | Row | Role | Work center | Base qty (overview) | Operation Details |
|---|---|---|---|---|---|
| **AS** (Dept AS) | 1 | production | Resource | Capacity | - |
| | 2 | final (PP94) | keep | Capacity | - |
| **PLT** (Dept PLT; no component allocation) | 1 | production | Resource | Capacity | - |
| | 2 | final | keep | Capacity | - |
| **STP** (Dept STP) | 2 | production | Resource | - | base qty, cavity, eff, util |
| | 3 | tool line | Tool | - | op text = its WC text, base qty, cavity, eff, util |
| | 4 | final | keep | Capacity x Tool Cavity | - |
| **MD** (Dept MD, no Sorting/ Lubricant) | 2 | production | Resource | - | op text = machine name, base qty, cavity, eff, util, **setup 1** |
| | 3 | tool line | Tool | - | op text = its WC text, base qty, cavity, eff, util |
| | 4 | final | keep | Capacity x Tool Cavity | - |
| **MD_SORTING** (Dept MD + Sorting/ Lubricant) | 2, 3 | as MD | | | as MD |
| | 4 | sorting (YMHI) | Sorting/ Lubricant | Sorting/ Lubricant Capacity | - |
| | 5 | final | keep | Capacity x Tool Cavity | - |

Detail fields: base qty = Capacity, cavity (unit conversion header qty) = Tool Cavity,
eff / util = Efficiency / Utilization - **blank in Excel = not typed, the copied value stays** (D.3).
Setup is typed only by MD / MD_SORTING on the production row (`1`, as UiPath mold; commented out in
UiPath stamping). Not covered: `C_AUTO` assembly routings (Business rules checklist, open item).

### I.3 Department differences in short

| | AS | PLT | STP | MD | MD_SORTING |
|---|---|---|---|---|---|
| Opens Operation Details | no | no | yes (2 rows) | yes (2 rows) | yes (2 rows) |
| Tool work center | - | - | row 3 | row 3 | row 3 |
| Machine name as op text | - | - | - | yes | yes |
| Setup typed | - | - | - | yes (`1`) | yes (`1`) |
| Final step base qty | Capacity | Capacity | Capacity x Cavity | Capacity x Cavity | Capacity x Cavity |
| Component allocation | yes | **no** | yes | yes | yes |

### I.4 Missing setup on a copied operation (Operation - Check)

**Rule (user, 2026-11-18; extended 2026-11-19):** after **every Enter of the operation entry** - after the header, after the work centers (seen live: row 2 of `add_routing_test - Copy.xlsx`, STP 5051070099, error was `No cell [5,4] ... status 'Enter standard value Setup'`), and in Operation Details - when CA01 stops on
"Create Routing: Operation - Check" with the status "Enter standard value Setup", type
**STD Setup = `1`** and **unit = `H` (hour)**, press Enter, and repeat for every time the popup shows
(once per operation that has no STD Setup), until the operation overview shows. Only blank fields
are filled; a value already there is kept. Applies
to every department (it depends on the copy source, not the layout).

| Item | Value |
|---|---|
| Why it happens | the copy source has an operation without setup, e.g. AS `C_AUTO` (control key MP03) - 152 such MP03 rows at plant 1901 (`docs/operation_values.md`, "Known exceptions") |
| Values | `elements.SETUP_DEFAULT = "1"`, `elements.SETUP_DEFAULT_UNIT = "H"`; consistent with the standard-value rule `1.000 H` at 0020 of `routing check operation-values` |
| Limit | max 20 times per Enter (`operations.MAX_SETUP_CHECKS`), then Failed; an SAP error (E / A) other than the setup message -> Failed |
| Where | `operations.fill_missing_setups` (shared): called in `ca01.open_operations` (after the header), `CreateRouting.run` after the work-center Enter, `operations.set_details` after its Enter. `fill_header` no longer Enter-s this warning away (`operations.on_setup_check`) |
| Result | not reported in `RESULT_ROUTING` (user: redundant, 2026-11-19) - the row just shows `Done: ...` |
| Elements | setup `wnd[0]/usr/sub/3/txt[6]`; unit has no recorded id, found as the field right of setup (`docs/uipath/ui_elements.md` 4) |
| Test | `test_setup_check_after_header_gets_setup_1_h_until_operation_overview`, `test_setup_check_is_handled_after_any_enter_not_only_after_the_header` |
| UiPath | had an Enter on this screen, commented out (`create_routing_mold` / `_stamping`); it never typed a value |
| Live | after the header: done 2026-11-19 (rows 4, 5 of `add_routing_test - Copy.xlsx`, AS `C_AUTO1`: `setup 1 H entered on 3 operation(s)`). After the work centers: fix not run live yet (row 2). Open: record the unit field id |

### I.5 Other screens that stop the operation entry

| Screen / message | Python |
|---|---|
| E / A status after the work-center Enter (e.g. unknown work center) | row Failed with the SAP text (`raise_on_error("work centers")`) |
| Operation Details does not open | row Failed: `Operation Details of row N did not open` |
| Operation overview not shown after btn[7] | row Failed: `Operation overview not shown` |
| any failure | (1) the SAP screen + status bar are read and added to the result as `[SAP: wnd[0] '...', status '...']` (unless the message already has them); (2) reset: popups closed, `/n`; the exit popup is **read**: save question -> **No**, "data will be lost" / "exit editing" -> **Yes** (leave unsaved), anything else -> the run stops (nothing clicked, RunAborted); (3) row Failed, next row. **Save is never pressed for a failed step** - steps press it only as their last action. Tests: `test_failed_step_logs_status_bar_and_never_presses_save`, `test_reset_never_saves_save_question_no_data_lost_yes_unknown_stops` |
