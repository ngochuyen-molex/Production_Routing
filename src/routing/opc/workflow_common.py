"""Workflow rules shared by add-workflow and compare-workflow (docs/opc.md, Shared logic).

Only rules that must stay identical in both scripts live here: target naming, the Excel target
columns, SAP group counters, source candidates and the source selection. Script-specific steps
(description / conflict check in add, step comparison in compare) stay in the scripts.
"""
import pandas as pd

from routing.core.clean import clean_string
from routing.core.config import PLANT
from routing.core.db import snowflake_session
from routing.data.routing import group_counters

SELECTION_COLUMNS = ["Material", "SourceGroupCounter", "SourceWorkflowName", "CandidateCounters", "SkippedCounters"]


def build_workflow_name(material, counter_number):
    # group counter 1 workflow is named with the material only
    return material if counter_number == 1 else f"{material}-{counter_number}"


def prepare_targets(input_df):
    """Excel rows -> (rows with TargetWorkflowName, rows with a blank Material / group counter)."""
    prepared_df = input_df.copy()

    for column in ["Material", "group counter"]:
        prepared_df[column] = prepared_df[column].apply(clean_string)

    blank_mask = (prepared_df["Material"] == "") | (prepared_df["group counter"] == "")
    blank_key_df = prepared_df[blank_mask].copy()
    prepared_df = prepared_df[~blank_mask].copy()

    counter = pd.to_numeric(prepared_df["group counter"], errors="coerce")
    prepared_df["TargetWorkflowName"] = prepared_df["Material"] + "-" + prepared_df["group counter"]
    prepared_df.loc[counter == 1, "TargetWorkflowName"] = prepared_df.loc[counter == 1, "Material"]

    return prepared_df, blank_key_df


def fetch_sap_counters(materials):
    """Active SAP routing group counters of the materials (Snowflake): Material, CounterNumber (int)."""
    materials = list(dict.fromkeys(clean_string(material) for material in materials if clean_string(material)))

    if not materials:
        return pd.DataFrame(columns=["Material", "CounterNumber"])

    with snowflake_session() as conn:
        counter_df = group_counters(conn, materials, PLANT)
    counter_df.columns = ["Material", "GroupCounter"]

    counter_df["Material"] = counter_df["Material"].apply(clean_string)
    counter_df["CounterNumber"] = pd.to_numeric(counter_df["GroupCounter"], errors="coerce")
    counter_df = counter_df.dropna(subset=["CounterNumber"])
    counter_df["CounterNumber"] = counter_df["CounterNumber"].astype(int)

    return counter_df[["Material", "CounterNumber"]].drop_duplicates()


def build_source_candidates(counter_df, prepared_df, log_columns):
    """SAP counters minus the target counters, highest first, plus both target logs.

    Returns (candidate_df, target_not_in_sap_df, target_in_sap_df); the logs have `log_columns` + Reason.
    """
    targets = prepared_df.copy()
    targets["CounterNumber"] = pd.to_numeric(targets["group counter"], errors="coerce")

    sap_keys = set(zip(counter_df["Material"], counter_df["CounterNumber"]))
    in_sap_mask = pd.Series(
        [(material, counter) in sap_keys for material, counter in zip(targets["Material"], targets["CounterNumber"])],
        index=targets.index, dtype=bool,
    )

    target_not_in_sap_df = targets[~in_sap_mask][log_columns].copy()
    target_not_in_sap_df["Reason"] = f"No active SAP routing for this group counter (plant {PLANT}, PLNTY=N)"
    target_in_sap_df = targets[in_sap_mask][log_columns].copy()
    target_in_sap_df["Reason"] = f"Group counter already exists in SAP routing (plant {PLANT})"

    # target counters are never used as source
    candidate_df = counter_df.merge(targets[["Material", "CounterNumber"]], on=["Material", "CounterNumber"], how="left", indicator=True)
    candidate_df = candidate_df[candidate_df["_merge"] == "left_only"].drop(columns="_merge")
    candidate_df["SourceWorkflowName"] = [
        build_workflow_name(material, counter)
        for material, counter in zip(candidate_df["Material"], candidate_df["CounterNumber"])
    ]
    candidate_df = candidate_df.sort_values(by=["Material", "CounterNumber"], ascending=[True, False])

    return candidate_df[["Material", "CounterNumber", "SourceWorkflowName"]], target_not_in_sap_df, target_in_sap_df


def select_source_workflows(candidate_df, fetch_steps):
    """One source per material: the highest candidate counter that exists as a workflow in OpCenter.

    `fetch_steps(names)` returns the steps of those workflows (each script passes its own column set).
    Returns (source steps, selection log).
    """
    if candidate_df.empty:
        return pd.DataFrame(), pd.DataFrame(columns=SELECTION_COLUMNS)

    candidate_steps_df = fetch_steps(candidate_df["SourceWorkflowName"].tolist())
    found_workflows = set(candidate_steps_df["WorkflowName"]) if not candidate_steps_df.empty else set()

    # highest SAP counter that exists in MES, falling back to the next highest
    selection_rows = []

    for material, group_df in candidate_df.groupby("Material", sort=False):
        counters = group_df["CounterNumber"].astype(int).astype(str).tolist()
        selected = group_df[group_df["SourceWorkflowName"].isin(found_workflows)].head(1)

        if selected.empty:
            continue

        selected_counter = str(int(selected["CounterNumber"].iloc[0]))

        selection_rows.append({
            "Material": material,
            "SourceGroupCounter": selected_counter,
            "SourceWorkflowName": selected["SourceWorkflowName"].iloc[0],
            "CandidateCounters": ", ".join(counters),
            "SkippedCounters": ", ".join(counters[:counters.index(selected_counter)])
        })

    selection_df = pd.DataFrame(selection_rows, columns=SELECTION_COLUMNS)

    if selection_df.empty:
        return pd.DataFrame(), selection_df

    source_df = candidate_steps_df[candidate_steps_df["WorkflowName"].isin(selection_df["SourceWorkflowName"])].copy()
    return source_df, selection_df


def source_not_found_reason(missing_source_df, candidate_df):
    """Reason per material without a source: no SAP counter at all, or none of them in OpCenter."""
    if missing_source_df.empty:
        return missing_source_df

    sap_found = set(candidate_df["Material"]) if not candidate_df.empty else set()

    missing_source_df["Reason"] = f"No SAP routing group counter found (plant {PLANT}, PLNTY=N) after excluding target counters"
    missing_source_df.loc[missing_source_df["Material"].isin(sap_found), "Reason"] = "No MES workflow found for any SAP routing group counter"

    return missing_source_df
