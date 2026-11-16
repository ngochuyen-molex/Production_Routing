# Migrating the routing automation from UiPath to Python - context and handover

Status: **planning** (2026-11-16). No migration code written yet. This file collects everything
decided or learned so far so that a new session can pick it up. Read it fully before starting.

Next steps, in order:
1. ~~New session: read the UiPath project~~ **done 2026-11-16**: `docs/uipath_flows.md` (logic flow,
   call graph, conditions, defects) and `docs/uipath/ui_elements.md` + `docs/uipath/ui_elements.csv`
   (SAP element catalogue with SAP GUI scripting IDs). Regenerate with `tools/uipath_dump.py` and
   `tools/uipath_catalog.py`.
2. **Planning session: design the architecture** on top of that map (open design questions in section 7;
   `docs/uipath_flows.md` section 9 maps UiPath pieces to existing / new Python).
3. Only after the user agrees with the design: implementation, one branch at a time.

The user wants clean, extensible code and to review a plan (with a readable HTML view, like
`docs/proposed_structure.html`) before anything is implemented.

---

## 1. Goal

Today:
- **This repo (`ROUTING`)** checks request data against SAP (via Snowflake) and writes results to
  Excel, and generates OpCenter (MES) upload files (Tool Plan Matrix, workflows).
- **UiPath** does the actual SAP data entry (SAP GUI): create / change routings, assign BOM
  components, production versions, capacity / work center changes.

Target: **one Python tool runs the whole routing lifecycle**, so UiPath is no longer needed. UiPath
keeps running until each Python branch is proven.

Future features the design must make easy to add (user's examples):
- update capacity, update work center (the work center row differs per department too),
- rename routings and production versions.

## 2. The lifecycle

**Create a routing**
1. Pre-checks (exist today): routing exists / inactive, material at plant, alt BOM count,
   operation values, production version exists.
2. Create the routing in SAP: **CA01** (new routing group) or **CA02** (new group counter in an
   existing group). Operation screens differ per department.
3. Allocate BOM components (CA02 component allocation): **all alt BOMs** or **one specific alt BOM**.
4. Create the production version(s) in **MM02**: for that alt BOM, or one per alt BOM.
5. Generate the OpCenter upload files: Tool Plan Matrix (`routing opc add-tpm`) and workflow
   (`routing opc add-workflow`).

**Delete a routing** (mirror image)
1. Set the routing inactive in SAP (deletion flag) and set its status. The exact steps are in UiPath.
2. Deal with its production version(s).
3. OpCenter: remove the TPM rows (`routing opc delete-tpm` exists) and set the workflow status /
   inactive (no Python generator yet; steps are in UiPath).

## 3. Variation dimensions (they combine)

| Dimension | Values | What changes |
|---|---|---|
| Action | create, delete; later change (capacity, work center, names) | transaction + steps |
| Transaction | CA01, CA02, MM02 | different screens and flow each |
| Department | MD (molding), AS (assembly), PLT (plating), STP (stamping) | operation screens differ: which row / field holds capacity, base quantity, work center |
| Routing variant | e.g. "same info" copy, find a valid routing to copy | how the routing is created |
| BOM allocation | all alt BOMs / one alt BOM | component allocation step |
| Downstream | production version, TPM, workflow | follow from the SAP result, also on delete |

Example: CA02 + MD + alt BOM 2 -> production version B2 -> TPM -> workflow.
The design should treat each dimension as a swappable piece (e.g. a per-department "operation screen
layout"), not one script per combination as UiPath does now.

## 4. Existing assets

### 4.1 This repo (`C:\Users\nguyeb3\Downloads\ROUTING`)
Layout and rules: `README.md`. Layers: `core` (config, DB, cleaning, Excel) -> `data` (SQL only, one
module per SAP domain, intentional) -> `checks` / `opc` -> `pipelines` -> `cli` (`routing` command,
defined in `pyproject.toml` `[project.scripts]`). Imports only go downward; SQL uses bound params.

| Piece | What it does | Doc |
|---|---|---|
| `checks/routing_condition.py` | routing exists? `SKIP` 0 safe to add, 1 exists, 2 material not at plant, **3 inactive** (deletion flag `PLKO.DELKZ` set, still in SAP: untick to reactivate; an active routing wins over a flagged one) | - |
| `checks/alt_bom.py` | `ALT_BOM_COUNT` (active alt BOMs, `MAST`/`STKO`, usage 1, status 01) | - |
| `checks/operation_values.py` | base quantity per operation role, standard values, efficiency / utilization | `docs/operation_values.md` |
| `checks/pv_exist.py` | production version exists for routing + `Alt Bom` (number only; ALL BOM listed, not checked) | `docs/production_version.md` |
| `checks/production_version.py` | pv-count / by-group / by-attributes / fallback lookups (deleted versions excluded) | `docs/production_version.md` |
| `checks/delete_status.py` | delete flag at operation 0020 | - |
| `opc/add_tpm.py`, `delete_tpm.py`, `update_tpm_priority.py` | Tool Plan Matrix upload files | `docs/opc.md` |
| `opc/add_workflow.py`, `compare_workflow.py` | MES workflow upload files / comparison | `docs/opc.md` |
| `pipelines/pre_uipath.py` | routing condition -> alt BOM count, run before UiPath | `README.md` |

### 4.2 `C:\Users\nguyeb3\Downloads\SAP_automation\change_bom`
Python **SAP GUI scripting** (`win32com`, `connect.get_session()`), so the technical route is
settled: SAP GUI scripting, not RFC/BAPI.
- `production_version.py`: MM02 production versions (open material, read versions, next number,
  enter version, save, read popups, skip previous successes).
- `routing.py`, `routing_main.py`, `routing_sf.py`: CA02 routing handling incl. component allocation.
- `bom.py`, `bom_create.py`: CS02 / CS01 BOM change / create.
- Docs: `docs/routing.md`, `docs/workflow.md`, `docs/TODO.md`, `docs/TODO_bug.md` (known problems),
  `archive/docs/routing_altbom_plan.md`.
Earlier plan: this folder may be merged into `ROUTING` later.

### 4.3 UiPath project
Folder: `C:\Users\nguyeb3\OneDrive - kochind.com\Documents\UiPath\add routing` (read-only).
Full map: `docs/uipath_flows.md`. Key findings:
- `main.xaml` is empty: every workflow is run on its own, each with a hard-coded Excel path.
- All SAP actions use SAP element ids (no image / coordinate clicks); UiPath `usr/sub?N/...` =
  scripting `wnd[0]/usr/sub/N/...`. MM02 production version IDs are identical to `SAP_automation`.
- No error handling at all; several defects (broken invoke in `change_wc_sap`, `delete_routing.xaml`
  does not delete, positional alt BOM rows) - list in `docs/uipath_flows.md` section 8.
- OpCenter delete steps are **not** in the UiPath project.

Seen in the project tree (screenshot, 2026-11-16):
- `main.xaml`, `project.json`
- `add_routing/`: `create_routing_as.xaml`, `create_routing_mold.xaml`, `create_routing_plt.xaml`,
  `create_routing_stamping.xaml`, `create_routing_sameinfo.xaml`, `find_valid_routing_tocopy.xaml`,
  `nested_find_copy_routing.xaml`
- `bom_assign/`, `change_routing/`, `production_version/` (folders)
- `change_capacity_molding.xaml`, `change_capacity.xaml`, `change_wc_sap.xaml`
- dependencies: UiPath.Excel, IntegrationService, Python, System, UIAutomation activities
- `create_routing_mold.xaml` starts SAP GUI (`saplogon.exe`), opens the Excel input
  (`Downloads\add_...xlsx`), calls transaction `CA01` (`/n`), then loops "For Each Excel Row".

## 5. Decisions so far

| Topic | Decision |
|---|---|
| SAP access | SAP GUI scripting from Python (as in `SAP_automation`) |
| Input | **one Excel file with an `Action` column** (Create / Delete, later Change); a file with one action just runs that branch; optional `--only create` |
| Order inside a run | deletes before creates for the same material |
| Branching | dispatch on Action + Transaction + Department + BOM allocation, not one script per combination |
| Results | written back per row and step (e.g. `RESULT_ROUTING`, `RESULT_PV`, `RESULT_TPM`, `RESULT_WORKFLOW`); reruns skip rows that already succeeded |
| Migration order | production version step first (reuse `pv-exist` + `SAP_automation` MM02 code), then a single `routing create` / `routing delete` pipeline, then routing + component entry off UiPath |
| Delete in SAP | set inactive / status as UiPath does: CA02 Header (F5) -> tick deletion flag `usr/sub/6/chk` -> status `1` -> Save (`change_routing/inactive_routing.xaml`, see `docs/uipath_flows.md` 7.1) |
| ALL BOM | not automated yet: a routing may already have some alt BOM versions (avoid duplicates); see `docs/production_version.md` |

## 6. SAP facts learned (plant 1901, Snowflake `MLX_DATALAKE.MLX_SAP_ECC`)

- **Delete fields**: `PLKO.DELKZ = 'X'` = deletion flag tick box, reactivatable;
  `DW_SOFT_DELETE_FLAG = 1` = gone from SAP (history only); `MAPL.LOEKZ = 'X'` = material
  assignment deleted; `PLKO.LOEKZ = 'X'` = header deleted. Example: 522690630 GC 15 flagged,
  still in SAP; GC 16 flagged and permanently deleted.
- **Operation roles**: production = 0020 (`PP01`; a few at 0030); sorting / lubricant = work
  center `YMHI*` with `PP96` at 0030; final step = `PP94` (always last: 0030-0060) or `ZP04`.
  YMHI at 0020 is production (hi-coat, regrinding). Details and gaps: `docs/operation_values.md`.
- **Standard values** (`PLPO`): setup / machine / labor = `VGW01-03`, units `VGE01-03`,
  activity types `LAR01-03`; header/operation unit conversion `UMREZ` / `UMREN`.
- **Production versions** (`MKAL`): `VERID`, routing `PLNNR` + `ALNAL`, alt BOM `STLAL`,
  lock `MKSP`, valid `ADATU`-`BDATU`, text like `MF50-09 - L501330A B1`. MM02 shows them per material.
- **Alt BOM count is a count, not the numbers**: active alt BOMs 1 and 3 give count 2.

## 7. Open design questions (for the planning session)

- How to model the per-department screen differences (data-driven layout table vs one class per department).
- One "step" abstraction shared by SAP steps (CA01/CA02/MM02) and file steps (TPM, workflow)?
- Where SAP GUI element IDs live (code constants vs config file) so screen changes are a one-place fix.
- Error handling and recovery in SAP GUI: popups, locks, a half-finished routing, restart from the last good step.
- A dry-run / check-only mode before writing to SAP.
- How results and logs are written (per row, per step) and how UiPath and Python co-exist during migration.
- Folding `SAP_automation` into this repo: same layers or a new `sap/` layer below `checks` / `opc`.
- Remaining branches beyond those listed in section 3: ask the user.

## 8. Brief for the next session: map the UiPath project

Goal: understand, not code. Produce `docs/uipath_flows.md`.

XAML files are XML text and can be read directly. SAP activities store selectors like
`<sap id='usr/ctxtRC27M-MATNR' />`; the `usr/...` part is the same element ID SAP GUI scripting
uses (`session.findById("wnd[0]/usr/...")`). Confirm this on the first file instead of assuming it.
Clicks recorded by image or screen position have no ID: list them, they must be re-recorded with
the SAP GUI script recorder.

For each `.xaml` (start with `main.xaml` to see how the others are called):

| Field | Content |
|---|---|
| Purpose | what it does, when `main` calls it, arguments in / out |
| Transaction(s) | CA01 / CA02 / MM02 / other, prefix (`/n`, `/o`) |
| Excel input | file, sheet, columns read, columns written back |
| Screen sequence | step by step: screen, action (type / click / select / key), element ID, value source |
| Branches | conditions (If / Switch / Flow Decision) and what differs |
| Popups / errors | expected popups, retries, Try Catch, status bar checks |
| Non-ID clicks | image / coordinate / anchor based actions |

Then summarise across files:
- the **department differences**: which operation row / field holds capacity, base quantity, work
  center per MD / AS / PLT / STP;
- **BOM allocation**: all alt BOMs vs one, and how the alt BOM is chosen;
- **delete / inactive** steps in SAP and OpCenter;
- what already exists in `SAP_automation\change_bom` (same transaction / screens) and what is new;
- risks / barriers found.

Do not change any file in the UiPath project or `SAP_automation`.
