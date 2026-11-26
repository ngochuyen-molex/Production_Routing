from pathlib import Path

import pandas as pd

from routing.data.workflow import fetch_workflow_steps
from routing.opc.tpm_common import clean_string, validate_input_columns
from routing.opc.workflow_common import (
    build_source_candidates, fetch_sap_counters, prepare_targets, select_source_workflows, source_not_found_reason,
)


# ============================================================
# CONFIG
# ============================================================

REQUIRED_COLUMNS = ["Material", "group counter"]

STEP_COLUMNS = [
    "Material",
    "WorkflowName",
    "WorkflowRevision",
    "StepName",
    "RouteStepId",
    "RouteStepName",
    "Sequence",
    "ERPRouteName"
]

# ============================================================
# PREPARE INPUT
# ============================================================

def prepare_input(input_df):
    # shared: clean Material / group counter, blank rows, TargetWorkflowName
    prepared_df, blank_key_df = prepare_targets(input_df)

    # a target name contains its material, so there is nothing to conflict on: only de-duplicate
    conflict_df = prepared_df.iloc[0:0].copy()
    prepared_df = prepared_df.drop_duplicates(subset=["TargetWorkflowName"], keep="last").copy()

    return prepared_df, blank_key_df, conflict_df


# ============================================================
# CLEAN WORKFLOW RESULTS
# ============================================================

def clean_workflow_df(workflow_df):
    if workflow_df.empty:
        return workflow_df

    for column in ["Material", "WorkflowName", "WorkflowRevision", "StepName", "RouteStepId", "RouteStepName", "ERPRouteName"]:
        workflow_df[column] = workflow_df[column].apply(clean_string)

    workflow_df["Sequence"] = pd.to_numeric(workflow_df["Sequence"], errors="coerce")
    return workflow_df


# ============================================================
# FETCH WORKFLOWS BY NAME
# ============================================================

def fetch_workflows_by_name(target_workflows):
    target_workflows = list(dict.fromkeys(clean_string(name) for name in target_workflows if clean_string(name)))

    if not target_workflows:
        return pd.DataFrame(columns=STEP_COLUMNS)

    target_df = fetch_workflow_steps(target_workflows).rename(columns={"MaterialKey": "Material"})[STEP_COLUMNS]

    return clean_workflow_df(target_df)


# ============================================================
# FETCH SAP ROUTING GROUP COUNTERS
# ============================================================

# ============================================================
# FETCH ONE SOURCE WORKFLOW PER MATERIAL
# ============================================================

# ============================================================
# DUPLICATE SEQUENCE CHECK
# ============================================================

def prepare_steps(workflow_df, workflow_type):
    if workflow_df.empty:
        return workflow_df.copy(), pd.DataFrame()

    counts = workflow_df.groupby(["WorkflowName", "Sequence"], dropna=False).size().reset_index(name="RowCount")
    duplicate_keys = counts[counts["RowCount"] > 1][["WorkflowName", "Sequence"]]

    duplicate_df = workflow_df.merge(duplicate_keys, on=["WorkflowName", "Sequence"], how="inner")
    duplicate_df["WorkflowType"] = workflow_type

    prepared_df = workflow_df.drop_duplicates(subset=["WorkflowName", "Sequence"], keep="first").copy()
    return prepared_df, duplicate_df


# ============================================================
# COMPARE WORKFLOW STEPS
# ============================================================

def compare_workflows(prepared_df, target_df, source_df):
    target_df, target_duplicate_df = prepare_steps(target_df, "Target")
    source_df, source_duplicate_df = prepare_steps(source_df, "Source")

    target_map = prepared_df[["Material", "TargetWorkflowName"]].drop_duplicates()
    target_df = target_map.merge(target_df, left_on=["Material", "TargetWorkflowName"], right_on=["Material", "WorkflowName"], how="left")
    target_df = target_df.drop(columns="WorkflowName").rename(columns={
        "WorkflowRevision": "TargetRevision",
        "StepName": "TargetStepName",
        "RouteStepId": "TargetRouteStepId",
        "RouteStepName": "TargetRouteStepName",
        "ERPRouteName": "TargetERPRouteName"
    })

    source_df = source_df.rename(columns={
        "WorkflowName": "SourceWorkflowName",
        "WorkflowRevision": "SourceRevision",
        "StepName": "SourceStepName",
        "RouteStepId": "SourceRouteStepId",
        "RouteStepName": "SourceRouteStepName",
        "ERPRouteName": "SourceERPRouteName"
    })

    # pair each target workflow with its material's source steps
    source_df = target_map.merge(source_df, on="Material", how="inner")

    comparison_df = target_df.merge(source_df, on=["Material", "TargetWorkflowName", "Sequence"], how="outer", indicator=True)

    # fill source name on target-only rows so the summary keeps one row per target
    comparison_df["SourceWorkflowName"] = comparison_df.groupby("TargetWorkflowName")["SourceWorkflowName"].transform("first")

    comparison_df["TargetStepClean"] = comparison_df["TargetStepName"].apply(clean_string)
    comparison_df["SourceStepClean"] = comparison_df["SourceStepName"].apply(clean_string)
    comparison_df["StepNameMatch"] = comparison_df["TargetStepClean"] == comparison_df["SourceStepClean"]

    comparison_df["ComparisonStatus"] = "Matched"
    comparison_df.loc[comparison_df["_merge"] == "left_only", "ComparisonStatus"] = "Sequence only in target"
    comparison_df.loc[comparison_df["_merge"] == "right_only", "ComparisonStatus"] = "Sequence only in source"
    comparison_df.loc[(comparison_df["_merge"] == "both") & (~comparison_df["StepNameMatch"]), "ComparisonStatus"] = "StepName mismatch"

    comparison_df = comparison_df.drop(columns=["TargetStepClean", "SourceStepClean", "_merge"])
    comparison_df = comparison_df.sort_values(by=["Material", "TargetWorkflowName", "Sequence"], na_position="last")

    duplicate_df = pd.concat([target_duplicate_df, source_duplicate_df], ignore_index=True)
    return comparison_df, duplicate_df


# ============================================================
# WORKFLOW SUMMARY
# ============================================================

def build_summary(comparison_df):
    if comparison_df.empty:
        return pd.DataFrame(columns=[
            "Material",
            "TargetWorkflowName",
            "SourceWorkflowName",
            "TotalComparedRows",
            "MatchedRows",
            "MismatchRows",
            "WorkflowMatch"
        ])

    summary_df = (
        comparison_df.groupby(
            ["Material", "TargetWorkflowName", "SourceWorkflowName"],
            dropna=False
        )
        .agg(
            TotalComparedRows=("ComparisonStatus", "size"),
            MatchedRows=("ComparisonStatus", lambda values: (values == "Matched").sum()),
            MismatchRows=("ComparisonStatus", lambda values: (values != "Matched").sum())
        )
        .reset_index()
    )

    summary_df["WorkflowMatch"] = summary_df["MismatchRows"] == 0
    return summary_df


# ============================================================
# MISSING WORKFLOW CHECKS
# ============================================================

def build_missing_workflows(prepared_df, target_df, source_df, candidate_df):
    target_found = set(target_df["WorkflowName"].apply(clean_string)) if not target_df.empty else set()
    source_found = set(source_df["Material"].apply(clean_string)) if not source_df.empty else set()
    missing_target_df = prepared_df[
        ~prepared_df["TargetWorkflowName"].isin(target_found)
    ][["Material", "group counter", "TargetWorkflowName"]].copy()

    missing_target_df["Reason"] = "Target workflow not found"

    missing_source_df = prepared_df[
        ~prepared_df["Material"].isin(source_found)
    ][["Material", "group counter", "TargetWorkflowName"]].copy()

    return missing_target_df, source_not_found_reason(missing_source_df, candidate_df)


# ============================================================
# MAIN
# ============================================================

def main(input_file, output_file):
    input_file = Path(input_file)
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    print("Reading workflow comparison input...")

    input_df = pd.read_excel(input_file, dtype=str)
    validate_input_columns(input_df, REQUIRED_COLUMNS)

    prepared_df, blank_key_df, conflict_df = prepare_input(input_df)

    materials = prepared_df["Material"].drop_duplicates().tolist()
    target_workflows = prepared_df["TargetWorkflowName"].drop_duplicates().tolist()

    print(f"Found {len(materials)} materials and {len(target_workflows)} target workflows.")
    print("Loading target workflows...")

    target_df = fetch_workflows_by_name(target_workflows)

    print(f"Found {target_df['WorkflowName'].nunique() if not target_df.empty else 0} target workflows with {len(target_df)} step rows.")
    print("Loading SAP routing group counters...")

    counter_df = fetch_sap_counters(materials)
    candidate_df, _, already_exists_df = build_source_candidates(counter_df, prepared_df, ["Material", "group counter", "TargetWorkflowName"])

    print(f"Found {len(candidate_df)} candidate source counters. {len(already_exists_df)} target counters already exist in SAP.")
    print("Loading one source workflow per material...")

    source_df, selection_df = select_source_workflows(candidate_df, fetch_workflows_by_name)
    if source_df.empty:
        source_df = pd.DataFrame(columns=STEP_COLUMNS)

    print(f"Found {source_df['WorkflowName'].nunique() if not source_df.empty else 0} source workflows with {len(source_df)} step rows.")

    missing_target_df, missing_source_df = build_missing_workflows(prepared_df, target_df, source_df, candidate_df)
    comparison_df, duplicate_sequence_df = compare_workflows(prepared_df, target_df, source_df)
    summary_df = build_summary(comparison_df)

    print(f"Comparison rows: {len(comparison_df)}.")
    print(f"Matched rows: {(comparison_df['ComparisonStatus'] == 'Matched').sum() if not comparison_df.empty else 0}.")
    print(f"Mismatched rows: {(comparison_df['ComparisonStatus'] != 'Matched').sum() if not comparison_df.empty else 0}.")
    print(f"Missing target workflows: {len(missing_target_df)}.")
    print(f"Missing source workflows: {len(missing_source_df)}.")

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        comparison_df.to_excel(writer, sheet_name="Step Comparison", index=False)
        summary_df.to_excel(writer, sheet_name="Workflow Summary", index=False)
        target_df.to_excel(writer, sheet_name="Target Workflow Steps", index=False)
        source_df.to_excel(writer, sheet_name="Source Workflow Steps", index=False)
        missing_target_df.to_excel(writer, sheet_name="Target Not Found", index=False)
        missing_source_df.to_excel(writer, sheet_name="Source Not Found", index=False)
        selection_df.to_excel(writer, sheet_name="Source Counter Selection", index=False)
        already_exists_df.to_excel(writer, sheet_name="Target Already In SAP", index=False)
        duplicate_sequence_df.to_excel(writer, sheet_name="Duplicate Sequence", index=False)
        conflict_df.to_excel(writer, sheet_name="Conflicting Input", index=False)
        blank_key_df.to_excel(writer, sheet_name="Blank Material Counter", index=False)

    print(f"Finished: {output_file}")
