# UiPath project - logic flow (part 2 of 2)

Source: `C:\Users\nguyeb3\OneDrive - kochind.com\Documents\UiPath\add routing` (read 2026-11-16,
nothing changed there). UI elements (part 1): [`uipath/ui_elements.md`](uipath/ui_elements.md),
catalogue `uipath/ui_elements.csv`. Full pseudo-code per file: `uipath/raw/*.txt`.

Purpose of this file: what each workflow does, how workflows call each other (arguments in / out),
the conditions and loops, and what that means for the Python design (`docs/architecture.md`).

---

## 1. Project facts

| Item | Value |
|---|---|
| `project.json` description | "create routing ca02 (copy from, edit, get group information), add production version for bom 1" |
| Dependencies | UiPath.Excel 3.5.1, IntegrationService 1.25, Python 2.2.2 (not used in any XAML), System 26.8.1, UIAutomation 25.10.31 |
| Expression language | VB.NET |
| Entry point | `main.xaml` with arguments `action_input`, `bom_alt_input`, `filepath_input` - **the body is empty** (no activities). No workflow is called from main |
| How it is run today | each workflow is opened and run on its own in Studio ("Run File"); each has its **own hard-coded Excel path** |
| Error handling | **none**: no Try Catch, Retry Scope or Throw in any file. "Check App State" (exists / not exists) is the only popup handling; fixed delays of 1-2 s |
| Excel | `Use Excel File` + `For Each Excel Row` on `Sheet1`, headers on, stops at the first empty row, `SaveAfterEachRow = False` (progress cells are lost if the run crashes before the workbook is saved) |
| Non-ID clicks | none - every UI action has a SAP element id (part 1, section 1) |

### 1.1 How the user runs it today (confirmed 2026-11-16)

`main.xaml` is not used. Each step is started on its own:

| Step | Run | Helpers it calls |
|---|---|---|
| Create routing (CA01) | the department file in `add_routing/`: `create_routing_as` / `_plt` / `_stamping` / `_mold` (`_sameinfo` = copy variant) | `nested_find_copy_routing` + `find_valid_routing_tocopy`: pick the routing to copy when the "Entry Option: Group" / "Select Type" popups appear |
| Assign components of a specific routing (CA02) | `bom_assign/main_bom_assignment` | `choose_routing_allocate_bom` (find the routing), `assign_bom_activity` |
| Delete routing (CA02) | `change_routing/inactive_routing` | routing chooser (the XAML invokes `bom_assign/choose_routing_allocate_bom`, not `change_routing/choose_routing`) |
| Production versions (MM02) | `production_version/production_version_main` (common navigation, Switch on Action) | Add: `add_pd` -> `add_production_detail`; Delete: `delete_production_version` |

Not part of the current flow (kept for reference / future features): `change_routing/delete_routing`,
`change_routing/delete_product_version`, `production_version/delete_all_pd`, `delete_pd_textdesc`,
`change_resource`, and the root `change_capacity*`, `change_wc_sap` (future "change" features in
`docs/architecture.md` section 9).

---

## 2. Call graph

Read it like Python: a workflow = a function, **In** arguments = parameters, **Out** arguments =
return values. `[run]` = the file you start yourself; indented boxes are the files it calls, in order.

### 2.1 Create routing (CA01) - one department file per run

```
[run] add_routing/create_routing_<dept>.xaml          (as / plt / stamping / mold / sameinfo)
  |   loop: for each Excel row
  |
  |-- 1. nested_find_copy_routing(material, resource, in_sort_lub)        pick the routing to copy
  |       |   if popup "Entry Option: Group":  click first Status 4, not TRIAL
  |       |
  |       '-- find_valid_routing_tocopy(material, in_sorting_lubricant)
  |               if popup "Select Type": copy-from dialog -> click first Status 4,
  |               not TRIAL / MDTRIAL, contains YMHI when sorting is given
  |
  |-- 2. (inline) header, description, status, operation rows per department (section 4)
  |
  '-- 3. assign_bom_activity()                                           not in plt
          assign each unassigned component to 0030 / 0020, Save
```

### 2.2 Assign components of a specific routing (CA02)

```
[run] bom_assign/main_bom_assignment.xaml
  |   loop: for each Excel row where ALT_BOM_COUNT = 2
  |
  |-- 1. choose_routing_allocate_bom(tool, resource, in_sort_lub) -> row_index
  |         row_index = -1  ->  Save, write "not found routing", next row
  |
  '-- 2. assign_bom_activity(sort_lub)          after choosing alt BOM 2 in the popup
```

### 2.3 Delete routing (CA02)

```
[run] change_routing/inactive_routing.xaml
  |   loop: for each Excel row
  |
  '-- choose_routing_allocate_bom(tool, resource) -> row_index      (in_sort_lub not passed!)
          row_index <> -1  ->  Header -> tick Deletion flag -> status 1 -> Save
          row_index =  -1  ->  Save, write "routing not found"
```

### 2.4 Production versions (MM02)

```
[run] production_version/production_version_main.xaml
  |   loop: for each Excel row:  open material -> ProdVersions
  |
  |-- Switch "Action"
  |     |
  |     |-- "Add"    --> add_pd(group, group_counter, resource, tool, material,
  |     |                       alt_bom_ver, alt_bom_count, in_sort_lub)
  |     |                  |
  |     |                  '-- add_production_detail(bom_alt, group, group_counter,
  |     |                                            tool, resource, sorting)
  |     |                        1x for one alt BOM, or ALT_BOM_COUNT x for "ALL BOM"
  |     |
  |     |-- "DELETE" --> delete_production_version(num_alt_bom, resource, tool, in_sort_lub)
  |     |
  |     '-- "CHANGE" --> change_resource(resource_before, resource_after, tool)   (not used today)
  |
  '-- Continue, Save, write "done mm02"
```

### 2.5 Not in the current flow (reference / future "change" features)

```
change_routing/delete_routing.xaml      --> choose_routing_allocate_bom    (does not delete)
change_capacity.xaml                    --> change_routing/choose_routing
change_capacity_molding.xaml            --> change_routing/choose_routing
change_wc_sap.xaml                      --> delete_routing/choose_routing  (BROKEN path)
production_version/delete_all_pd.xaml       (no calls)
change_routing/delete_product_version.xaml  (no calls)
```

### 2.6 Arguments in detail (what the caller passes)

| Caller | Called file | Argument (direction) = value |
|---|---|---|
| create_routing_mold | nested_find_copy_routing | material(In) = `"Material"`, resource(In) = `"Resource"`, in_sort_lub(In) = `"Sorting/ Lubricant"` or Nothing |
| create_routing_stamping / plt | nested_find_copy_routing | same, in_sort_lub(In) = Nothing |
| create_routing_as / sameinfo | nested_find_copy_routing | material(In), resource(In) only |
| nested_find_copy_routing | find_valid_routing_tocopy | material(In) = material, in_sorting_lubricant(In) = in_sort_lub |
| create_routing_as / stamping / mold | assign_bom_activity | none (so sort_lub = Nothing) |
| main_bom_assignment | choose_routing_allocate_bom | tool(In) = `"Tool"` trimmed, resource(In) = `"Resource"` trimmed, in_sort_lub(In) = sorting, **row_index(Out)** |
| main_bom_assignment | assign_bom_activity | sort_lub(In) = sorting |
| inactive_routing | choose_routing_allocate_bom | tool(In), resource(In), **row_index(Out)** |
| production_version_main | add_pd | group, group_counter = `"group"`, `"group counter"`; resource; tool = `"Tool"` or `"0"`; material; alt_bom_ver = `"Alt Bom"`; alt_bom_count = `CInt("ALT_BOM_COUNT")`; in_sort_lub |
| add_pd | add_production_detail | bom_alt = alt BOM (or 1, 2, ... in the ALL BOM loop), group, group_counter, tool, resource, sorting = in_sort_lub |
| production_version_main | delete_production_version | num_alt_bom = `CInt("ALT_BOM_COUNT")`, resource, tool, in_sort_lub = `"Sorting/ Lubricant"` |
| production_version_main | change_resource | resource_before, resource_after = `"Resource before"`, `"Resource after"`, tool |

Python equivalent of one call, for orientation:

```python
row_index = choose_routing_allocate_bom(session, tool=row.tool, resource=row.resource,
                                        sort_lub=row.sorting)   # -1 = not found
```

How values travel: the top-level file owns the Excel row (`CurrentRow`) and passes **plain strings**
to the child (`CurrentRow("Material").ToString`, etc.). Children never touch Excel. Only two children
return a value: `choose_routing*` return `row_index` (`-1` = not found). The others work on whatever
SAP screen is open (`AttachMode = ByInstance`) - the shared state between workflows is **the SAP screen
itself**, not variables. In Python this becomes: functions that take a session + a typed row object and
return a result; the "current screen" contract must be explicit (pre / post condition per step).

Transactions are only opened in two files (`NSAPCallTransaction`): `create_routing_mold` (`/nCA01`)
and `production_version_main` (`/nmm02`). All others expect the right transaction to be open already.

---

## 3. Create routing (CA01)

### 3.1 Common skeleton (all `create_routing_*.xaml`)

```
for each Excel row:
    if SKIP == "1" or progress == "done ca01": continue          (sameinfo: check commented out)
    bom = "Alt Bom" - 1   (mold: blank / "ALL BOM" -> 0; plt / stp: blank -> 0; as: InputDialog 1/2, see 6)
    type Material, 1901, click "Copy from"
    [as only] read status bar; "MATERIAL STATUS" or "NOT EXIST" -> continue
    invoke nested_find_copy_routing(material, resource, sort_lub)        -> picks the routing to copy (3.2)
    if popup "Choose Alternative BOM": double-click row bom             (which BOM the new routing uses)
    wait 1 s
    type routing description (per department, 4.1)
    read group, group counter -> write to Excel "group", "group counter"
    header details: status 4 + Enter
    [mold, plt, stp] extra Enter (keyboard shortcut)
    operation overview: department-specific entry (4.2)
    [all but plt] CompAlloc -> if popup "Choose Alternative BOM": double-click row bom
                  -> invoke assign_bom_activity (5.1)  (assign_bom_activity saves)
    [plt] Save, no component allocation
    write progress = "done ca01"
```

### 3.2 Choosing the routing to copy (`nested_find_copy_routing` -> `find_valid_routing_tocopy`)

```
nested_find_copy_routing(material, resource, in_sort_lub):
    if popup "Entry Option: Group" (tblSAPLCPSLTCTRL_2110) is shown:     material already has routing groups
        table = extract popup table
        row = first row with Status == "4" and description not containing "TRIAL"
        double-click description cell of row                            -> new GrC inside that group
    invoke find_valid_routing_tocopy(material, in_sort_lub)            (in both branches)
    (argument "resource" is received but not used)

find_valid_routing_tocopy(material, in_sorting_lubricant):
    if popup "Select Type" is shown:
        Continue
        type material (copy from the SAME material) + 1901, Continue
        if list "Entry Option: Group" (tblSAPLCPSLTCTRL_2120) is shown:
            row = first row with Status == "4"
                    and description not containing "TRIAL" / "MDTRIAL"
                    and (no sorting given  or  description contains "YMHI")
            double-click row
    (if "Select Type" does not appear: nothing happens, the caller continues)
```

Notes: `FindIndex` returns `-1` when nothing matches; the click then goes to row `-1` and fails.
The sorting filter only checks for `YMHI`, not for the exact sorting work center (`YMHI-1` etc.).

---

## 4. Department differences (create)

### 4.1 Routing description (`usr/sub/2/txt[1]` on Header Data Check)

| Department / file | Text |
|---|---|
| AS (`create_routing_as`) | `Resource - Material` |
| PLT, STP | `Resource - Material - Tool` |
| MD (`create_routing_mold`) | no sorting: `Resource - Material - Tool`; with sorting: `Resource - Tool - Sorting` |
| sameinfo | `Resource - Material - <tool read from operation row 3>`, typed after Header (F5) |

### 4.2 Operation overview entry (`tblSAPLCPDITCTRL_1400`)

Rows are UiPath `tableRow` values (base to be confirmed, part 1 section 1.1). "WC" = work center column,
"BQ" = base quantity column 5, "detail" = double-click description column 6, which opens Operation Details.

| | AS | PLT | STP | MD | sameinfo |
|---|---|---|---|---|---|
| WC row 1 | Resource | Resource | | | |
| WC row 2 | | | Resource | Resource | Resource |
| WC row 3 | | | Tool | Tool | (read tool) |
| WC row 4 | | | | Sorting (if given) | |
| BQ row 1, 2 | Capacity, Capacity | Capacity, Capacity | | | Capacity, Capacity |
| Machine name | | | | double-click WC row 2 -> Display Work Center -> read `sub/1/txt[2]` -> Back | |
| detail row 2 (machine op) | | | BQ=Capacity, cavity, eff, util | op text=machine name, BQ=Capacity, cavity, eff, util, **setup=1** | |
| detail row 3 (tool op) | | | op text = own WC text, BQ, cavity, eff, util | same as STP | |
| BQ row 4 | | | Capacity x Tool Cavity | sorting: Sorting Capacity; else Capacity x Tool Cavity | |
| BQ row 5 | | | read only (`base_quantity_0040`, unused) | sorting: Capacity x Tool Cavity | |
| Component allocation | yes | **no** (save) | yes | yes | inline: row 0 -> 0020 |

Operation Details fields: `sub/2/txt[2]` WC description (read), `sub/2/txt[4]` operation short text,
`sub/3/txt[3]` base quantity, `sub/3/txt[0]` header qty of the unit conversion (= Tool Cavity),
`sub/3/txt[6]` setup, `sub/15/txt[11]` efficiency, `sub/15/txt[13]` utilization.
This matches `docs/operation_values.md`: 0020 production with eff / util / header = cavity, YMHI
sorting at 0030 shifts the final step (PP94) one row down.

Excel columns per department:

| File | Reads | Writes |
|---|---|---|
| create_routing_as | Material, Resource, Capacity, SKIP, progress | group, group counter, progress |
| create_routing_plt | + Alt Bom, Tool | same |
| create_routing_stamping | + Tool Cavity, Efficiency, Utilization | same |
| create_routing_mold | + Sorting/ Lubricant, Sorting/ Lubricant Capacity | same |
| create_routing_sameinfo | Material, Resource, Capacity, skip | group, group counter, skip=1 |

---

## 5. BOM allocation

### 5.1 `assign_bom_activity(sort_lub)` - assign unassigned components

```
table = extract Material Component Overview (tblSAPLCMDITCTRL_1000)
for each row (index i):
    if Component is blank: break
    if Activity is blank:                                   (not yet assigned)
        select row i, New Assignment
        if description contains carton / sheet / bag / silica / bubble / box
           or (description == "lubricant" and sort_lub in {"YMHI-1", "YMHI"}):  operation = 0030
        else:                                               operation = 0020
        type operation, Continue
Save
```

Same rule as `SAP_automation\change_bom\routing.py` (`planned_operation`), but there it is two passes
(select all 0030 rows, assign once; then 0020) and the lubricant test uses the routing's 0030 work
center. UiPath assigns **one row at a time**. In the CA01 files the workflow is invoked **without**
`sort_lub`, so lubricant always goes to 0020 when created from CA01.

### 5.2 Which alt BOM

| Where | How it is chosen |
|---|---|
| CA01 (mold / plt / stp) | `"Alt Bom" - 1` used as **row index** in "Choose Alternative BOM"; blank -> row 0; mold also `ALL BOM` -> row 0. One alt BOM is allocated in CA01 |
| CA01 (as) | InputDialog "bom alt version for comp alloc" (1 / 2) -> first popup uses the value **as row** (1 = second row), second popup always row 0; `bom_index` computed but unused |
| CA02 `main_bom_assignment` | only rows with `ALT_BOM_COUNT == "2"`: find the routing, CompAlloc, read BOM usage of popup row 1 (`txt[1,0]`). If usage is `2` (row 1 is a usage-2 BOM, not alt BOM 2) -> "check bom again", close, save. Else double-click row 1 (= alt BOM 2) -> `assign_bom_activity(sort_lub)` -> "bom assign" = `done` |

So "all alt BOMs" is done as: CA01 allocates alt BOM 1, then `main_bom_assignment` (CA02) allocates
alt BOM 2. More than 2 alt BOMs is not handled. Rows are picked by **position**, not by the AltBOM value
(`SAP_automation` reads AltBOM at column 19 and matches by value - safer).

### 5.3 Finding the routing in CA02 (`choose_routing` / `choose_routing_allocate_bom`)

```
if header list (tblSAPLCPDITCTRL_1200) is shown:                        group already chosen by SAP
    row = first row whose description contains resource
          and contains tool                (choose_routing: tool optional)
          [allocate_bom: and contains sort_lub if given, and YMHI in text == YMHI in sort_lub]
          and not "TRIAL"
    [choose_routing: row == -1 -> Save, return -1]
    double-click row
elif small group popup (tblSAPLCPSLTCTRL_2110) is shown:                several groups
    row = first popup row whose description contains resource and tool (case-sensitive, no TRIAL filter)
    double-click it, then repeat the header-list search (no sorting filter) and double-click
return row_index (-1 = not found)
```

If neither list appears (SAP opened the single routing directly) `row_index` keeps its initial value
`0`, which every caller reads as "found" and carries on with whatever routing SAP opened (see 8).

---

## 6. Production versions (MM02) - `production_version_main`

```
/nmm02
for each Excel row:
    if progress in ("done mm02", "skip"): continue
    type Material + Enter, Enter (select views)
    status bar contains "MATERIAL STATUS" / "NOT EXIST": continue
    Organizational Levels: Continue;  click ProdVersions
    sort_lubricant = "Sorting/ Lubricant" or Nothing;  tool = "Tool" or "0"
    switch "Action":                        (case-sensitive keys: "Add", "CHANGE", "DELETE"; else nothing)
        "Add":    add_pd(...)
        "CHANGE": change_resource(Resource before, Resource after, Tool)
        "DELETE": delete_production_version(ALT_BOM_COUNT, Resource, tool, Sorting/ Lubricant)
    Continue (close version list), Save, progress = "done mm02", wait 2 s
```

`add_pd`: if `Alt Bom` is not `ALL BOM` -> `add_production_detail(bom_alt = Alt Bom)` once; else repeat
`ALT_BOM_COUNT` times with `bom_alt = 1, 2, ...` (a count, so active alt BOMs 1 and 3 give 1, 2 - wrong
for gaps, see `README.md` Background, SAP facts).

`add_production_detail`:
```
table = extract version list;  max_ver = max(col 0 where < 5000), 0 if none
New Details
version = (max_ver + 1) as "0000";  valid from = today yyyy/MM/dd;  valid to = 9999/12/31
text = resource [+ " - " + tool if tool not "0"/blank] [+ " - " + sorting] + " B" + bom_alt
task list type N;  group;  group counter;  alt BOM = bom_alt;  BOM usage 1
Check, Cancel (F12), Continue
```
Same screens as `SAP_automation\change_bom\production_version.py`. Differences: Python builds the text
from the routing description and checks the 40-character limit, and handles the warning popup
(`wnd[3]`) after Check; UiPath does neither and does not skip existing versions.

`change_resource`: find the version whose Text contains `Resource before` and `Tool`, overwrite that
Text cell with `Resource after - Tool` (no `-1` check; drops the ` B<n>` suffix).

`delete_production_version`: repeat `ALT_BOM_COUNT` times: extract list, first row whose Text contains
resource (and tool, sorting if given) -> select + Delete; none -> stop. Save is done by the main file.
`delete_pd_textdesc` (commented out in main) is the same but matches the exact text `ROUTING_DESCRIPTION`
and versions < 5000.

Stand-alone MM02 files (own Excel): `delete_all_pd` (`Delete prod ver.xlsx`) deletes every version
of the material (always row 0 until a blank Text), writes `progress = done`;
`change_routing/delete_product_version` (`delete_routing_with_description.xlsx`) deletes up to
`ALT_BOM_COUNT` versions whose Text contains `text_description`, saving after each.

---

## 7. Delete / inactive routing (CA02) and changes

### 7.1 `change_routing/inactive_routing.xaml` - the real "delete" (Excel `delete_mold.xlsx`)

```
for each row:
    if progress in ("done ca02", "routing not found"): continue
    Material, 1901 + Enter, Enter
    status bar contains "E3" or "NOT EXIST": done = "skip"; continue
    if operation overview is already open (row 2 col 6 exists):       single routing, list skipped
        Save; progress = "routing not found"; continue
    row = choose_routing_allocate_bom(tool, resource)
    if row != -1:
        Header (F5); tick Deletion flag; status = 1; Save; progress = "done ca02"
    else:
        Save; progress = "routing not found"
```

`change_routing/delete_routing.xaml` is the same loop but, instead of the header steps, clicks
**Material Assignment** (`tbar[1]/btn[31]`) before the search and sets nothing: it marks
`done ca02` without changing the routing. It looks like an unfinished copy; treat `inactive_routing`
as the reference (matches decision "set inactive / status" in `README.md` Background).

OpCenter side: **not in the UiPath project** (no TPM / workflow steps in any XAML).

### 7.2 Changes

| File | Excel | Steps |
|---|---|---|
| `change_capacity` (AS / PLT layout) | `change_capacity_with_resources.xlsx`: Material, Resource, Tool, Capacity after | find routing (`choose_routing`), BQ rows 1 and 2 = Capacity after, `done = done`, Save. No `-1` check (types into whatever screen) |
| `change_capacity_molding` | same file | skip if `done = done`; find routing; `-1` -> Save, `not found`; open 0020 details, read Tool Cavity (`sub/3/txt[0]`), Back; BQ rows 2, 3 = Capacity after, row 4 = Cavity x Capacity after; Save. No sorting case |
| `change_wc_sap` | `change_wc.xlsx`: Material, Resource before / after, Tool | find routing (**invoke path `delete_routing\choose_routing.xaml` does not exist** -> fails); WC row 1 = Resource after (plating); open row 2 col 6 details, copy WC text into op text; Header; description = `Resource after - Material - Tool`; Save |


## 8. Mapping to the Python design (input for the planning session)

| UiPath piece | Python counterpart | Exists? |
|---|---|---|
| CA02 open / group popup / header list | `SAP_automation\change_bom\routing.py` (`open_routing`, `select_group`, `open_header_row`, `find_row`) - matches by group + GrC, not by description | yes |
| `choose_routing*` (match by description: resource, tool, sorting, not TRIAL) | new matcher; better: take group + GrC from Snowflake (`checks/routing_condition`) and reuse `routing.py` | partly |
| `assign_bom_activity` | `routing.py` `assign_components` (two-pass, same rule) | yes |
| Choose Alternative BOM | `routing.py` `open_component_allocation` (by value) | yes |
| MM02 add version | `production_version.py` (`open_production_versions`, `read_versions`, `next_version`, `enter_new_version`, `save_material`) | yes |
| MM02 delete / rename version | new: select row + `wnd[1]/tbar[0]/btn[14]`; text cell col 1 | no |
| CA01 copy-from + routing selection | new (`3.2`) | no |
| Header data / details (description, status, group read) | new | no |
| Department operation entry (4.2) | new: one data-driven layout per department (rows / fields of 4.2) | no |
| Inactive routing (deletion flag + status 1) | new (`7.1`) | no |
| Capacity / work center change | new, same layout table as create | no |
| Status bar / skip checks | `routing.get_status_text` | yes |
