# Ideal cycle time (`routing opc add-tpm`)

How `mlxIdealCycleTime` is calculated for Tool Plan Matrix rows. Code: `src/routing/opc/add_tpm.py`,
`build_normal_requests` (normal rows) and `build_sorting_requests` (Sorting / Lubricant rows).
Matching, output sheets and skip reasons: [`opc.md`](opc.md#add_tpmpy).

## 1. Which value is used (first match wins)

| # | Input column | Used as |
|---|---|---|
| 1 | `Ideal cycle time` | taken **as is**, no formula, even when a capacity is filled |
| 2 | `Capacity(Pcs/hr)` | Capacity, multiplier 1 |
| 3 | `Capacity` (shots/hr) | Capacity, multiplied by `Tool Cavity` (blank → 1) |
| - | none of the three | row skipped: `Missing Capacity / Ideal cycle time` |

`CapacitySource` on the Calculation Audit sheet shows which one was used.

## 2. Formula per Dept

`C` = Capacity × multiplier from section 1. Lookup = `Efficiency` / `Utilization` of the row's
`Resource` in the work center file (`EFFICIENCY_FILE`, `Eff_Util_workcenter.xlsx` on the MXV share).

| Dept | Formula | Efficiency | Utilization |
|---|---|---|---|
| `MD` | C × Eff | Excel → lookup → 1 (Excel `0` counts as blank) | not used |
| `AS` | C × Util | not used | Excel → lookup → 1 |
| `STP`, `PLT`, tool filled | C × Eff × Util | lookup → 1 | lookup → 1 |
| `STP`, `PLT`, tool blank | C × Eff × Util | Excel → 1 | Excel → 1 |
| anything else | - | row skipped: `Invalid Dept` | |

For `MD` the tool makes no difference. A tool of `0` / `0.0` counts as blank.

Result: rounded to a whole number (round half to even: `2.5 → 2`, `3.5 → 4`).

Example, `STP`, tool filled, `Capacity` 1000 shots/hr, cavity 4, lookup Eff 0.9, Util 0.8:
1000 × 4 × 0.9 × 0.8 = 2880.

## 3. Sorting / Lubricant rows

`Sorting/ Lubricant Capacity` is used as is (rounded), no efficiency, utilization or cavity.
Resource = the `Sorting/ Lubricant` column.

## 4. New or updated

- Key matches an existing TPM row → its `mlxIdealCycleTime` is replaced (Normal / Sorting Update
  Audit: old, new, `IdealCycleTimeChanged`).
- No match → new row (`Add New TPM` / `Add New Sorting`).
- Same key with different cycle times in the input → all of them skipped (`Conflicting cycle time`).
- Same Material + Resource + Tool on several group counters → highest group counter kept.

## 5. Spec for new rows

Taken from an existing row of the same material; existing rows keep their own Spec.

| Resource | Spec must |
|---|---|
| contains `YMHI` | contain `sort` or `lubrication` and **not** contain `production` |
| anything else | **not** contain `sort` or `lubrication` (so never e.g. `MD_lubrication`) |

None found → Spec blank, row on the **Spec Warning** sheet.

## 6. Watch out (review 2026-11-26)

| # | Behaviour | Effect |
|---|---|---|
| 1 | Work center file cannot be read or misses a column → only a printed message, all lookups become 1 | cycle times too high without an error; check the console output |
| 2 | Excel `0` counts as blank only for `MD` efficiency | `AS` utilization `0`, `STP`/`PLT` efficiency or utilization `0` → cycle time 0 |
| 3 | Efficiency / utilization are multiplied as they are | must be fractions (`0.85`), not percent (`85`) - in the Excel and in the lookup file |
| 4 | The result is pcs/hr × factors (a rate), stored as "cycle time" | confirm this is what OpCenter expects (not checked) |
| 5 | `Ideal cycle time` in the Excel overrides any capacity | a stale value in that column wins |
