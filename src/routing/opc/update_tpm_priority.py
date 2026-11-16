from pathlib import Path
import pandas as pd
from routing.core.config import OUTPUT_DIR
from routing.opc.tpm_common import (
    OUTPUT_COLUMNS,
    clean_string,
    clean_tool,
    fetch_existing_tool_plan_matrix,
    validate_input_columns
)

# ============================================================
# CONFIG
# ============================================================

INPUT_FILE = Path(
    r"C:\Users\nguyeb3\OneDrive - kochind.com\change_routing.xlsx"
)

OUTPUT_FILE = OUTPUT_DIR / "update_tpm_priority_result.xlsx"

# Optional column: Tool (filled -> only that tool's row, blank -> all rows of Material + Resource)
REQUIRED_COLUMNS = [
    "Material",
    "Resource",
    "Priority"
]

# ============================================================
# HELPERS
# ============================================================
def build_priority_key(row):
    material = clean_string(row["Material"])
    resource = clean_string(row["Resource"])
    tool = clean_tool(row["Tool"])
    return f"{material}|{resource}|{tool}" if tool else f"{material}|{resource}"


def add_existing_keys(existing_df):
    keyed_df = existing_df.copy()
    keyed_df["_key_general"] = keyed_df["Name"].apply(clean_string) + "|" + keyed_df["Resource"].apply(clean_string)
    keyed_df["_key_tool"] = keyed_df["_key_general"] + "|" + keyed_df["ToolPlan"].apply(clean_tool)
    return keyed_df


# ============================================================
# VALIDATE PRIORITY INPUT
# ============================================================
def prepare_priority_input(input_df):

    update_df = input_df.copy()

    update_df["Material"] = update_df["Material"].apply(clean_string)
    update_df["Resource"] = update_df["Resource"].apply(clean_string)
    update_df["Tool"] = update_df["Tool"].apply(clean_tool) if "Tool" in update_df.columns else ""
    update_df["Priority"] = pd.to_numeric(update_df["Priority"], errors="coerce")

    blank_key_rows = update_df[(update_df["Material"] == "") | (update_df["Resource"] == "")].copy()

    update_df = update_df[(update_df["Material"] != "") & (update_df["Resource"] != "")].copy()

    missing_priority_rows = update_df[update_df["Priority"].isna()].copy()

    update_df = update_df[update_df["Priority"].notna()].copy()

    update_df["Priority"] = update_df["Priority"].round().astype(int)

    # Tool filled: Material|Resource|Tool. Tool blank: Material|Resource.
    update_df["_key"] = update_df.apply(build_priority_key, axis=1)

    conflicting_priorities = (
        update_df.groupby("_key")["Priority"]
        .nunique()
        .reset_index(name="PriorityCount")
    )

    conflicting_priorities = conflicting_priorities[
        conflicting_priorities["PriorityCount"] > 1
    ]

    conflict_rows = update_df[
        update_df["_key"].isin(conflicting_priorities["_key"])
    ].copy()

    update_df = update_df[
        ~update_df["_key"].isin(conflicting_priorities["_key"])
    ].copy()

    update_df = update_df.drop_duplicates(subset=["_key"], keep="last")

    return update_df, blank_key_rows, missing_priority_rows, conflict_rows


# ============================================================
# FIND UNMATCHED INPUT ROWS
# ============================================================
def get_unmatched_input_rows(update_df, existing_df):
    keyed_existing = add_existing_keys(existing_df)

    general_keys = set(keyed_existing["_key_general"])
    tool_keys = set(keyed_existing["_key_tool"])

    matched_mask = update_df.apply(
        lambda row: row["_key"] in tool_keys if row["Tool"] else row["_key"] in general_keys,
        axis=1
    )

    return update_df[~matched_mask].drop(columns="_key", errors="ignore").copy()


# ============================================================
# UPDATE PRIORITY
# ============================================================
def update_priority(existing_df, update_df):

    result_df = add_existing_keys(existing_df)

    priority_lookup = update_df.set_index("_key")["Priority"].to_dict()

    # Tool-specific match has priority. If unavailable, use Material + Resource.
    result_df["_NewPriority"] = result_df["_key_tool"].map(priority_lookup).fillna(
        result_df["_key_general"].map(priority_lookup)
    )

    matching_mask = result_df["_NewPriority"].notna()

    updated_rows_df = result_df.loc[matching_mask].copy()

    updated_rows_df["OldPriority"] = updated_rows_df["mlxPriority"]

    updated_rows_df["NewPriority"] = updated_rows_df["_NewPriority"].astype(int)

    # Compare as numbers: "1", 1.0 and 1 are the same priority
    old_priority = pd.to_numeric(updated_rows_df["OldPriority"], errors="coerce")
    new_priority = pd.to_numeric(updated_rows_df["NewPriority"], errors="coerce")
    updated_rows_df["PriorityChanged"] = old_priority.ne(new_priority)

    result_df.loc[matching_mask, "mlxPriority"] = (
        result_df.loc[matching_mask, "_NewPriority"]
        .astype(int)
        .to_numpy()
    )

    result_df.loc[matching_mask, "RowType"] = "Priority Updated"

    updated_rows_df["RowType"] = "Priority Updated"

    helper_columns = ["_key_general", "_key_tool", "_NewPriority"]
    result_df = result_df.drop(columns=helper_columns)
    updated_rows_df = updated_rows_df.drop(columns=helper_columns)

    result_df = result_df.sort_values(
        by=["Name", "mlxPriority", "Resource", "ToolPlan"],
        na_position="last"
    )

    return result_df[OUTPUT_COLUMNS], updated_rows_df


# ============================================================
# BUILD UPLOAD OUTPUT (same layout as add_tpm)
# ============================================================
def build_upload_output(result_df):
    upload_df = result_df.reindex(columns=OUTPUT_COLUMNS)

    # All rows already exist in the TPM -> Update. All rows of the material are written
    # because ReplaceDetails replaces the full detail list.
    upload_df.insert(0, "Execute", "Update")
    upload_df.insert(1, "Completion Message", "")

    erp_route_pos = upload_df.columns.get_loc("mlxERPRoute") + 1
    upload_df.insert(erp_route_pos, "ReplaceDetails", "True")
    upload_df.insert(erp_route_pos + 1, "ReplaceDetailsSubentityListNames", "Details")

    return upload_df

# ============================================================
# MAIN
# ============================================================

def main(input_file=INPUT_FILE, output_file=OUTPUT_FILE):
    input_file = Path(input_file)
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    print("Reading priority update file...")

    input_df = pd.read_excel(input_file, dtype=str)
    validate_input_columns(input_df, REQUIRED_COLUMNS)

    update_df, blank_key_df, missing_priority_df, conflict_df = (
    prepare_priority_input(input_df))

    materials = (
        update_df["Material"]
        .drop_duplicates()
        .tolist()
    )

    print(f"Found {len(materials)} materials.")
    print("Loading existing Tool Plan Matrix...")

    existing_df = fetch_existing_tool_plan_matrix(materials)

    print(f"Found {len(existing_df)} existing TPM rows.")

    not_found_df = get_unmatched_input_rows(update_df, existing_df)

    result_df, updated_rows_df = update_priority(
        existing_df,
        update_df
    )

    upload_df = build_upload_output(result_df)

    print(f"Updated {len(updated_rows_df)} TPM rows ({updated_rows_df['PriorityChanged'].sum()} with a new value).")
    print(f"Unmatched input rows: {len(not_found_df)}.")

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:

        upload_df.to_excel(writer, sheet_name="Updated TPM Output", index=False)

        updated_rows_df.to_excel(writer, sheet_name="Updated Rows Audit", index=False)

        not_found_df.to_excel(writer, sheet_name="Material Resource Not Found", index=False)

        missing_priority_df.to_excel(writer, sheet_name="Missing Priority", index=False)

        blank_key_df.to_excel(writer, sheet_name="Blank Material Resource", index=False)

        conflict_df.to_excel(writer, sheet_name="Conflicting Priority", index=False)

    print(f"Finished: {output_file}")


if __name__ == "__main__":
    main()