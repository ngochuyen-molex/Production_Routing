"""Compare the Excel input with the values of the SAP routing operations.

Rules (details, exceptions and known gaps in docs/operation_values.md):
  PRODUCTION   operation 0020                         base qty vs Capacity
  SORTING      operation whose resource contains YMHI base qty vs Sorting Capacity
  FINAL        operation with control key PP94        base qty vs Capacity x Tool Cavity
  STD VALUES   operation 0020: setup / machine / labor must be 1.000 H (all rows, no exception)
  HEADER       operation 0020: header qty (UMREZ) vs Tool Cavity; operation qty reported only
  EFF / UTIL   operation 0020: PLPO.USR04 / USR05 vs Excel Efficiency / Utilization

Excel columns: Material, Resource, Capacity, Tool Cavity,
               optional Sorting Capacity (or Sorting/ Lubricant Capacity),
               optional Efficiency / Utilization / Tool / group / group counter
Matching: group + group counter when both filled, else Resource (+ Tool in description).
Note: when routing is not found, check delete status as well.
"""
import pandas as pd

from routing.core.clean import clean_material_series
from routing.core.config import PLANT
from routing.core.db import snowflake_session
from routing.core.excel import read_input, write_output
from routing.data import operation_values as operation_values_data

TOLERANCE = 0.001
PRODUCTION_OPERATION = "0020"
SORTING_RESOURCE = "YMHI"
FINAL_CONTROL_KEY = "PP94"
TRIAL_CONTROL_KEY = "ZP04"  # trial routing, not a final step

# Standard values required at operation 0020.
STANDARD_VALUE = 1.0
STANDARD_VALUE_UNIT = "H"
STANDARD_VALUES = [("Setup", "SETUP_TIME", "SETUP_UNIT"),
                   ("Machine", "MACHINE_TIME", "MACHINE_UNIT"),
                   ("Labor", "LABOR_TIME", "LABOR_UNIT")]

# Conversion of units of measure at 0020: header qty must equal the tool cavity.
# The operation qty is reported but not checked (it is 1 everywhere at plant 1901).

OUTPUT_COLUMNS = ["MATCH_METHOD", "ROUTING_GROUP", "ROUTING_GROUP_COUNTER", "ROUTING_DESCRIPTION",
                  "BASE_QTY_0020", "SORTING_OPERATION", "BASE_QTY_SORTING",
                  "FINAL_OPERATION", "BASE_QTY_FINAL",
                  "CHECK_0020", "CHECK_SORTING", "CHECK_FINAL",
                  "SETUP_0020", "MACHINE_0020", "LABOR_0020", "STD_VALUE_CHECK",
                  "HEADER_QTY_0020", "OPERATION_QTY_0020", "CHECK_HEADER",
                  "RTG_EFFICIENCY", "RTG_UTILIZATION", "EFF_CHECK", "UTIL_CHECK"]

NUMERIC_COLUMNS = ["BASE_QUANTITY", "CONV_HEADER_QTY", "CONV_OPERATION_QTY",
                   "SETUP_TIME", "MACHINE_TIME", "LABOR_TIME",
                   "EFFICIENCY", "UTILIZATION"]
TEXT_COLUMNS = ["RESOURCE_NAME", "CONTROL_KEY", "ROUTING_DESCRIPTION", "OPERATION_NUMBER",
                "SETUP_UNIT", "MACHINE_UNIT", "LABOR_UNIT"]


def _compare(expected, actual):
    if pd.notna(expected) and actual is not None and pd.notna(actual):
        return "Match" if abs(actual - expected) < TOLERANCE else "Mismatch"
    if actual is None or pd.isna(actual):
        return "No routing found"
    return "Missing capacity"


def _compare_sorting(expected, actual, routing_found):
    """Sorting is optional: no YMHI operation and no Sorting Capacity is fine."""
    if not routing_found:
        return "No routing found"
    if actual is None:
        return "Sorting capacity given, no YMHI operation" if pd.notna(expected) else ""
    return _compare(expected, actual)


def _compare_final(expected, actual, matches):
    """Final step is PP94 only. ZP04 marks a trial routing, it is never the final step."""
    if matches.empty:
        return "No routing found"
    if actual is None:
        if (matches["CONTROL_KEY"] == TRIAL_CONTROL_KEY).any():
            return f"No final step {FINAL_CONTROL_KEY} ({TRIAL_CONTROL_KEY} = trial routing)"
        return f"No final step {FINAL_CONTROL_KEY}"
    return _compare(expected, actual)


def _compare_value(expected, actual, missing_text):
    """Excel value vs routing value; `missing_text` when the Excel value is blank."""
    if actual is None or pd.isna(actual):
        return "No routing found"
    if pd.isna(expected):
        return missing_text
    return "Match" if abs(actual - expected) < TOLERANCE else "Mismatch"


def _first(ops):
    """(operation number, base quantity) of the first operation, or ("", None)."""
    if ops.empty:
        return "", None
    row = ops.sort_values("OPERATION_NUMBER").iloc[0]
    return row["OPERATION_NUMBER"], row["BASE_QUANTITY"]


def pick_operations(matches):
    """Split the operations of one matched routing into production / sorting / final."""
    production = matches[matches["OPERATION_NUMBER"] == PRODUCTION_OPERATION]
    sorting = matches[matches["RESOURCE_NAME"].str.contains(SORTING_RESOURCE, na=False)]
    final = matches[matches["CONTROL_KEY"] == FINAL_CONTROL_KEY]
    return production, _first(sorting), _first(final)


def check_standard_values(production):
    """Setup / machine / labor at 0020 must be 1.000 H. Applies to every row.
    Returns (setup, machine, labor, result): result names what is wrong."""
    if production.empty:
        return None, None, None, "No routing found"

    row = production.sort_values("OPERATION_NUMBER").iloc[0]
    times = [row[time_column] for _, time_column, _ in STANDARD_VALUES]
    problems = []

    for label, time_column, unit_column in STANDARD_VALUES:
        value = row[time_column]
        unit = str(row[unit_column]).strip().upper()

        if pd.isna(value) or abs(value - STANDARD_VALUE) >= TOLERANCE:
            problems.append(f"{label} {value:.3f}" if pd.notna(value) else f"{label} blank")
        elif unit != STANDARD_VALUE_UNIT:
            problems.append(f"{label} unit {unit or 'blank'}")

    return (*times, "; ".join(problems) if problems else "Match")


def check_header_value(production, tool_cavity):
    """Conversion of units of measure at 0020: header qty must equal Tool Cavity.
    The operation qty is returned for reference only, it is never judged.
    Returns (header qty, operation qty, result)."""
    if production.empty:
        return None, None, "No routing found"

    row = production.sort_values("OPERATION_NUMBER").iloc[0]
    header_qty = row["CONV_HEADER_QTY"]
    operation_qty = row["CONV_OPERATION_QTY"]

    if pd.isna(tool_cavity):
        return header_qty, operation_qty, "No Excel tool cavity"
    if pd.isna(header_qty) or abs(header_qty - tool_cavity) >= TOLERANCE:
        header_text = f"{header_qty:g}" if pd.notna(header_qty) else "blank"
        return header_qty, operation_qty, f"Header {header_text}, Tool Cavity {tool_cavity:g}"
    return header_qty, operation_qty, "Match"


def check_routing_values(df, conn=None, plant=PLANT):
    df = df.copy()
    df["Material"] = clean_material_series(df["Material"])
    df["Resource"] = df["Resource"].astype(str).str.strip()

    for col in ["Tool", "group", "group counter"]:
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)

    df["Capacity"] = pd.to_numeric(df["Capacity"], errors="coerce")

    def optional(*names):
        """First column present out of `names`, as numbers; all-NaN when none is there."""
        for name in names:
            if name in df.columns:
                return pd.to_numeric(df[name], errors="coerce")
        return pd.Series(float("nan"), index=df.index)

    sorting_capacity = optional("Sorting Capacity", "Sorting/ Lubricant Capacity")
    excel_efficiency = optional("Efficiency")
    excel_utilization = optional("Utilization")
    tool_cavities = optional("Tool Cavity")

    with snowflake_session(conn) as c:
        sf_df = operation_values_data.operation_values(c, df["Material"].unique().tolist(), plant)

    sf_df["Material"] = sf_df["MATNR"].str.lstrip("0")
    sf_df["ROUTING_GROUP"] = sf_df["ROUTING_GROUP"].astype(str).str.strip()
    sf_df["GROUP_COUNTER"] = pd.to_numeric(sf_df["GROUP_COUNTER"], errors="coerce").astype("Int64").astype(str)

    for col in TEXT_COLUMNS:
        sf_df[col] = sf_df[col].fillna("").astype(str).str.strip()
    for col in NUMERIC_COLUMNS:
        sf_df[col] = pd.to_numeric(sf_df[col], errors="coerce")

    out = {key: [] for key in OUTPUT_COLUMNS}

    for idx, row in df.iterrows():
        mat = row["Material"]
        grp = row["group"]
        gc = row["group counter"]
        tool = row["Tool"]
        capacity = row["Capacity"]
        tool_cavity = tool_cavities[idx]
        capacity_final = row["Capacity"] * tool_cavity

        if grp and gc:
            matches = sf_df[(sf_df["Material"] == mat) & (sf_df["ROUTING_GROUP"] == grp) & (sf_df["GROUP_COUNTER"] == gc)]
            method = "Group+Counter"
        else:
            # find the routing by resource, then keep all its operations (final step has another resource)
            hit = sf_df[(sf_df["Material"] == mat) & (sf_df["RESOURCE_NAME"] == row["Resource"])]
            if tool:
                hit = hit[hit["ROUTING_DESCRIPTION"].str.contains(tool, na=False, regex=False)]
                method = "Resource+Tool"
            else:
                method = "Resource"
            matches = hit
            if not hit.empty:
                first = hit.sort_values("GROUP_COUNTER").iloc[0]
                matches = sf_df[(sf_df["Material"] == mat) & (sf_df["ROUTING_GROUP"] == first["ROUTING_GROUP"])
                                & (sf_df["GROUP_COUNTER"] == first["GROUP_COUNTER"])]

        production, (sort_op, qty_sort), (final_op, qty_final) = pick_operations(matches)
        qty_20 = _first(production)[1]
        setup, machine, labor, std_value_check = check_standard_values(production)
        header_qty, operation_qty, header_check = check_header_value(production, tool_cavity)

        efficiency = production["EFFICIENCY"].iloc[0] if not production.empty else None
        utilization = production["UTILIZATION"].iloc[0] if not production.empty else None

        out["MATCH_METHOD"].append(method)
        out["BASE_QTY_0020"].append(qty_20)
        out["SORTING_OPERATION"].append(sort_op)
        out["BASE_QTY_SORTING"].append(qty_sort)
        out["FINAL_OPERATION"].append(final_op)
        out["BASE_QTY_FINAL"].append(qty_final)
        out["CHECK_0020"].append(_compare(capacity, qty_20))
        out["CHECK_SORTING"].append(_compare_sorting(sorting_capacity[idx], qty_sort, not matches.empty))
        out["CHECK_FINAL"].append(_compare_final(capacity_final, qty_final, matches))

        out["SETUP_0020"].append(setup)
        out["MACHINE_0020"].append(machine)
        out["LABOR_0020"].append(labor)
        out["STD_VALUE_CHECK"].append(std_value_check)

        out["HEADER_QTY_0020"].append(header_qty)
        out["OPERATION_QTY_0020"].append(operation_qty)
        out["CHECK_HEADER"].append(header_check)

        out["RTG_EFFICIENCY"].append(efficiency)
        out["RTG_UTILIZATION"].append(utilization)
        out["EFF_CHECK"].append(_compare_value(excel_efficiency[idx], efficiency, "No Excel efficiency"))
        out["UTIL_CHECK"].append(_compare_value(excel_utilization[idx], utilization, "No Excel utilization"))

        first = matches.iloc[0] if not matches.empty else None
        out["ROUTING_GROUP"].append(first["ROUTING_GROUP"] if first is not None else "")
        out["ROUTING_GROUP_COUNTER"].append(first["GROUP_COUNTER"] if first is not None else "")
        out["ROUTING_DESCRIPTION"].append(first["ROUTING_DESCRIPTION"] if first is not None else "")

    for key, values in out.items():
        df[key] = values
    return df


def summary(df):
    capacity_checks = ["CHECK_0020", "CHECK_SORTING", "CHECK_FINAL"]
    mismatch = (df[capacity_checks] == "Mismatch").any(axis=1).sum()
    no_routing = ((df["CHECK_0020"] == "No routing found") & (df["CHECK_FINAL"] == "No routing found")).sum()
    all_match = ((df["CHECK_0020"] == "Match") & (df["CHECK_FINAL"] == "Match")
                 & df["CHECK_SORTING"].isin(["Match", ""])).sum()
    std_value_problem = (~df["STD_VALUE_CHECK"].isin(["Match", "No routing found"])).sum()
    header_problem = (~df["CHECK_HEADER"].isin(["Match", "No routing found"])).sum()
    no_final = df["CHECK_FINAL"].str.startswith(f"No final step {FINAL_CONTROL_KEY}").sum()
    eff_util_mismatch = ((df["EFF_CHECK"] == "Mismatch") | (df["UTIL_CHECK"] == "Mismatch")).sum()

    return (f"  Capacity all match: {all_match}\n"
            f"  Capacity mismatch (0020, sorting or final): {mismatch}\n"
            f"  No routing found: {no_routing}\n"
            f"  Routing without final step {FINAL_CONTROL_KEY}: {no_final}\n"
            f"  Standard values not 1.000 H at 0020: {std_value_problem}\n"
            f"  Header qty not equal to Tool Cavity at 0020: {header_problem}\n"
            f"  Efficiency / utilization mismatch: {eff_util_mismatch}")


def run(input_path, output_path=None, sheet_name="Sheet1", conn=None, plant=PLANT):
    df = check_routing_values(read_input(input_path, sheet_name=sheet_name), conn=conn, plant=plant)
    saved = write_output(df, output_path or input_path)
    print(f"Done. {len(df)} rows processed. Saved to: {saved}")
    print(summary(df))
    return df
