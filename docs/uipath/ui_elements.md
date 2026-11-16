# UiPath project - SAP UI elements (part 1 of 2)

Source: UiPath project `C:\Users\nguyeb3\OneDrive - kochind.com\Documents\UiPath\add routing`
(read 2026-11-16, read-only). Part 2, the logic flow, is in [`../uipath_flows.md`](../uipath_flows.md).

Files in this folder:

| File | What |
|---|---|
| `ui_elements.csv` | **the catalogue**: 101 unique SAP elements (window + ID + cell), with SAP GUI scripting ID, actions, values, files that use them |
| `raw/ui_elements_raw.csv` | every UI activity (265 rows), one per use, in file order |
| `raw/<folder>__<file>.xaml.txt` | each XAML as an indented pseudo-code tree (activities, conditions, selectors, arguments) |

Regenerate (read-only on the UiPath folder):

```powershell
.venv\Scripts\python tools\uipath_dump.py "C:\Users\nguyeb3\OneDrive - kochind.com\Documents\UiPath\add routing" docs\uipath\raw
.venv\Scripts\python tools\uipath_catalog.py docs\uipath\raw\ui_elements_raw.csv docs\uipath\ui_elements.csv
```

`~create_routing_mold.xaml` (Studio autosave copy) is skipped.

---

## 1. How a UiPath selector maps to a SAP GUI scripting ID

Confirmed on all files: every SAP activity has a selector `<sap id='...' />` inside a window scope
`<wnd app='saplogon.exe' cls='...' title='...' />`. **No click is image-, OCR- or coordinate-based**
(all 265 targets have a SAP id; `DesignTimeRectangle` values are only design-time screenshots).

| UiPath | SAP GUI scripting (`session.findById`) | Rule |
|---|---|---|
| scope `cls='SAP_FRONTEND_SESSION'` | `wnd[0]/...` | main window |
| scope `cls='#32770'` (popup) | `wnd[1]/...` | first popup; `Production Version Details` is `wnd[2]` (opened from the overview popup), its warning popup `wnd[3]` |
| `usr/sub?6/btn` | `wnd[0]/usr/sub/6/btn` | `?` is UiPath's wildcard for the subscreen container; `SAP_automation` uses `sub/N` and that runs today |
| `sbar/pane[0]` | `wnd[0]/sbar` (`.text`) | status bar |
| `tbar[1]/btn[7]` | `wnd[0]/tbar[1]/btn[7]` | same |
| `usr/tblX tableCol='5' tableRow='2'` | `wnd[0]/usr/tblX/txt[5,2]` (or `ctxt`) | **verify**: column / row base and cell type, see 1.1 |
| `usr/tblX colTooltip='Work Center' tableRow='2'` | `wnd[0]/usr/tblX/ctxt[<wc col>,2]` | column found by tooltip; its index must be recorded |
| `usr/sub?1/txt[{0},8]` (Choose Alternative BOM) | `wnd[1]/usr/sub/1/txt[row,8]` | list popup: **row first**, then character column position |
| `string.Format("...{0}...", x)` | built at run time | dynamic selector (column `dynamic = yes` in the CSV) |
| Type Into `...[k(Enter)]` / Keyboard Shortcut `[k(Enter)]` | `wnd[n].sendVKey(0)` | Enter |

### 1.1 Open points on table cells (must be checked with the SAP GUI script recorder)

- **Row base.** UiPath writes the operation overview rows as `tableRow='1'`..`'5'`. In the AS / PLT
  routing the capacity goes to rows 1 and 2; in molding the machine is row 2, tool row 3 and the final
  step row 4 (5 with sorting). `SAP_automation` uses 0-based visible rows. Whether UiPath's row 1 is
  SAP row 0 or 1 could not be verified from the XAML alone. The dynamic clicks
  (`tableRow='{0}'` with `FindIndex`, 0-based) suggest UiPath rows are 0-based too, which would make
  row 0 the first operation line. Record one CA02 operation overview to settle it.
- **Cell type.** `txt` vs `ctxt` per column is not in the selector. `SAP_automation.get_cell_text`
  tries both; the same approach works for writing.
- **Scrolling.** UiPath addresses visible rows only. With more operations / versions than fit on the
  screen, row numbers shift. `SAP_automation.find_row` pages through the table; reuse that.

---

## 2. Verification against `SAP_automation\change_bom\docs\for_routing_uipath.md` (CA01)

| for_routing_uipath.md | UiPath (all 5 `create_routing_*.xaml`) | Result |
|---|---|---|
| material field `<sap id='usr/ctxt[0]' />` | `usr/ctxt[0]`, window `Create Routing: Initial Screen`, text `CurrentRow("Material")` | match |
| plant 1901 `<sap id='usr/ctxt[1]' />` | `usr/ctxt[1]`, text `1901` (hard-coded) | match |
| copy from `<sap id='tbar[1]/btn[5]' />` | `tbar[1]/btn[5]`, **double** click | match (Python: one `.press()`) |

Also compared with the IDs used by `SAP_automation\change_bom` (`routing.py`, `production_version.py`);
column `in_sap_automation` in `ui_elements.csv`:

| Area | Same element in both | Note |
|---|---|---|
| CA02 initial screen | `wnd[0]/usr/ctxt[0]`, `ctxt[1]`, `wnd[0]/sbar` | same |
| Group popup | `wnd[1]/usr/tblSAPLCPSLTCTRL_2110` | `SAP_automation`: col 0 group, 1 GrC, 2 description; UiPath double-clicks col 2 - same column |
| Header overview | `wnd[0]/usr/tblSAPLCPDITCTRL_1200` | `SAP_automation`: col 0 GrC, col 1 description; UiPath double-clicks col 1 - same |
| Comp. allocation button | `wnd[0]/tbar[1]/btn[7]` | same |
| Choose Alternative BOM | `wnd[1]/usr/sub/1/txt[row,col]` | UiPath reads col 0 (BOM usage) and clicks col 8 (BOM number); `SAP_automation` reads col 19 (AltBOM) and **finds the row by value**. UiPath picks the row by position (`Alt Bom - 1`) |
| Component table | `wnd[0]/usr/tblSAPLCMDITCTRL_1000` | `SAP_automation`: `chk[0,row]` select, `txt[10,row]` operation, `txt[13,row]` description |
| New assignment | `wnd[0]/tbar[1]/btn[5]` -> `wnd[1]/usr/txt[0]` -> Enter | same |
| Save | `wnd[0]/tbar[0]/btn[11]` | same |
| MM02 | `wnd[0]/usr/ctxt[0]`, `wnd[0]/usr/sub/6/btn`, `wnd[1]/usr/tblSAPLMDIAT_MKAL_NEW`, `wnd[1]/tbar[0]/btn[7]`, all `wnd[2]` detail fields, `wnd[2]/usr/btn`, `btn[12]`, `btn[0]` | **identical**, field for field |

**New (not in `SAP_automation`)**: everything on the CA01 create path after "Copy from"
(copy dialog, `tblSAPLCPSLTCTRL_2120`, header data / details, operation overview
`tblSAPLCPDITCTRL_1400`, operation details `sub/2`, `sub/3`, `sub/15`, work center display), the CA02
deletion flag / status, `btn[31]` material assignment, and the MM02 delete button `btn[14]`.

---

## 3. Catalogue by transaction and screen

Short form of `ui_elements.csv`. IDs are SAP GUI scripting form; `sub/N` = UiPath `sub?N`.
Excel column names are in `"quotes"`.

### 3.1 CA01 - Create routing

| Screen (window title) | ID | Action | Value / meaning |
|---|---|---|---|
| Create Routing: Initial Screen | `wnd[0]/usr/ctxt[0]` | type | `"Material"` |
| | `wnd[0]/usr/ctxt[1]` | type | `1901` |
| | `wnd[0]/usr/ctxt[5]` | type | `"M" + first 7 of material` (commented out: "FOR NO TASK LIST ONLY", group name) |
| | `wnd[0]/tbar[1]/btn[5]` | click | Copy from |
| | `wnd[0]/sbar` | read | error "... material status ..." / "... not exist" -> skip row |
| Entry Option: Group (popup, material already has groups) | `wnd[1]/usr/tblSAPLCPSLTCTRL_2110` | read table | columns Group, GrC, Task list description, Status, Usage, Plnt, From/To lot size, Valid From, Deletion flag |
| | `wnd[1]/usr/tblSAPLCPSLTCTRL_2110/txt[2,row]` | double-click | row picked by `Status = 4` and not `TRIAL` |
| Select Type (popup) | `wnd[1]/tbar[0]/btn[0]` | click | continue (default type = routing) |
| Create Using Copy Function: Select Object to be Copied (popup) | `wnd[1]/usr/ctxt[0]` | type | material to copy from (= same material) |
| | `wnd[1]/usr/ctxt[1]` | type | `1901` |
| | `wnd[1]/tbar[0]/btn[0]` | click | continue |
| Entry Option: Group (copy list) | `wnd[1]/usr/tblSAPLCPSLTCTRL_2120` | read table | columns incl. Status, Description |
| | `wnd[1]/usr/tblSAPLCPSLTCTRL_2120/txt[2,row]` | double-click | routing to copy, see flows 3.2 |
| Choose Alternative BOM (popup) | `wnd[1]/usr/sub/1/txt[row,8]` | double-click | alt BOM row = `"Alt Bom" - 1` (0 for blank / `ALL BOM`) |
| Create Routing: Header Data Check | `wnd[0]/usr/sub/2/txt[1]` | type | routing description, per department (flows 4.1) |
| | `wnd[0]/usr/sub/2/ctxt[0]` | read | group -> `"group"` |
| | `wnd[0]/usr/sub/2/txt[0]` | read | group counter -> `"group counter"` |
| Create Routing: Header Details | `wnd[0]/usr/sub/6/ctxt[1]` | type | status `4` + Enter (display name says 1, value is 4) |
| | `wnd[0]/tbar[1]/btn[7]` | click | Operations (sameinfo only) |
| Create Routing: Operation Overview | `wnd[0]/usr/tblSAPLCPDITCTRL_1400` work center column, row 1-4 | type / read / double-click | `"Resource"`, `"Tool"`, `"Sorting/ Lubricant"` (rows per department, flows 4.2) |
| | `.../tblSAPLCPDITCTRL_1400` col 5, row 1-5 | type / read | base quantity: `"Capacity"`, `"Sorting/ Lubricant Capacity"`, `Capacity * Tool Cavity` |
| | `.../tblSAPLCPDITCTRL_1400` col 6, row 2 / 3 | double-click | open operation details (machine / tool line) |
| | `wnd[0]/tbar[1]/btn[5]` | click | Header (F5) |
| | `wnd[0]/tbar[1]/btn[7]` | click | CompAlloc |
| | `wnd[0]/tbar[0]/btn[11]` | click | Save (PLT saves here, no component allocation) |
| Display Work Center: Basic Data | `wnd[0]/usr/sub/1/txt[2]` | read | work center description (machine name) |
| | `wnd[0]/tbar[0]/btn[3]` | click | Back |
| Create Routing: Operation Details | `wnd[0]/usr/sub/2/txt[2]` | read | work center description (tool line) |
| | `wnd[0]/usr/sub/2/txt[4]` | type | operation short text = machine / tool description |
| | `wnd[0]/usr/sub/3/txt[3]` | type | base quantity `"Capacity"` |
| | `wnd[0]/usr/sub/3/txt[0]` | type | header qty in unit conversion = `"Tool Cavity"` |
| | `wnd[0]/usr/sub/3/txt[6]` | type | setup standard value `1` (mold only; commented in stamping) |
| | `wnd[0]/usr/sub/15/txt[11]` | type | `"Efficiency"` |
| | `wnd[0]/usr/sub/15/txt[13]` | type | `"Utilization"` |
| | `wnd[0]/tbar[0]/btn[0]` / `btn[3]` | click | Enter / Back |
| Create Routing: Operation - Check | `wnd[0]/tbar[0]/btn[0]` | click | Enter (commented out) |
| Material Component Overview | see 3.3 | | |

### 3.2 CA02 - Change routing

| Screen | ID | Action | Value / meaning |
|---|---|---|---|
| Change Routing: Initial Screen | `wnd[0]/usr/ctxt[0]`, `ctxt[1]` | type | material, `1901` + Enter |
| | `wnd[0]/sbar` | read | contains `E3` or `NOT EXIST` -> skip (delete flows) |
| Change Routing: Overview (header list) | `wnd[0]/usr/tblSAPLCPDITCTRL_1200` | exists? / read table | Task list description ... |
| | `.../tblSAPLCPDITCTRL_1200/txt[1,row]` | double-click | open the matched GrC |
| Entry Option: Group (small popup) | `wnd[1]/usr/tblSAPLCPSLTCTRL_2110`, `txt[2,row]` | read / double-click | pick group by description |
| Change Routing: Operation Overview | `.../tblSAPLCPDITCTRL_1400/txt[6,2]` | exists? | "is the operation overview open directly" (single routing) |
| | `.../tblSAPLCPDITCTRL_1400` col 5 rows 1-4 | type | capacity change |
| | `.../tblSAPLCPDITCTRL_1400` work center col rows 1-2 | type | work center change |
| | `wnd[0]/tbar[1]/btn[31]` | click | material assignment (delete_routing only) |
| | `wnd[0]/tbar[1]/btn[5]` | click | Header |
| | `wnd[0]/tbar[1]/btn[7]` | click | CompAlloc |
| | `wnd[0]/tbar[0]/btn[11]` | click | Save |
| Change Routing: Operation Details | `wnd[0]/usr/sub/2/txt[2]` read, `sub/2/txt[4]` type, `sub/3/txt[0]` read (cavity), `tbar[0]/btn[3]` back | | |
| Change Routing: Header Details | `wnd[0]/usr/sub/6/chk` | click | **Deletion flag** |
| | `wnd[0]/usr/sub/6/ctxt[1]` | type | status `1` |
| | `wnd[0]/usr/sub/2/txt[1]` | type | new description (`change_wc_sap`) |

### 3.3 Component allocation (CA01 and CA02)

| Screen | ID | Action | Value / meaning |
|---|---|---|---|
| Choose Alternative BOM (popup) | `wnd[1]/usr/sub/1/txt[row,8]` | double-click | BOM row |
| | `wnd[1]/usr/sub/1/txt[1,0]` | read | BOM usage of the 2nd row |
| | `wnd[1]/tbar[0]/btn[12]` | click | "Choose (F2)" / close |
| Routing Change / Material Component Overview | `wnd[0]/usr/tblSAPLCMDITCTRL_1000` | read table | Component, Activity, Material Description ... |
| | `.../tblSAPLCMDITCTRL_1000` row `{i}` (row selector) | click | select component row |
| | `wnd[0]/tbar[1]/btn[5]` | click | New Assignment |
| New Assignment (popup) | `wnd[1]/usr/txt[0]` | type | `0030` or `0020` |
| | `wnd[1]/tbar[0]/btn[0]` | click | continue |
| | `wnd[0]/tbar[0]/btn[11]` | click | Save |

### 3.4 MM02 - Production versions

| Screen | ID | Action | Value / meaning |
|---|---|---|---|
| Change Material (Initial Screen) | `wnd[0]/usr/ctxt[0]` | type | material + Enter, then Enter again (select views) |
| | `wnd[0]/sbar` | read | `MATERIAL STATUS` / `NOT EXIST` -> skip |
| Organizational Levels (popup) | `wnd[1]/tbar[0]/btn[0]` | click | continue |
| Change Material ... (MRP view) | `wnd[0]/usr/sub/6/btn` | click | ProdVersions |
| Production Version Overview (popup) | `wnd[1]/usr/tblSAPLMDIAT_MKAL_NEW` | read table | col 0 version, `Text` ... |
| | `.../tblSAPLMDIAT_MKAL_NEW` col 1 row `{i}` | click / type | select a version / overwrite its text (`change_resource`) |
| | `wnd[1]/tbar[0]/btn[7]` | click | New Details |
| | `wnd[1]/tbar[0]/btn[14]` | click | **Delete** version |
| | `wnd[1]/tbar[0]/btn[0]` | click | continue (close) |
| Production Version Details (popup) | `wnd[2]/usr/ctxt[0]` | type | version = max(<5000) + 1, `0000` format |
| | `wnd[2]/usr/ctxt[1]` / `ctxt[2]` | type | valid from today `yyyy/MM/dd` / `9999/12/31` |
| | `wnd[2]/usr/txt[0]` | type | text `Resource[ - Tool][ - Sorting] B<alt bom>` |
| | `wnd[2]/usr/cmb[1]` | type | `N` (routing task list type; Python: `.key = "N"`) |
| | `wnd[2]/usr/ctxt[3]` / `txt[4]` | type | `"group"` / `"group counter"` |
| | `wnd[2]/usr/ctxt[6]` / `ctxt[7]` | type | alt BOM / BOM usage `1` |
| | `wnd[2]/usr/btn` | click | Check |
| | `wnd[2]/tbar[0]/btn[12]`, `btn[0]` | click | cancel (red cross), continue |
| Change Material ... | `wnd[0]/tbar[0]/btn[11]` | click | Save |
