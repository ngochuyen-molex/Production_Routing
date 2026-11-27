## Archived: pre-UiPath checks (2026-11-27)

UiPath is no longer used for routing (`routing run` replaces it), so the `pre-uipath` command was
removed. The code is kept, not importable, in `archive/`:

- `archive/pre_uipath.py` - was `src/routing/pipelines/pre_uipath.py` (routing condition, then alt
  BOM count, on one Snowflake connection; wrote `SKIP`, `SKIP_REASON`, `group`, `group counter`,
  `ALT_BOM_COUNT`).
- `archive/pre_uipath_launcher.py` - was the repo-root `pre_uipath.py` shim for UiPath / VBS.

The same results are still available from the two checks:

```powershell
routing check routing-condition C:\path\input.xlsx
routing check alt-bom C:\path\input.xlsx
```

To restore: `git mv` both files back, re-add the `pre-uipath` subparser in `src/routing/cli.py`
(and `legacy_script` for the root shim), see commit "Archive pre-uipath".

## Use from other code

```python
from routing.checks.routing_condition import check_routing_exists
from routing.checks.alt_bom import check_alt_bom_count

df = check_alt_bom_count(check_routing_exists(df))   # DataFrame in, DataFrame out
```

Every check has a pure `check_xxx(df, conn=None, plant=PLANT)` function and a `run(path)`
wrapper that reads and writes Excel. Pass `conn` to reuse one Snowflake connection.
