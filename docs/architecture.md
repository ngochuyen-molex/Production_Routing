# Routing automation in Python - architecture (draft for review)

Status: **routing, components and pv phases built and run against SAP on test rows** (2026-11-19); opc phase not built. Open items: `docs/verification.md`.
Background, decisions and SAP facts: `README.md` (Background: replacing UiPath). UiPath behaviour being replaced: `docs/uipath_flows.md`.

## 0. Implementation status

| Part | Files | State |
|---|---|---|
| model | `model/` (enums, entities, requests, result, row_state) | built, tested |
| pipeline | `pipelines/run.py`, `recipes.py`, `workbook.py` (in the existing `pipelines/` folder, not a new `pipeline/`) | built, tested; `routing run FILE --dry-run` checked against Snowflake |
| SAP core | `sap/session.py`, `elements.py`, `table.py` | built, **not run against SAP** |
| routing phase | `sap/screens/ca01.py`, `ca02.py`, `operations.py`, `layouts/`, `resolve/routings.py`, `steps/routing.py` (`CreateRouting`, `InactivateRouting`) | built, fake-SAP tests; open element ids: `docs/verification.md` |
| components phase | `sap/screens/components.py`, `steps/components.py` (`AllocateComponents`) | built (screen code + 0030 / 0020 rule copied from `SAP_automation`), plan tested, **not run against SAP** |
| pv phase | `sap/screens/mm02.py`, `steps/production_version.py` (`CreateProductionVersion`, `DeleteProductionVersion`), `data/bom.alt_bom_numbers` | built (MM02 create copied from `SAP_automation`; delete button confirmed in 4 UiPath flows), plan tested + dry run on Snowflake |
| opc phase | - | not built |

Scope = the UiPath files the user runs (`docs/uipath_flows.md` 1.1) and what they invoke:

| UiPath | Python | State |
|---|---|---|
| `create_routing_as` / `_plt` / `_stamping` / `_mold` + `nested_find_copy_routing`, `find_valid_routing_tocopy` | Action `Add`, layouts AS / PLT / STP / MD / MD_SORTING, `CreateRouting` | built |
| `create_routing_sameinfo` | - | **backlog**: not in the code (removed 2026-11-18), design in section 9 |
| `assign_bom_activity` (inside create) | `AllocateComponents` | built |
| `bom_assign/main_bom_assignment` + `choose_routing_allocate_bom` | Action **`Assign Components`** -> `AllocateComponents` on an existing routing | built (2026-11-18) |
| `change_routing/inactive_routing` | Action `Delete` -> `InactivateRouting` | built |
| `production_version_main`: Add (`add_pd`, `add_production_detail`), DELETE (`delete_production_version`) | `CreateProductionVersion`, `DeleteProductionVersion` | built |
| `change_resource` | - | **backlog**: planned as Delete old + Create new (section 9) |
| `delete_pd_textdesc`, `delete_all_pd`, `delete_product_version`, `delete_routing`, `change_capacity*`, `change_wc_sap`, `change_routing/choose_routing` | - | **out of scope** (not run / not invoked by the files above) |

Assign Components (UiPath `main_bom_assignment`): the routing is found like Delete (group / group
counter, else resource + tool + sorting; several matches -> skip, never guess; flagged -> skip);
alt BOM from `Alt Bom` (number or ALL BOM). UiPath only ran rows with `ALT_BOM_COUNT = 2` and always
alt BOM 2; that filter is dropped.

**Verification checklist** (what is checked, what is still open, popup branching, element ids,
copy source rules, blank values, final step): **[docs/verification.md](verification.md)** - the only place.

Production versions (pv phase):
- **Create**: one version per wanted alt BOM **that has none yet** on the routing. `ALL BOM` =
  the material's **real active alt BOM numbers** (`data/bom.alt_bom_numbers`, not the count), minus
  the ones that already have a version -> a partly done routing is completed, never duplicated
  (solves the ALL BOM concern of `docs/production_version.md`; example: M5013300/34 has B1 + B2 ->
  only B3 planned). Text = routing description + ` B<n>`, shortened like `SAP_automation` (drop
  ` - <material>` when over 40). Next number = highest below 5000 + 1. Trial routings: no version.
- **Delete**: the versions of the routing found by the routing phase, **by version number from
  Snowflake** (UiPath matched text). Order inside a Delete row follows the phases: the routing is
  inactivated first, then its versions are deleted (earlier assumption "versions first" dropped).
- A routing created in this run is not in Snowflake yet: components / pv use the in-memory routing
  from `CreateRouting`; on a rerun within ~15 min it is rebuilt from the row's layout description.

Components phase:
- Only Create rows whose layout allocates components (not PLT) and `Assign Components` not "No";
  one CA02 pass per alt BOM (one alt BOM, or every active one for ALL BOM), alt BOM picked by value.
- Rule copied as is: packaging -> 0030, lubricant -> 0030 when the 0030 work center is YMHI /
  YMHI-1, else 0020; only unassigned rows are touched (safe to rerun).
- Only the visible page of the component table is read (as `SAP_automation`); a warning is written
  when the table has more rows.

Choices made while building:
- **Planning reads all routings of the input materials once** (`data/routing.routing_operations`:
  status, deletion flag, operations), then decides per row with the entity methods (section 5.5):
  existing routing (routing condition rule, active before flagged), copy source (status 4, not
  flagged, not TRIAL, layout-compatible first, then same resource, then newest counter), group size.
- **Create skips** when the routing already exists (`routing already exists G/C`) or is
  deletion-flagged (`routing inactive G/C, untick the deletion flag`); the key is still kept for
  later phases.
- **Delete never guesses**: the routing is found by the routing condition rule (Resource = work
  center of an operation, Tool / Sorting in the description), or by `group` / `group counter` when
  filled. `Dept` stays required on Delete rows.
  Some departments (e.g. **PLT**) have no tool or lubricant to tell routings apart, so when more
  than one active routing matches, the row is skipped with `N routings match (G/C, ...), fill
  group / group counter` instead of deleting the first match.
- **Copy source**: rules in `docs/verification.md` C (a source with the wrong sorting shape is
  never copied; a layout misfit otherwise is a Plan warning).
- **Copy source override**: the planner writes its pick to `COPY_FROM_PLANNED` (information only).
  To copy from another routing, type group / counter in `COPY_FROM_GROUP` / `COPY_FROM_GC`; only
  the user fills these, so the planner's own pick never becomes a fixed override. An override must
  still be a valid source (status 4, not flagged, not TRIAL), else the row is skipped.
  Today the override is always a routing of the **same material**; copying from another material
  is a logged future branch (section 9, "Copy from another material").
- **TRIAL** (decided 2026-11-17): a TRIAL / MDTRIAL routing is **never a copy source**
  (`Routing.can_be_copied`), but it **does count** when checking whether a routing exists or which
  routing a Delete row means - same as `checks/routing_condition`.
- **Request params** (renamed from "spec" 2026-11-17, to avoid confusion with the OpCenter / TPM
  `Spec` column): `Request` = common columns, `request.params` = what one action needs
  (`CreateParams`: capacity, cavity, eff, util, sorting, alt BOM; `DeleteParams`: nothing yet).
- **CA01 saves without component allocation**: components are their own phase (section 4.1).
- **A failed step** resets SAP (`/n`, no save), is written as `Failed: ...` and blocks the later
  phases of that row; the file is saved after every row and the run stops if it cannot be saved
  (Excel open), so no SAP work goes unrecorded.

### 0.1 Why the copy source is chosen before the run (not in the SAP popup)

CA01 "Copy from" needs one existing routing of the **same material** to copy. UiPath picks it
**inside the SAP popups** while the run is going: first row with status 4, not `TRIAL`, `YMHI` in
the text when the request has sorting (`uipath_flows.md` 3.2). Python picks it **in the planner,
from Snowflake, before SAP is touched**, with the same conditions, and CA01 then selects exactly
that group + counter in the popup. Reasons:

| | UiPath (pick in the popup) | Python (pick in the planner) |
|---|---|---|
| visible before it happens | no - known only after the routing is created | yes - Plan sheet and `COPY_FROM_*` columns, also in `--dry-run` |
| can be changed by the user | no | yes - type another group / counter |
| checks the copied operations fit the layout | no - wrong source = values typed on the wrong rows | yes - `check_copy_source` (sorting step, final step) |
| how the row is picked | by position: first matching row on the visible page | by value: group + counter, through all pages |
| nothing matches | clicks row -1, the run stops | row skipped / warned with a reason, other rows go on |
| choice between several valid sources | always the first one | ranked: layout fits, same resource, newest counter |

What stays the same: always the same material, status 4, no TRIAL / MDTRIAL, YMHI when sorting.
Risk: Snowflake is ~15 min behind SAP, so a routing changed in the last minutes can be chosen
wrongly; CA01 fails safely in that case (source not in the popup -> step `Failed`, nothing saved).

### 0.2 Overlap with existing checks (review 2026-11-17)

"Which routing does this Excel row mean?" is implemented six times, with different rules:

| Where | Resource matched on | Tool / sorting | TRIAL excluded | Deletion flag |
|---|---|---|---|---|
| `checks/routing_condition.py` | **work center of an operation** (`CRHD.ARBPL`), exact | description contains Tool, WorkCenter, Sorting | no | active wins (SKIP 3) |
| `checks/operation_values.py` | work center, exact | description contains Tool | no | not read |
| `checks/delete_status.py` | work center at 0020, exact | - | no | reported |
| `checks/routings_by_tool.py` | - | description contains Tool | no | - |
| `checks/production_version.py` (by attributes) | work center set of the version | **PRT** (tool / lubricant assigned to the operation) | no | - |
| `resolve/routings.py` (first version) | description contains resource | description contains tool / sorting | yes | active wins |

The first version of the resolver was a seventh variant; it now uses the routing condition rule
(resource = real work center) through the shared entity methods below.

**Progress (2026-11-17):** section 5.5 is built for the first part:
- the rule now lives once on the entities: `Routing.matches` (= the routing condition rule),
  `Routing.operation(role)`, `Routing.can_be_copied`, `MaterialRoutings.matching / copy_source /
  group_size`, `MaterialVersions.on / has / missing / next_number`, `ProductionVersion.text_for`;
- switched to it: `checks/routing_condition.py`, `checks/pv_exist.py` (also uses `AltBomChoice`),
  the planner (`steps/routing.py`), `layouts/select.check_copy_source`;
- **before / after on real data**: both checks gave identical output for the same input
  (8 routing condition rows incl. inactive / not at plant, 4 pv rows incl. ALL BOM / blank group);
- still own logic, to switch next (each with a before / after run): `checks/operation_values.py`
(matching + roles: final = PP94 only in both, ZP04 = trial routing, see `docs/operation_values.md` gap 3), `checks/delete_status.py`,
  `checks/routings_by_tool.py`, `checks/production_version.py` lookups.

Other overlaps:
- `data/routing.routing_operations` (new) returns a superset of `routings_with_resource` and
  `deleted_status_0020`; the old ones can be derived from it once the checks share the matcher.
- `checks/pv_exist` Alt Bom parsing: **done**, uses `AltBomChoice.parse`.
- Operation roles: `checks/operation_values.pick_operations` (0020 / YMHI / PP94) and
  `layouts/select.check_copy_source` (YMHI / PP94) define the same roles in two places (same rules now).
- Future pv phase must reuse `data/production_version.by_routing` and `data/bom` (not new queries).

---

## 1. The idea in plain words

You give the tool **one Excel file**. Each row is one request: "create this routing", "delete that
routing", later "change capacity", and so on.

The tool works in **phases**, always in the same order:

| # | Phase | What happens | SAP transaction |
|---|---|---|---|
| 1 | `routing` | create, change or inactivate the routing | CA01 / CA02 |
| 2 | `components` | allocate BOM components to operations (optional) | CA02 |
| 3 | `pv` | add or delete production versions | MM02 |
| 4 | `opc` | build the Tool Plan Matrix and workflow upload files | none (Excel) |

You can run **all phases**, or **only some** of them. Every phase reads what earlier phases wrote
in the same Excel file, so phases can also run on different days.

For every row the tool **first plans, then acts**:

1. **Plan**: read the row, look up SAP data in Snowflake (does the routing exist, which routing to
   copy from, which alt BOMs, which production versions already exist) and decide which steps it
   will do. The plan is written to a **Plan** sheet. With `--dry-run` it stops here, so you can
   check the plan before SAP is touched.
2. **Act**: run the planned steps in SAP, write the result of each step to the row, and save the
   file after every row, so a crash or a rerun never repeats work that already succeeded.

## 2. How you run it

```powershell
routing run FILE                                  # all phases
routing run FILE --dry-run                        # plan only, nothing written to SAP
routing run FILE --phase routing                  # only create / change / inactivate routings
routing run FILE --phase components               # only component allocation
routing run FILE --phase pv                       # only production versions
routing run FILE --phase routing --phase pv       # several phases
routing run FILE --only add                       # only rows with Action = Add (also: delete, "assign components")
routing run FILE --rows 5-12                      # only these Excel rows (for tests)
```

Rules:
- Phases always run in the order of section 1, whatever order you type them in.
- A row only gets the phases that **apply** to it, e.g. PLT has no component allocation and a
  Delete row has no `components` phase (section 4).
- A step that already succeeded (its result column says `Done`) is skipped on a rerun.

## 3. How data passes between phases

Everything a phase needs about "which routing" is the **routing key**:
`Material + group + group counter` (e.g. `5013300800 / M5013300 / 34`).

```
          Excel row (input)                    Plan sheet / row columns (written)
          ─────────────────                    ──────────────────────────────────
          Action, Material, Resource,   ──►    plan:    COPY_FROM_GROUP, COPY_FROM_GC, ALT_BOMS, STEPS
          Tool, Dept, Capacity, Alt Bom,       results: group, group counter      (routing phase)
          Tool Cavity, Sorting, ...                     RESULT_ROUTING            (routing phase)
                                                        RESULT_COMPALLOC          (components phase)
                                                        RESULT_MM02               (pv phase)
                                                        RESULT_OPC                (opc phase)
```

Where a phase gets the routing key:

| Situation | Routing key comes from |
|---|---|
| `routing` phase creates the routing in this run | the SAP screen (CA01 shows the new group / counter), written to `group`, `group counter` |
| a later phase runs in the same run | the row (just written by the routing phase) |
| a later phase runs on its own, another day | the `group` / `group counter` columns in the file; if blank, looked up in Snowflake (like `check routing-condition`) |
| Delete rows | looked up in Snowflake before SAP is touched (the routing has existed long enough) |

So phases never talk to each other directly. They share **one row object**, and the row is saved
to Excel after each step.

## 4. Which steps a row gets

Steps per phase and action (✓ = the step applies; conditions in brackets):

| Phase | Create | Delete | Change capacity (later) | Change work center (later) |
|---|---|---|---|---|
| routing | `CreateRouting` (CA01, copy from same material) | `InactivateRouting` (deletion flag + status 1) | `ChangeCapacity` | `ChangeWorkCenter` |
| components | `AllocateComponents` (only some rows, see 4.1) | - | - | - |
| pv | `CreateProductionVersion` (for the alt BOM, skip if it exists) | `DeleteProductionVersion` | - | `RenameProductionVersion` |
| opc | `AddTpm`, `AddWorkflow` | `DeleteTpm`, `InactivateWorkflow` | `UpdateTpmCycleTime` | - |

Order inside a run: **all deletes first, then creates** (a resource / tool swap often has both for
one material). Inside a Delete row: the routing is inactivated first, then its production versions
are deleted (phase order; section 0).

### 4.1 Component allocation is not a fixed follow-up of the routing phase

`AllocateComponents` only applies to some rows; `applies()` decides, so it never runs just
because the routing phase ran:

| Case | Component allocation | Why |
|---|---|---|
| Create, MD / AS / STP | yes (one alt BOM or each alt BOM) | new routing uses the material's existing BOM |
| Create, **PLT** | **no** | plating needs a **new BOM** for the new routing, so there is nothing to allocate from the existing BOM |
| Delete (inactivate in CA02) | no | routing is set inactive, components are left as they are |
| Change (capacity, work center, names) in CA02 | no | the operations stay, components are not touched |
| Create with `Assign Components = No` in the file | no | user opt-out |

**Future (not designed yet, logged 2026-11-17): new BOM for plating.** Creating a PLT routing
will need a `CreateBom` step (CS01) before components are allocated to the new routing.
`SAP_automation\change_bom\bom_create.py` / `bom_create_main.py` already create BOMs in CS01. Open
questions for then: which components / quantities the new BOM gets, which alt BOM number SAP
assigns (`get_created_alt_bom`), and whether allocation then runs on that new alt BOM.

Adding a future feature = write one step class + add one line to this table (the `RECIPES` dict,
section 6.5). Nothing else changes.

## 5. Folders and files

As built (2026-11-19). **new** = added for the SAP automation; *(planned)* = designed, not built.
Visual view of the same tree: [`structure.html`](structure.html).

```
src/routing/
  cli.py                        routing run | check | opc | pre-uipath | list
  core/                         existing: config, Snowflake / SQL Server, Excel helpers
  data/                         existing: SQL only (Snowflake); + material.py (MARC status)
  checks/                       existing: stand-alone checks (still usable on their own)
  opc/                          existing: TPM / workflow file generators

  model/            new         plain data, no SAP, no Snowflake (section 5.1)
    enums.py                    Action, Dept, OperationRole, Status, PHASES
    entities.py                 what exists in SAP: RoutingKey, Routing, Operation, ProductionVersion,
                                MaterialRoutings, MaterialVersions + the shared rules (section 5.5)
    requests.py                 what the user asks, one per Excel row: Request + CreateParams, AltBomChoice
    result.py                   StepResult
    row_state.py                RowState: request + plan + results

  sap/              new         SAP GUI scripting only, no business rules
    session.py                  connect, status bar, warnings, popups, reset without saving
    elements.py                 every SAP element id in one place
    table.py                    table cells, paging, find_row
    screens/
      ca01.py                   initial screen, copy-from popups, alt BOM, header data
      ca02.py                   open routing, group popup, header list (by group + counter), inactivate, save
      operations.py             operation overview + operation details, missing setup check
      components.py             component allocation, choose alternative BOM (by value)
      mm02.py                   production version list: add, delete

  layouts/          new         production workflow types as data (section 5.2)
    catalog.py                  LAYOUTS: AS, PLT, STP, MD, MD_SORTING
    select.py                   layout_for, description, operation_values, check_copy_source

  resolve/          new         Snowflake rows -> entities (uses data/)
    routings.py                 load / load_versions / load_alt_boms -> MaterialRoutings, MaterialVersions,
                                active alt BOM numbers (data/bom.alt_bom_numbers); copy source, routing
                                key and existing versions are entity methods (5.5)

  steps/            new         one class per SAP / file action: plan() + run()
    base.py                     Step interface, Context (Snowflake + SAP session, caches)
    routing.py                  CreateRouting, InactivateRouting
    components.py               AllocateComponents
    production_version.py       CreateProductionVersion, DeleteProductionVersion

  pipelines/                    existing folder, new files for the run
    run.py          new         plan rows, run phases, safe_run, RunSummary (planner + runner in one)
    recipes.py      new         RECIPES (Action -> steps); PHASES order is in model/enums.py
    workbook.py     new         read rows, RESULT_ columns, Plan + Run log sheets, save after each row
    pre_uipath.py               existing

  (planned) departments.py      DEPARTMENTS: per Dept its layouts + OpCenter rules (section 5.3)
  (planned) opc/rules.py        OpCenter rules per department (moved out of add_tpm.py)
  (planned) steps/opc.py        AddTpm, AddWorkflow, DeleteTpm, InactivateWorkflow (wrap opc/)
  (planned) steps/routing.py    + ChangeCapacity, ChangeWorkCenter
```

Import rule (as today, downward only):
`cli -> pipelines -> steps -> (sap, layouts, resolve, opc) -> (data, model) -> core`.
`sap/` never imports Snowflake code and `resolve/` never touches SAP, so each can be tested alone.

`SAP_automation\change_bom` already has working code for CA02, component allocation and MM02. It
is **copied** into `sap/` (section 5.4), not moved and not imported.

### 5.1 Modelling: three kinds of objects, kept apart

| Kind | Answers | Examples | Changes during a run? |
|---|---|---|---|
| **Request** | what does the user want? (one per Excel row) | `Request(action=Create, spec=CreateParams(...))` | no (frozen) |
| **Entity** | what exists in SAP? | `Routing`, `Operation`, `ProductionVersion`, `RoutingKey` | no; read from Snowflake or the SAP screen |
| **Result** | what happened? | `StepResult(Done, "0006 (B2)")` | one per step |

`RowState` ties them together for one row and is what flows through the phases.

Steps (`CreateRouting`, `CreateProductionVersion`, ...) are **actions, not data**: there is no
data class per step. A step reads the request + entities and returns a result.

Compared with `SAP_automation\change_bom\models.py`: its `Routing` and `ProductionVersion` mix
the three kinds in one class (SAP data + work item + `status` / `message`). Here the SAP part
becomes the entity (same fields: material, group, counter, description, alt BOM, deleted ...),
`status` / `message` move to `StepResult`, and counts like `unassigned` move to the plan of the
step that needs them. That keeps entities reusable by checks, steps and the OpCenter side.

Per action, only what differs is a separate class (a **spec**): `CreateParams` (capacity, cavity,
eff, util, sorting, alt BOM), `DeleteParams`, later `ChangeCapacityParams` (capacity after),
`ChangeWorkCenterParams` (resource before / after), `RenameParams`. The common part (row, action,
material, dept, resource, tool) is in `Request`. A new action = one new spec + its steps.

### 5.2 Production workflow types (layouts): a mapping, yes

The operation overview differs per department because the production workflow differs, and one
department can have more than one (MD without / with sorting today; more may exist). So the key
of the mapping is the **workflow type**, not the department:

| Layout id | Used when | Operations (role per overview row, from `uipath_flows.md` 4.2, to be confirmed) |
|---|---|---|
| `AS` | Dept AS | production |
| `PLT` | Dept PLT | production (no component allocation) |
| `STP` | Dept STP | production, tool, final |
| `MD` | Dept MD, no sorting | production, tool, final |
| `MD_SORTING` | Dept MD + sorting given | production, tool, sorting, final |

Each layout lists its operations by **role** (`PRODUCTION`, `TOOL`, `SORTING`, `FINAL` - the
same roles `checks/operation_values.py` uses) and, per role, the overview row, what goes into the
work center, base quantity formula and detail fields. Steps never use row numbers directly; they
ask the layout: `layout.row(OperationRole.PRODUCTION)`. Then:
- create fills every role of the layout,
- change capacity sets the base quantity of the roles that carry capacity,
- change work center sets the work center of `PRODUCTION`,
with **one** table to fix when a screen differs.

`layout_for(request, copy_source)` picks the layout: the department + request features
(sorting given). Because CA01 copies an existing routing, the planner also checks that the copy
source has the operations the layout expects (from Snowflake `PLPO`) and writes a warning to the
Plan sheet if not, before SAP is touched. A new workflow type = one new entry in `LAYOUTS`
(+ one line in `layout_for` if it needs a new condition).

The copy-source check is **agreed** (2026-11-17).

### 5.3 Department rules on the OpCenter side: registered together, stored apart

Departments also differ in OpCenter (`docs/opc.md`, `add_tpm.py`): ideal cycle time is
MD = capacity x efficiency, AS = capacity x utilization, STP / PLT = capacity x efficiency x
utilization (tool given -> lookup file, tool blank -> Excel); sorting / lubricant rows have their
own cycle time and Spec rule.

SAP screen layout and OpCenter rules change for different reasons, so they live in different
modules, but one registry shows everything about a department:

```python
# departments.py - the only place that says what a department is
@dataclass(frozen=True)
class DeptProfile:
    layouts: tuple[str, ...]      # ids in layouts/catalog.py, picked by layouts/select.py
    opc: "OpcRules"               # from opc/rules.py


DEPARTMENTS = {
    Dept.MD:  DeptProfile(layouts=("MD", "MD_SORTING"), opc=OPC_RULES["MD"]),
    Dept.AS:  DeptProfile(layouts=("AS",),              opc=OPC_RULES["AS"]),
    Dept.STP: DeptProfile(layouts=("STP",),             opc=OPC_RULES["STP_PLT"]),
    Dept.PLT: DeptProfile(layouts=("PLT",),             opc=OPC_RULES["STP_PLT"]),
}
```

| What | Where | Used by |
|---|---|---|
| SAP operation screen per workflow type | `layouts/catalog.py` | SAP steps |
| OpCenter rules per department (cycle time formula, eff / util source, Spec rule) | `opc/rules.py` | `add_tpm`, later `UpdateTpmCycleTime` |
| shared values (capacity, capacity x cavity, eff, util) | one helper on the request spec | both, so SAP base quantity and TPM cycle time cannot drift apart |

`opc/add_tpm.py` keeps its output; its inline department branches move to `opc/rules.py`
(refactor, testable against today's output). A new department = one `DEPARTMENTS` entry + a layout
and / or OpCenter rule only where it differs.

### 5.4 Reusing `SAP_automation\change_bom`: copy, not move or import

| Option | How | For | Against |
|---|---|---|---|
| Move | cut the code out of `SAP_automation`, `SAP_automation` imports it back from `routing.sap` | one copy of the code | changes `SAP_automation`, which must stay as it is (`README.md` Background); its BOM scripts (`bom*.py`) break if the move goes wrong |
| Import | `routing.sap` calls `change_bom` modules directly (`sys.path` or a path dependency) | no duplicated code, fixes in one place | `change_bom` is flat scripts, not a package (no `pyproject.toml`); its names `config`, `workbook`, `utils`, `models` clash with ours; screen code is mixed with Excel / Snowflake / status handling (`models.py`), which breaks the rule "`sap/` has no business rules"; a change there can silently break a routing run |
| **Copy** (chosen) | copy only the screen code into `sap/`, adapt it to `session.py` / `elements.py` / `model/` | `SAP_automation` untouched and keeps running; `sap/` stays clean and testable; no hidden dependency | two copies; a fix in one must be copied to the other by hand |

What is copied (source -> target):

| From `change_bom` | To | Only the SAP part |
|---|---|---|
| `connect.py` (`get_session`) | `sap/session.py` | connect, wait, status bar, popups |
| `routing.py` (`open_routing`, `select_group`, `open_header_row`, `find_row`, `get_cell_text`) | `sap/screens/ca02.py` | open by group + counter, page through tables |
| `routing.py` (component allocation, choose alt BOM by value) | `sap/screens/components.py` | find alt BOM row by value (col 19), assign components |
| `production_version.py` (open material, read versions, next number, enter, save, popups) | `sap/screens/mm02.py` | without the Excel / skip-previous logic, which goes to `steps/` and `pipelines/` |
| element ids used in the files above | `sap/elements.py` | one place |

Not copied: `models.py`, `workbook.py`, `reader.py`, `config.py`, `routing_main.py`, `routing_sf.py`,
`bom*.py`, `update_*.py` (Excel, Snowflake and BOM work have their own place here or are out of scope).

Rules for the copy:
- each copied function gets a one-line comment `# from SAP_automation/change_bom/<file>.py:<function>`,
  so the twin can be found when a fix is needed;
- known problems in `change_bom/docs/TODO_bug.md` are checked before copying, not copied blindly;
- `SAP_automation` stays as it is; once the routing run replaces it for CA02 / MM02 work, its copies
  can be retired (open point, section 9).

### 5.5 Entities with behaviour + one shared matcher (first part built, see 0.2)

Today `Routing` / `ProductionVersion` are plain data and the rules about them are free functions
spread over `resolve/`, `layouts/select.py` and five checks (section 0.2). Proposal: put each rule
on the class it is about, once, and let checks, planner and steps call the same method.

```python
# model/entities.py
@dataclass(frozen=True)
class Routing:
    key: RoutingKey
    description: str = ""
    status: str = ""
    deleted: bool = False
    operations: tuple[Operation, ...] = ()

    @property
    def is_trial(self) -> bool: ...            # "TRIAL" in description (covers MDTRIAL)
    @property
    def is_production(self) -> bool: ...       # status 4, not deleted, not trial -> may be copied

    def matches(self, resource, tool="", sorting="") -> bool:
        """THE rule (from checks/routing_condition): resource = work center of an operation,
        tool / sorting / extra work center text in the description."""

    def operation(self, role: OperationRole) -> Operation | None:
        """THE role rule (from checks/operation_values): production 0020, sorting YMHI after it,
        final PP94 = last operation (ZP04 = trial routing, never final)."""

    def fits(self, layout) -> list[str]:        # today: layouts.select.check_copy_source
        ...


@dataclass(frozen=True)
class MaterialRoutings:                         # all routings of one material (from Snowflake)
    material: str
    routings: tuple[Routing, ...]

    def matching(self, resource, tool="", sorting="") -> list[Routing]: ...   # active first, newest first
    def group_size(self, group) -> int: ...
    def copy_source(self, request, layout) -> Routing | None: ...


@dataclass(frozen=True)
class ProductionVersion:
    material: str
    version: str
    routing: RoutingKey
    alt_bom: int
    text: str = ""
    locked: bool = False

    @staticmethod
    def text_for(routing: Routing, alt_bom: int) -> str: ...   # "<description> B<n>", 40-char check


@dataclass(frozen=True)
class MaterialVersions:                         # all production versions of one material
    material: str
    versions: tuple[ProductionVersion, ...]

    def on(self, key: RoutingKey) -> list[ProductionVersion]: ...
    def has(self, key, alt_bom) -> bool: ...                   # today: checks/pv_exist
    def missing(self, key, alt_boms) -> list[int]: ...         # ALL BOM concern (production_version.md)
    def next_number(self) -> str: ...                          # max below 5000 + 1, "0000" format
```

Who uses what afterwards:

| Rule | Method | Used by |
|---|---|---|
| which routing a row means | `MaterialRoutings.matching` / `Routing.matches` | routing_condition, operation_values, delete_status, planner (create / delete) |
| operation roles | `Routing.operation(role)` | operation_values, `Routing.fits`, later change capacity |
| copy source | `MaterialRoutings.copy_source` | CreateRouting |
| version exists / missing | `MaterialVersions.has` / `missing` | pv_exist, CreateProductionVersion |
| Alt Bom parsing | `AltBomChoice.parse` | requests, pv_exist |

Checks keep their pandas input / output (Excel columns stay the same); only the decision inside
moves to the entity. Each check is changed with a before / after run on the same file.
Decided: TRIAL is excluded as copy source only, not from matching (section 0).

Built differently from the sketch above: `Routing.fits(layout)` stays in
`layouts/select.check_copy_source` (model must not import layouts); `MaterialRoutings.copy_source`
takes a `fits` function instead of the layout. `OperationValue` (the to-type list) moved from
`model/entities.py` to `layouts/select.py`, because it is not something that exists in SAP.

## 6. Skeleton (as built)

Key signatures as they are in the code (2026-11-19); bodies: see the files. Updated from the
original design skeleton - differences are noted under each part.

### 6.1 `model/` - enums, entities, requests

```python
# model/enums.py
class Action(str, Enum):
    CREATE = "Add"                  # file wording; "Create" accepted as an alias
    DELETE = "Delete"
    ASSIGN = "Assign Components"    # existing routing (UiPath main_bom_assignment)
    # later: CHANGE_CAPACITY, CHANGE_WORK_CENTER, RENAME

class Dept(str, Enum):        MD, AS, PLT, STP
class OperationRole(str, Enum): PRODUCTION, TOOL, SORTING, FINAL   # same vocabulary as checks/operation_values
class Status(str, Enum):      DONE, SKIPPED, FAILED
PHASES = ("routing", "components", "pv", "opc")

# model/entities.py - what exists in SAP (Snowflake or the SAP screen) + the shared rules (5.5)
RoutingKey(material, group, counter)
Operation(number, control_key, work_center, base_quantity)
Routing(key, description, status, deleted, operations)
    .matches(resource, *texts)    .operation(role)    .has_sorting    .is_trial    .can_be_copied_for(resource)
MaterialRoutings(material, routings)
    .get(key)    .matching(resource, *texts)    .copy_source(fits, resource, needs_sorting, sorting)    .group_size(group)
ProductionVersion(material, version, routing, alt_bom, text, locked)    .text_for(routing, alt_bom)
MaterialVersions(material, versions)    .on(key)    .has(key, alt_bom)    .missing(key, alt_boms)    .next_number()

# model/requests.py - one Request per Excel row; one params class per action
AltBomChoice(all, number)                              .parse("ALL BOM" | "2" | "B2" | blank -> 1)
CreateParams(capacity, tool_cavity, efficiency, utilization, sorting, sorting_capacity, alt_bom, assign_components)
DeleteParams()
AssignParams(sorting, alt_bom, assign_components)
Request(excel_row, action, dept, material, resource, tool, key, copy_from, params)
request_from_row(excel_row, values) -> Request          # InputError -> RESULT_INPUT
```

Differences from the design: `Action.ASSIGN` + `AssignParams` added (2026-11-18); `Request.copy_from`
(the `COPY_FROM_GROUP` / `_GC` override); the matching / copy-source rules are entity methods instead
of separate `resolve/` modules.

### 6.2 `model/row_state.py` - what flows through the phases

```python
@dataclass
class Plan:                                  # decided before SAP is touched (Snowflake only)
    steps: list[str]
    layout: str                              # e.g. "MD_SORTING"
    copy_from: Routing | None                # create: routing of the same material to copy
    target: Routing | None                   # the routing the row works on (existing or just created)
    alt_boms: list[int]                      # pv: alt BOMs that still need a version
    component_alt_boms: list[int]            # components: alt BOMs to allocate
    existing_versions: list[ProductionVersion]
    warnings: list[str]
    skip: dict[str, str]                     # step name -> reason: written as Skipped, not run
    errors: dict[str, str]                   # step name -> planning error: Failed, retried next run

@dataclass
class RowState:
    request: Request
    plan: Plan
    key: RoutingKey | None                   # target routing: file, Snowflake or SAP screen
    results: dict[str, StepResult]           # step name -> result
    def done(step_name) -> bool              # Done or Skipped
    def has_failed() -> bool
```

### 6.3 `steps/base.py` - the one interface every step follows

```python
class Step:
    name: str          # result column via pipelines/workbook.RESULT_COLUMNS, e.g. CreateRouting -> RESULT_ROUTING
    phase: str         # "routing" | "components" | "pv" | "opc"
    def applies(self, row) -> bool            # does the step belong to the row (e.g. no components for PLT)
    def plan(self, row, ctx) -> None          # Snowflake only; reason in row.plan.skip[self.name] to skip
    def run(self, row, ctx) -> StepResult     # SAP / files; Save only as the last action

class Context:     # shared resources of one run; Snowflake and SAP opened only when first used
    sf, sap                                   # sap raises in --dry-run
    routings(material), versions(material), alt_boms(material), material_status(material)   # cached
```

### 6.4 A step, e.g. `steps/production_version.py`

```python
class CreateProductionVersion(Step):
    name, phase = "CreateProductionVersion", "pv"
    def applies(self, row):  return row.request.action is Action.CREATE
    def plan(self, row, ctx):
        wanted = ctx.alt_boms(material) if ALL BOM else [number]
        plan.existing_versions = ctx.versions(material).on(routing.key)
        plan.alt_boms = ctx.versions(material).missing(routing.key, wanted)   # never a duplicate
    def run(self, row, ctx):
        mm02.open_versions -> read_versions -> add_version per alt BOM (next number) -> close_and_save

class DeleteProductionVersion(Step):          # versions of the routing (group + counter) from Snowflake
    def run(self, row, ctx):
        mm02.delete_version(sap, version, expected_text)   # by number, text checked, cursor on the row,
                                                            # only that version may disappear
```

### 6.5 `pipelines/recipes.py` - the only place that decides "which steps"

```python
RECIPES = {
    Action.CREATE: [CreateRouting(), AllocateComponents(), CreateProductionVersion()],
    Action.DELETE: [InactivateRouting(), DeleteProductionVersion()],
    Action.ASSIGN: [AllocateComponents()],
}   # opc steps (AddTpm, AddWorkflow, DeleteTpm, InactivateWorkflow): not built

def steps_for(row, phases=PHASES, recipes=RECIPES) -> list[Step]   # phase order, --phase, Step.applies()
def earlier_failed(row, step, recipes) -> bool                     # later phases of a failed row wait
```

Difference from the design: Delete runs `InactivateRouting` before `DeleteProductionVersion` (phase order).

### 6.6 `layouts/` - production workflow types as data

```python
# layouts/catalog.py
OperationSlot(role, row, work_center="keep", base_qty=None, details=())
    # work_center: "resource" | "tool" | "sorting" | "keep"; base_qty: "capacity" | "capacity_x_cavity" |
    # "sorting_capacity" | None; details: ((field, formula), ...), fields: op_text, base_qty, cavity,
    # efficiency, utilization, setup
OperationLayout(id, description, slots, allocate_components=True, verified=False)
    .slot(role)    .roles()    .slots_with_capacity()          # the last one for a future ChangeCapacity
LAYOUTS = {"AS", "PLT" (no components), "STP", "MD", "MD_SORTING"}   # rows: verification.md I.2

# layouts/select.py
layout_for(request) -> OperationLayout                        # MD + sorting -> MD_SORTING
description(layout, request) -> str                            # blank parts left out, max 40 characters
operation_values(layout, request) -> list[OperationValue]      # what CreateRouting types, row by row
missing_inputs(layout, request) -> list[str]
check_copy_source(layout, routing) -> list[str]                # warnings: sorting / final step not where expected
```

Difference from the design: `description` is a tuple of parts, not a format string; detail
fields carry their formula.

### 6.7 `pipelines/run.py` - the backbone

```python
def run(path, phases=PHASES, only=None, rows=None, dry_run=False, slow=False, sheet=None) -> RunSummary:
    book = RequestWorkbook(path, sheet)              # input rows + previous RESULT_ columns
    states, invalid = parse_rows(book.rows(), only, rows)   # deletes first
    plan_rows(states, ctx, phases)                   # Snowflake only; E3 material -> every step skipped
    book.write_plan(states, invalid)                 # Plan sheet
    if not dry_run:
        execute(states, book, ctx, summary, phases)  # phase by phase, all rows; save after every row

def safe_run(step, row, ctx) -> StepResult
    # error -> SAP screen + status bar into the message -> reset (popups closed, /n, leave WITHOUT
    # saving; a save question is answered No) -> Failed; only a failed reset stops the run (RunAborted)
```

Difference from the design: planner and runner are one module (`pipelines/run.py`), not
`pipeline/planner.py` + `runner.py`.

Why phase by phase and not row by row: SAP stays in one transaction per phase (CA01 for all
creates, then MM02 for all versions), which is faster and mirrors how UiPath is run today.

### 6.8 `cli.py` - `routing run`

```python
run.add_argument("file", nargs="?")
run.add_argument("--phase", action="append", choices=PHASES)
run.add_argument("--only", choices=[a.value.lower() for a in Action])    # add | delete | "assign components"
run.add_argument("--rows")                                               # 5-12 or 5,7,9
run.add_argument("--dry-run", action="store_true")
run.add_argument("--slow", action="store_true")
run.add_argument("--sheet")
```

## 7. Excel input / output (as built)

Input columns (one sheet, one row per request): `Action`, `Dept`, `Material`, `Resource`, `Tool`,
`Capacity`, `Tool Cavity`, `Efficiency`, `Utilization`, `Sorting/ Lubricant`,
`Sorting/ Lubricant Capacity`, `Alt Bom`, optional `Assign Components` (blank = yes), optional
`group` / `group counter` (override or for later phases).

Written back:

| Columns | Written by |
|---|---|
| `group`, `group counter` | routing phase (from the SAP screen) or the planner (Snowflake) |
| `COPY_FROM_PLANNED` (information only) | planner; the user may fill `COPY_FROM_GROUP` / `COPY_FROM_GC` as an override (never written by the tool) |
| `RESULT_ROUTING`, `RESULT_COMPALLOC`, `RESULT_MM02` (`Done` / `Skipped: ...` / `Failed: ...`), `RESULT_INPUT` | each step, see 7.1 |
| sheet **Plan** | planner, one row per request + its planned steps |
| sheet **Run log** | runner, one row per step run: time, row, step, status, message |

### 7.1 Progress and resume (replaces UiPath's `progress` column)

UiPath writes one progress text per row (`done ca01`, `done mm02`, ...) and skips the row on the
next run. Python keeps the idea but with **one result column per kind of work**, the same statuses
everywhere, and does **not read the old `progress` column** (decided 2026-11-18):

| Column | Step(s) | Filled for Action |
|---|---|---|
| `RESULT_ROUTING` | CA01 create routing (`CreateRouting`) / CA02 deletion flag + status 1 (`InactivateRouting`) | Add / Delete |
| `RESULT_COMPALLOC` | CA02 component allocation (`AllocateComponents`) | Add (not PLT), Assign Components |
| `RESULT_MM02` | MM02 production versions created (`CreateProductionVersion`) / deleted (`DeleteProductionVersion`) | Add / Delete |
| `RESULT_INPUT` | row could not be read (unknown Action, Capacity missing, ...) - nothing runs for it | any |
| (later) `RESULT_OPC` | OpCenter TPM / workflow files | Add / Delete |

A row has one Action, so Add and Delete share `RESULT_ROUTING` and `RESULT_MM02`. Mapping in
code: `pipelines/workbook.RESULT_COLUMNS`. Example after an Add row:

| RESULT_ROUTING | RESULT_COMPALLOC | RESULT_MM02 |
|---|---|---|
| `Done: M0629201/11 copied from M0629201/10` | `Done: B1 0030: 2, 0020: 5` | `Done: 0004 (B1)` |

| Status in a result column | Meaning | On a rerun |
|---|---|---|
| `Done` (+ detail, e.g. `Done: 0006 (B2)`) | step finished in SAP / file | skipped |
| `Skipped: <reason>` (e.g. `Skipped: routing not found`, `Skipped: material status E3`) | nothing to do, final | skipped |
| `Failed: <message>` | error, SAP status bar text included | **run again** |
| blank | not run yet | run |

A row whose step failed does not continue to the later phases (no production version for a
routing that was not created). To force a step again, clear its result cell.

Differences from UiPath, on purpose:
- one column per kind of work instead of one shared `progress` text that the next step overwrites;
- the file is saved **after every row** (UiPath: `SaveAfterEachRow = False`, progress lost on a crash);
- a `Failed` step is retried, an unknown error never writes `done` (UiPath writes `done mm02` even
  for an unknown Action);
- the UiPath `progress` column is left as it is and ignored; rows already done by UiPath are
  recognised by the planner instead ("routing already exists", "versions exist").

## 8. Build order (status 2026-11-19)

| # | Step | State |
|---|---|---|
| 1 | `model/`, `pipelines/` (run, recipes, workbook) with fake steps; `--dry-run` end to end | done |
| 2 | `sap/session.py` + `screens/mm02.py` + production version steps | done; create run live, delete fix (row by cursor) not run live yet |
| 3 | `screens/ca02.py` + `components.py` + `AllocateComponents`, `InactivateRouting` | done, run live |
| 4 | `layouts/` + `screens/ca01.py` + `operations.py` + `CreateRouting` | done; AS, PLT, STP, MD run live, layouts not marked verified; C_AUTO assembly layout open |
| 5 | `opc` steps wrapping the existing generators | not built (run `routing opc ...` separately) |
| 6 | Later: change capacity / work center, rename, new BOM for plating (`CreateBom`, CS01, 4.1) | backlog |

Open items per step: `docs/verification.md` (the only checklist).

## 9. Open points

### Copy from another material (user idea, logged 2026-11-17, not built)

The copy-source override (section 0) gives flexibility, and should later also cover a routing of
**another material**, e.g. when the material has **no task list yet** (no routing to copy from
its own group). That is a branch of Create:

| Case | Today | Later |
|---|---|---|
| material has routings | copy from the same material (planner pick or `COPY_FROM_GROUP` / `_GC`) | same |
| material has **no** routing | Create is skipped: "no routing of this material to copy from" | copy from the routing given in a new column **`COPY_FROM_MATERIAL`** + `COPY_FROM_GROUP` / `_GC` |
| user wants another material's routing on purpose | not possible | same new columns |

What already supports it:
- CA01 copy dialog types the source material (`sap/screens/ca01.choose_copy_source` uses
  `source.material`), so the SAP side needs no new screen;
- `RoutingKey` carries the material; the planner can load the other material's routings
  (`Context.load_routings`) and check them with the same rules (`can_be_copied`, `check_copy_source`).

What is new / to decide then:
- `Request.copy_from` with a material different from the row (read `COPY_FROM_MATERIAL`);
- **no task list = no "Entry Option: Group" popup**: SAP needs a new group. UiPath had this
  commented out: type `"M" + first 7 characters of the material` in `wnd[0]/usr/ctxt[5]`
  ("FOR NO TASK LIST ONLY", `docs/uipath/ui_elements.md` 3.1) - confirm the group naming rule;
- whether the planner may suggest a source from another material automatically (e.g. same
  resource / tool family) or only use what the user types;
- the copied routing's description / operations belong to the other material: check the layout
  fit and that work centers / tools make sense for the new material.

### Backlog: side requests on top of the backbone (decided 2026-11-18)

Not frequent; developed later, only if needed, on top of the backbone (Create / Delete / Assign
Components + pv + opc). Nothing in the backbone has to change for them.

#### Create routing "same info" (UiPath `add_routing/create_routing_sameinfo`)

Status: **backlog, not in the code** (a first draft was removed again on 2026-11-18 to keep the
backbone clean).

What UiPath does: another routing like the one the resource already has, **keeping its tool**.
Excel: Material, Resource, Capacity (no Tool). CA01 copy (same helpers as Create), alt BOM row 0,
header: read group / counter, status 4; operation overview: work center row 2 = Resource, **read the
tool from row 3**, Header (F5) -> description `Resource - Material - <tool>`, Operations; base quantity
= Capacity on rows 1 and 2; CompAlloc: first component -> 0020; save.

Design when it is picked up (reuses the backbone, no new SAP screens):

| Part | How |
|---|---|
| Input | Create row + opt-in column `Same Info` = Yes (not automatic on a blank Tool: a forgotten Tool would silently copy another routing's tool) |
| Layout | new `LAYOUTS["SAMEINFO"]`: production row 2 = Resource + Capacity, tool row 3 kept, row 1 Capacity; flag "tool from copy" |
| Plan | skip the "routing already exists" check (a routing with the resource always exists); copy source = newest status-4 routing with the Resource as work center, or COPY_FROM_GROUP / _GC; warn when several qualify; skip when none |
| Run | `fill_header` without description -> set work centers -> read tool at row 3 -> Header (F5), type description, Operations -> base quantities -> save |
| Components / pv / opc | normal `AllocateComponents` rule (not UiPath's "first component to 0020"), versions from the new description |
| Verify | layout rows (rows 1 / 2 come from the XAML only), description length (only known after the tool is read), pv rerun within the ~15 min Snowflake lag cannot rebuild the description |

#### Change resource (UiPath `production_version/change_resource`)

A resource change is not one edit. It touches four places:

| Where | What changes | Today in UiPath |
|---|---|---|
| CA02 operation overview | work center of the production operation (old resource -> new) | not done (`change_wc_sap` is separate, not run) |
| CA02 header | routing description `<old resource> - ...` -> `<new resource> - ...` | not done |
| MM02 production versions | version text `<old resource> - <tool> B<n>` -> new resource | `change_resource`: overwrites the text, drops ` B<n>`, no not-found check |
| OpCenter | TPM / workflow names with the old resource: delete old, add new | not done |

Editing all four in place means a new CA02 change flow, a MM02 text edit, and keeping routing,
versions and OpCenter names in step - complex, with many half-done states to resume from.

**Preferred approach: delete old + create new** with the steps that already exist:

| Excel row | Action | Steps it runs |
|---|---|---|
| 1 | `Delete`, old Resource (+ Tool, or group / group counter) | `InactivateRouting` (deletion flag + status 1), `DeleteProductionVersion`, opc: delete old TPM / workflow |
| 2 | `Create`, new Resource, same Tool, capacity etc. | `CreateRouting` (copy, status 4), `AllocateComponents`, `CreateProductionVersion`, opc: add new TPM / workflow |

Why: no new SAP screens or edit logic; names in routing, versions and OpCenter are consistent by
construction (all built from the new resource); resume / logging work as for any Create and Delete;
the old routing stays in SAP as inactive (deletion flag, reactivatable) for history.

To decide when it is picked up:
- a convenience action `Change Resource` (columns `Resource before` / `Resource after`) that the
  planner expands into the Delete + Create pair, or just two rows written by the user;
- order: deletes run first today (`parse_rows`), so the old routing is inactive before the new one
  is copied - the copy source must then be another active routing (planner picks it, or
  `COPY_FROM_GROUP` / `_GC`), or the order must be Create first, Delete second for this pair;
- the new production version numbers differ from the old ones (new versions, not renamed) -
  check that nothing downstream depends on the old version numbers.

### Other open points

- `SAP_automation\change_bom`: after the copy (section 5.4), does it keep its CA02 / MM02 scripts,
  or are they retired once `routing run` covers that work? Until then, fixes must be copied both ways.
- OpCenter files at the end of a run, only for successful rows: proposed, to be confirmed.
- Checks still open on SAP (delete order, layout rows, element ids, workflow types, ...):
  `docs/verification.md` checklist.
