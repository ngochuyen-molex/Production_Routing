## Before UiPath

```powershell
routing pre-uipath C:\path\input.xlsx
# or, without installing:
python pre_uipath.py C:\path\input.xlsx
```

Runs routing condition, then alt BOM count, on one Snowflake connection and writes the
results back to the file (`SKIP`, `SKIP_REASON`, `group`, `group counter`, `ALT_BOM_COUNT`).
Exit code `0` = success, `1` = error, so UiPath can branch on it.

## Use from other code

```python
from routing.checks.routing_condition import check_routing_exists
from routing.pipelines.pre_uipath import pre_uipath_checks

df = pre_uipath_checks(df)            # DataFrame in, DataFrame out
```

Every check has a pure `check_xxx(df, conn=None, plant=PLANT)` function and a `run(path)`
wrapper that reads and writes Excel. Pass `conn` to reuse one Snowflake connection.
