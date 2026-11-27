# ROUTING

SAP routing checks (Snowflake) that run before the UiPath routing automation, and
OpCenter upload-file generators (Tool Plan Matrix, workflows).

In progress: the SAP data entry moves from UiPath to Python (`routing run`, below). Background,
decisions and SAP facts: [Background: replacing UiPath](#background-replacing-uipath).

## Routing requests in SAP (in progress)

Built: routing (create in CA01, inactivate in CA02), components (CA02) and production versions
(MM02). OpCenter phase not built yet.

### Before every run

1. Setup done once (section [Setup](#setup-once)), plus `pip install -e ".[sap]"` (pywin32 for SAP GUI scripting).
2. In a new terminal: `cd C:\Users\nguyeb3\Downloads\ROUTING` and `C:\Users\nguyeb3\venvs\routing\Scripts\Activate.ps1` (venv location: see Setup).
3. SAP GUI open and logged in (not needed for `--dry-run`).
4. The request Excel file is **closed** - results are saved into it after every row; if it is open
   the run stops with "close it in Excel".

### Run all phases or one phase

`routing run` has three SAP phases. Without `--phase` all three run, in this order, each one for
all rows before the next starts:

| Phase | `--phase` | Add rows | Delete rows | Assign components rows |
|---|---|---|---|---|
| 1. Routing | `routing` | create routing in CA01 (copy from source) | inactivate routing in CA02 | - |
| 2. Components (BOM assignment) | `components` | assign components in CA02 | - | assign components in CA02 |
| 3. Production version | `pv` | create production version in MM02 | delete production version in MM02 | - |

```powershell
# all phases (routing -> components -> production version)
routing run "C:\path\requests.xlsx"

# one phase
routing run "C:\path\requests.xlsx" --phase routing       # 1. create / inactivate routing only
routing run "C:\path\requests.xlsx" --phase components    # 2. BOM component assignment only
routing run "C:\path\requests.xlsx" --phase pv            # 3. production version only

# several phases
routing run "C:\path\requests.xlsx" --phase components --phase pv

# combine with Action / rows
routing run "C:\path\requests.xlsx" --only add --phase pv     # production versions of Add rows only
routing run "C:\path\requests.xlsx" --rows 5-12 --phase routing
```

A later phase needs the earlier one done: components and pv use the group / group counter that
the routing phase writes into the row. Running `--phase pv` alone works for rows whose routing is
already `Done` (or whose `group` / `group counter` is filled). If an earlier phase `Failed` for a
row, its later phases are not run for that row. Rows already `Done` / `Skipped` in
a phase are skipped on rerun, `Failed` rows are retried. OpCenter is not a phase: run
`routing opc ...` afterwards (see [All commands](#all-commands)).

### First test run, step by step

```powershell
routing run "C:\path\requests.xlsx" --dry-run          # 1. plan only, SAP untouched -> check the Plan sheet
routing run "C:\path\requests.xlsx" --rows 2 --slow    # 2. one row, slow, while watching SAP
routing run "C:\path\requests.xlsx"                    # 3. all rows
```

| Option | Meaning |
|---|---|
| `--dry-run` | plan only: writes the **Plan** sheet (steps, layout, copy source, target routing, alt BOMs, skip reasons, warnings, errors); SAP is not touched |
| `--rows 5-12` / `--rows 5,7,9` | only these **Excel row numbers** (row 2 = first data row) |
| `--only add` / `delete` / `"assign components"` | only rows with this `Action` |
| `--phase routing` / `components` / `pv` | only this phase (repeat for several); default all, in that order |
| `--slow` | wait after every SAP action, to watch / debug |
| `--sheet NAME` | request sheet (default: first sheet) |

If FILE is left out you are asked for it (drag & drop works).

### Input

One sheet, one row per request: `Action` (Add / Delete / Assign Components; `Create` is also
accepted), `Dept`, `Material`, `Resource`, `Tool`, `Capacity`, `Tool Cavity`, `Efficiency`,
`Utilization`, `Sorting/ Lubricant`, ..., `Alt Bom` (number, `B2`, `ALL BOM`; blank = 1).
`Same Info` and Change Resource are backlog (docs/architecture.md section 9).

### Output (written into the same file)

| Where | What |
|---|---|
| `RESULT_ROUTING` | CA01 create (Add) / CA02 deletion flag + status 1 (Delete) |
| `RESULT_COMPALLOC` | component allocation (CA02), e.g. `Done: B1 0030: 2, 0020: 1` |
| `RESULT_MM02` | MM02 production versions created (Add) / deleted (Delete) |
| `RESULT_INPUT` | row not valid (reason) |
| `group`, `group counter` | routing key, filled when known |
| sheet **Plan** | the plan of the last run (replaced each run) |
| sheet **Run log** | one line per step: time, row, material, step, status, message |

Each result cell is `Done: ...`, `Skipped: ...` or `Failed: ...`. **Re-running is safe**: Done and
Skipped steps are not run again, Failed ones are retried - fix the cause and run the same command.
The old UiPath `progress` column is not read.

**Re-using an Add row for Delete:** Add and Delete share `RESULT_ROUTING` / `RESULT_MM02`, so a
`Done` from the create would make the delete look finished. Clear those two cells on the row
first (keep `group` / `group counter`, they pin the exact routing).
Design and status: [`docs/architecture.md`](docs/architecture.md); what is checked / still open:
[`docs/verification.md`](docs/verification.md).

## Setup (once)

```powershell
py -m venv C:\Users\nguyeb3\venvs\routing
C:\Users\nguyeb3\venvs\routing\Scripts\Activate.ps1
pip install -e "C:\Users\nguyeb3\Downloads\ROUTING[sap,dev]"
copy .env.example .env      # fill in the OpCenter SQL Server values
```

**Venv location:** `C:\Users\nguyeb3\venvs\routing` (created 2026-11-25, Python 3.14).
Not `ROUTING\.venv`: inside `Downloads`, `python.exe` and `Activate.ps1` were removed from
`.venv\Scripts` (likely security software), which broke every command. The old `.venv` is unused.
In every new terminal: `C:\Users\nguyeb3\venvs\routing\Scripts\Activate.ps1`, then `routing ...`.

`pip install -e .` makes `routing` importable from any folder and adds the `routing` command.
Snowflake uses the `default` connection from your Snowflake `connections.toml`.


## All commands

```powershell
routing list
routing check routing-condition FILE [-o OUT]
routing check alt-bom FILE
routing check delete-status FILE
routing check operation-values FILE [--sheet Sheet1]
routing check routings-by-tool FILE
routing check tpm-exist FILE
routing check pv-count | pv-by-group | pv-by-attributes | pv-fallback FILE [--sheet Sheet1]
routing check pv-exist FILE [-o OUT] [--sheet Sheet1]
routing opc add-tpm | add-workflow | compare-workflow | delete-tpm |
            update-tpm-priority  [-i INPUT] [-o OUTPUT]
```

If FILE is left out you are asked for it (drag & drop works).

`pv-exist` checks whether the production version for each row's routing (`group` + `group counter`,
filled by `routing-condition`) and `Alt Bom` already exists. It adds `PV_FOUND` and
`PV_CHECK` (`Exists` / `Missing`; `ALL BOM` rows are not checked yet, only listed) and writes back
into FILE unless `-o` is given. Production version commands, rules and the open ALL BOM concern:
[`docs/production_version.md`](docs/production_version.md).

`operation-values` checks the routing operations in one pass: base quantity at production /
sorting / final step, the standard values (setup, machine, labor must be `1.000 H` at 0020) and
efficiency / utilization. Rules, documented exceptions and known gaps:
[`docs/operation_values.md`](docs/operation_values.md). It replaces the former
`operation-capacity` and `util-eff` commands, which still work as aliases.

## Layout

| Folder | Contains |
|---|---|
| `src/routing/core/` | config (plant, connection name, paths), DB connections, cleaning, Excel I/O |
| `src/routing/data/` | SQL queries only, one file per topic, return DataFrames |
| `src/routing/checks/` | stand-alone checks (business logic) |
| `src/routing/opc/` | OpCenter upload-file generators, see `docs/opc.md` |
| `src/routing/pipelines/` | `routing run`: plan, phases, recipes, Excel results |
| `src/routing/cli.py` | the `routing` command |
| `sql/`, `notebooks/`, `docs/` | ad-hoc SQL, notebook, notes |
| `archive/` | retired code kept for reference (`pre_uipath`), not importable |
| `tests/` | `pytest` (no Snowflake needed) |
| `output/` | generated Excel files (git-ignored) |

Rules: imports only go downward (cli -> checks/opc -> data -> core); queries use bound
parameters, never values pasted into SQL; plant / connection / paths come from `core/config.py`
or `.env` (`ROUTING_PLANT`, `SNOWFLAKE_CONNECTION`, `ROUTING_OUTPUT_DIR`).

## Tests

```powershell
pytest
```

## Background: replacing UiPath

**Goal**: one Python tool runs the whole routing lifecycle (SAP + OpCenter files), so UiPath is no
longer needed. UiPath keeps running until each Python branch is proven on SAP.

| Lifecycle | Steps (phases of `routing run`) |
|---|---|
| Create | CA01 copy a routing of the same material -> component allocation (CA02, all or one alt BOM) -> production versions (MM02) -> OpCenter TPM + workflow files |
| Delete | CA02 deletion flag + status 1 -> delete the production versions (MM02) -> OpCenter delete TPM / workflow |
| Assign Components | component allocation (CA02) on an existing routing |
| Later | change capacity, change work center, rename routings / versions (design in `docs/architecture.md`) |

**Docs**

| File | What |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | design, status, scope, backlog |
| [`docs/verification.md`](docs/verification.md) | what is checked / still open (the only checklist) |
| [`docs/uipath_flows.md`](docs/uipath_flows.md) | how the UiPath project works (being replaced) |
| `docs/uipath/ui_elements.md`, `.csv` | SAP element ids taken from UiPath (regenerate: `tools/uipath_dump.py`, `tools/uipath_catalog.py`) |

**Decisions**

| Topic | Decision |
|---|---|
| SAP access | SAP GUI scripting from Python (as `SAP_automation`), not RFC / BAPI; SAP Logon connection `M04 [SSO]` |
| Input | one Excel file, one row per request, `Action` column; deletes run before creates |
| Copy source | a routing of the **same material**, chosen before the run from Snowflake (rules: `docs/verification.md` C), overridable per row |
| Routing status | create: **4** = production / released (UiPath's label "status 1" is outdated); delete: deletion flag + **1** = inactive |
| Snowflake lag (~15 min) | existing data comes from Snowflake; anything created in the same run (new group / counter) is read from the SAP screen |

**SAP facts** (plant 1901, Snowflake `MLX_DATALAKE.MLX_SAP_ECC`)
- Delete fields: `PLKO.DELKZ = 'X'` = deletion flag, still in SAP and reactivatable;
  `DW_SOFT_DELETE_FLAG = 1` = gone from SAP (history only); `MAPL.LOEKZ` / `PLKO.LOEKZ = 'X'` =
  deleted. Example: 522690630 GC 15 flagged, still in SAP; GC 16 permanently deleted.
- Operation roles: production = 0020 (`PP01`, a few at 0030); sorting / lubricant = work center
  `YMHI*` after 0020 (`PP96`); final step = `PP94` only (last, 0030-0060); `ZP04` = trial routing.
  YMHI at 0020 is production (hi-coat, regrinding). Details: `docs/operation_values.md`.
- Standard values (`PLPO`): setup / machine / labor = `VGW01-03`, units `VGE01-03`, activity types
  `LAR01-03`; unit conversion `UMREZ` / `UMREN`.
- Production versions (`MKAL`): `VERID`, routing `PLNNR` + `ALNAL`, alt BOM `STLAL`, lock `MKSP`,
  valid `ADATU`-`BDATU`, text like `MF50-09 - L501330A B1`.
- Active alt BOM = `MAST.STLAN = 1` + `STKO.STLST = 01`, not soft-deleted. A **count** is not the
  numbers: active alt BOMs 1 and 3 give count 2.
