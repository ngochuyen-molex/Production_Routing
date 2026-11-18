# Operation check

`routing check operation-values FILE` compares the input Excel with the values of the SAP
routing operations, read from Snowflake. One check covers capacity, standard values and
efficiency / utilization; before 2026-11-16 these were two commands
(`operation-capacity` and `util-eff`), which are kept as aliases.

Code: `src/routing/data/operation_values.py` (query), `src/routing/checks/operation_values.py` (rules).

## What is checked against what

| Rule | How the operation is picked | Compared with (Excel) | Output |
|---|---|---|---|
| Production capacity | operation `0020` | `Capacity` | `BASE_QTY_0020`, `CHECK_0020` |
| Sorting / lubricant capacity | resource (work center) contains `YMHI` | `Sorting Capacity` (optional column) | `SORTING_OPERATION`, `BASE_QTY_SORTING`, `CHECK_SORTING` |
| Final step capacity (pack & send to WH) | control key `PP94` | `Capacity × Tool Cavity` | `FINAL_OPERATION`, `BASE_QTY_FINAL`, `CHECK_FINAL` |
| Standard values | operation `0020` | must be `1.000` `H` (no Excel column) | `SETUP_0020`, `MACHINE_0020`, `LABOR_0020`, `STD_VALUE_CHECK` |
| Header value (unit conversion) | operation `0020` | header qty = `Tool Cavity` (operation qty reported only) | `HEADER_QTY_0020`, `OPERATION_QTY_0020`, `CHECK_HEADER` |
| Efficiency / utilization | operation `0020` | `Efficiency`, `Utilization` | `RTG_EFFICIENCY`, `RTG_UTILIZATION`, `EFF_CHECK`, `UTIL_CHECK` |

The final step is found by control key, not by number, because a sorting step moves it:

| Routing | 0020 | 0030 | 0040 |
|---|---|---|---|
| Normal (e.g. 5052771989) | MN15-09 PP01, 1,000 | **OMINS PP94, 8,000** | |
| With lubricant (e.g. 5052760989) | MN15-14 PP01, 923 | YMHI-1 PP96, 100,000 | **OMINS PP94, 7,384** |

Result values: `Match`, `Mismatch`, `Missing capacity` (Excel value blank), `No routing found`.

`CHECK_FINAL` - the final step is **PP94 only**; `ZP04` is the control key of a **trial routing** and
is never taken as the final step:

| `CHECK_FINAL` | Meaning | What to do |
|---|---|---|
| `Match` | PP94 base qty = `Capacity × Tool Cavity` | nothing |
| `Mismatch` | PP94 base qty differs | correct the PP94 base qty in CA02 (or the Excel) |
| `Missing capacity` | `Capacity` or `Tool Cavity` blank in the Excel | fill the Excel |
| `No final step PP94 (ZP04 = trial routing)` | routing found, it ends with ZP04: a trial routing | check the right (non-trial) routing was matched; fill group / group counter |
| `No final step PP94` | routing found, but it has neither PP94 nor ZP04 (e.g. regrinding: 0020 is the only step) | check in CA02 whether a final step is expected |
| `No routing found` | no routing matches material + resource (+ tool), or group / group counter | check the input; run `routing-condition` / `delete-status` |

The summary printed at the end counts these as `Routing without final step PP94: N`.

`CHECK_SORTING` is blank when the routing has no YMHI operation and no `Sorting Capacity` is given,
and `Sorting capacity given, no YMHI operation` when only the Excel has one.
`EFF_CHECK` / `UTIL_CHECK` show `No Excel efficiency` / `No Excel utilization` when the input has no value.
All comparisons use a tolerance of `0.001`.

## Standard values rule (setup / machine / labor)

At operation `0020`, setup, machine time and labor time must each be **`1.000`** with unit **`H`**.
The cycle time itself is carried by base quantity, so these three are expected to stay at 1.

**This rule is applied to every row — no department, work center or control key is exempted.**
`STD_VALUE_CHECK` is `Match`, or it names each field that is wrong, e.g. `Setup 0.000`,
`Setup 0.000; Labor 0.000`, `Machine unit blank`. Anything other than `Match` means re-inspect
the routing in SAP (CA02 → operation detail → Standard Values).

### Known exceptions at plant 1901 (checked 2026-11-16)

These exist in the data today and will be reported. They are listed so a non-`Match` result is
not mistaken for a bug in the check. Counts are over the 10,770 `0020` operations that pass the
query filters: setup ≠ 1 in **1,701**, machine ≠ 1 in **5**, labor ≠ 1 in **6**, a unit other
than `H` in **693**.

Nearly every exception is the same shape: **setup `0.000` while machine and labor are still
`1.000`**, with a blank setup unit (which is also what most "unit not H" rows are).

| Control key | Rows with setup ≠ 1 | Typical work center / operation |
|---|---|---|
| PP01 | 1,397 | `PM5-A` / `PM5-B` PLATING, some MOLDING INJECTION (e.g. `MF50-07`) |
| MP03 | 152 | `C_AUTO` "Hifix Automation line OPC" |
| MC01 | 132 | `OSRPKE` "LENGTH CHECK & PACKING" |
| PP96 | 9 | `ASMTRIAL` "TRIAL FOR ASSEMBLY MANUAL" |
| ZP04 | 9 | `YMHI-4` "MD-Regrinding" |
| PP03 | 2 | `C_AUTO` "Folding OUTER SHELL" |

Machine and labor time almost never deviate. The full list:

| Material | Routing | Work center | Setup | Machine | Labor | Note |
|---|---|---|---|---|---|---|
| 2240570000 | B224057/01 | BPACKING | 0.000 | **1000.000** | 0.000 | ENG-BPACKING, machine time looks like a data-entry error |
| 788366001 | P8836600/03, /04 | PM2-A, PM2-B | 0.000 | 0.000 | 0.000 | PLATING, all three blank |
| 788525001 | P8852500/03, /04 | PM2-A, PM2-B | 0.000 | 0.000 | 0.000 | PLATING, all three blank |
| 5027893089 | M0278930/25 | YMHI-2 | 0.000 | 1.000 | 0.000 | Hi-COATING |

## Header value (conversion of units of measure)

In SAP this is the **Conversion of Units of Measure** box on the operation screen, e.g.
`Header 8 PC <=> Operation 1 CYL`; in the data lake it is `PLPO.UMREZ` (header) and
`PLPO.UMREN` (operation).

At operation `0020` the check requires **header qty = `Tool Cavity`** from the Excel: one cylinder
(shot) yields one cavity's worth of pieces, so the conversion must carry the cavity count.

`CHECK_HEADER` is `Match`, `Header <n>, Tool Cavity <n>` when they disagree,
`No Excel tool cavity` when the input has no `Tool Cavity`, or `No routing found`.

**The operation qty (`UMREN`) is reported in `OPERATION_QTY_0020` but never judged** — it is `1`
in every one of the 10,770 `0020` operations at plant 1901, so a rule on it could not catch
anything today. The value is output so an unusual one is still visible.

Checked at plant 1901 on 2026-11-16:
- header qty is always populated (never null or 0) and ranges from **1 to 72**.
- header qty is `1` in 4,963 rows (46%), which is correct for assembly and other single-piece
  work centers where the tool cavity is also 1.
- On the molding rows checked against a real input file, header qty matched `Tool Cavity`
  exactly every time (e.g. 16→16, 14→14, 8→8).

The `header qty = Tool Cavity` rule was derived from that observed match, not from an SAP
specification. If a department sets the conversion differently, the rule will report it as a
mismatch and needs revisiting.

## Efficiency / utilization

In SAP these are the **Eff. in Routing** / **Utl. in Routing** fields on the operation's
User-Specific Fields tab (activity types `RTGEFF` / `RTGUTL`); in the data lake they are
`PLPO.USR04` and `PLPO.USR05`.

They are only ever filled at operation `0020`: every `0030` row (12,272) and every `0040` row
(1,256) at plant 1901 has `0`. The check therefore compares them at `0020` only — asking for
them at the sorting or final step would compare against zeros.

Exceptions to expect:
- **`0` at 0020 is normal for non-molding work centers**: 4,712 of 10,770 rows (every MC01, AP03
  and ZP04 operation, 327 of 565 PP96, 3,954 of 9,694 PP01). These are flagged only if the Excel
  carries a value for them.
- **One out-of-range value**: material `5016441810`, routing `M0164418/15`, work center `IOM-8`
  (MOLDING INJECTION) has efficiency `1.010`.

## Query filters

Materials come from the input file's `Material` column (batched `MATNR IN (...)`).

Rows are excluded when: the routing header or sequence or operation is deleted
(`LOEKZ`, `DW_SOFT_DELETE_FLAG`), the routing is flagged `DELKZ = 'X'`, the task list is not a
routing (`PLNTY != 'N'`), or the **material** is flagged for deletion (`MARC.LVORM`) or
discontinued (`MARC.MMSTA = 'E3'`).

The `MARC` filter was added on 2026-11-16 when the two checks merged. It previously applied only
to the efficiency / utilization check, so the capacity check now sees fewer rows: at `0020` it
excludes 1,524 rows for `LVORM` and 804 for `MMSTA = 'E3'`. The work-center join also requires
`CRHD.OBJTY = 'A'`; this changes nothing on current data (all 22,652 returned operations already
match) and is kept for parity with the old efficiency query.

## Control keys seen at plant 1901 (checked 2026-11-16)

| Control key | Where | Meaning |
|---|---|---|
| PP01 | 0020 (a few at 0030) | production |
| PP94 | always the last operation: 0030, 0040, 0050, 0060 | inspection, pack & send to WH |
| ZP04 | last operation at 0030 / 0040 (OMINS etc.); 0020 on YMHI-4 | **trial routing** (pack, or regrinding) - never the final step |
| PP96 | 0030 on YMHI | sorting / lubricant |
| PP96 | 0020 on MDTR, PLTT, ASTR, ASMT, STPT | other single-step processes |
| PPSB | sub-operation under 0020 (e.g. 0020/0010 L505276B) | not returned by the current PLAS join, not checked |

## Known gaps (rules kept simple on purpose)

1. **Production is not always at 0020.** The check then shows `No routing found` / `Mismatch` on 0020,
   and the standard-value and eff / util rules have nothing to read.
   - Automation cutting first: 0020 `C_AUTO1` AP03, production 0030 `A505087A` PP01
     (groups A0508706/06, A0508708/05, A0508712/06, A0508715/06, A0532605/03, A0532606/07, A0532615/05).
   - No 0020 at all: 0030 `OASR4E` PP01 (group I0291385/26 and /27, material 2029138015).
   - Two production steps: 0020 PLATING `PM2-A` and 0030 rewind `PR-01`, both PP01 (P0541470/02).
   Possible fix: use 0020 when it is PP01, else the first PP01 operation.
2. **YMHI is not always sorting.** In hi-coat and regrinding routings YMHI *is* the 0020 production
   step, so it is reported as sorting too:
   - Hi-coat: 0020 `YMHI` PP01 "HICOAT M/C" (M5133701/03 and /04).
   - Regrinding: 0020 `YMHI-4` ZP04 "MD-Regrinding", the only step (M6750000/01, M9675002/01).
   Possible fix: count YMHI as sorting only after 0020 (`OPERATION_NUMBER > '0020'`), or require PP96.
3. **Final step is PP94 only (decided 2026-11-18).** About 2,900 routings end with **ZP04** instead
   (e.g. OMINS, OPMINS; P0541470/02 ends 0040 `OPMINS` ZP04). ZP04 is the control key of **trial
   routings**, so it is never accepted as the final step; `CHECK_FINAL` says why there is no PP94
   (meanings: "Result values" above). The query fetches ZP04 operations only for that message.
   Logged in `docs/verification.md` E.
4. **Regrinding has no final step** (production is the only operation), so `CHECK_FINAL` cannot match.
5. **Sub-operations (PPSB)** are not read. If their base quantity can differ from the 0020 main
   operation, they need their own query.
6. **Resource matching** (no group / group counter in Excel) takes the lowest group counter in which
   the resource appears; with several routings for the same resource, fill group + group counter.
