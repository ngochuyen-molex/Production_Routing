"""Does the routing already exist for each Material + Resource (+ Tool / WorkCenter / Sorting)?

Excel columns: Material, Resource, Tool (optional), WorkCenter (optional), Sorting/ Lubricant (optional)
Adds: group, group counter, SKIP, SKIP_REASON, ROUTING_DESCRIPTION
"""
import pandas as pd

from routing.core.clean import clean_material_series, from_sap_matnr
from routing.core.config import PLANT
from routing.core.db import snowflake_session
from routing.core.excel import read_input, write_output
from routing.data import routing as routing_data

SAFE_TO_ADD = 0
ROUTING_EXISTS = 1
NOT_AT_PLANT = 2
ROUTING_INACTIVE = 3  # exists in SAP with deletion flag (PLKO.DELKZ) set: untick it to reactivate

SKIP_REASONS = {
    SAFE_TO_ADD: "Safe to add",
    ROUTING_EXISTS: "Routing already exists",
    NOT_AT_PLANT: "Material not at plant",
    ROUTING_INACTIVE: "Inactive",
}

OPTIONAL_COLUMNS = ["Tool", "WorkCenter", "Sorting/ Lubricant"]


def check_routing_exists(df, conn=None, plant=PLANT):
    df = df.copy()
    df["Material"] = clean_material_series(df["Material"])
    df["Resource"] = df["Resource"].astype(str).str.strip()

    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].fillna("").astype(str).str.strip()

    materials = df["Material"].unique().tolist()
    with snowflake_session(conn) as c:
        plant_df = routing_data.materials_at_plant(c, materials, plant)
        routing_df = routing_data.routings_with_resource(c, materials, plant)

    plant_df["Material"] = plant_df["MATNR"].map(from_sap_matnr)
    routing_df["Material"] = routing_df["MATNR"].map(from_sap_matnr)
    routing_df["GROUP_COUNTER"] = routing_df["GROUP_COUNTER"].astype(str).str.lstrip("0")
    routing_df["DELETION_FLAG"] = routing_df["DELETION_FLAG"].fillna("").astype(str).str.strip()

    materials_at_plant = set(plant_df["Material"])

    skip_flags = []
    skip_reasons = []
    routing_descriptions = []
    routing_groups = []
    group_counters = []

    for _, row in df.iterrows():
        mat = row["Material"]
        res = row["Resource"]

        # Check 1: is the material at the plant?
        if mat not in materials_at_plant:
            skip_flags.append(NOT_AT_PLANT)
            skip_reasons.append(SKIP_REASONS[NOT_AT_PLANT])
            routing_descriptions.append("")
            routing_groups.append("")
            group_counters.append("")
            continue

        # Check 2: does a routing with this resource (and tool / wc / sorting in the description) exist?
        # Deletion-flagged routings (PLKO.DELKZ) count too; an active one is preferred over a flagged one.
        match = routing_df[(routing_df["Material"] == mat) & (routing_df["RESOURCE"] == res)] if res else pd.DataFrame()
        if not match.empty:
            match = match.sort_values("DELETION_FLAG", kind="stable")

        found = None
        for _, m_row in match.iterrows():
            desc = str(m_row["ROUTING_DESCRIPTION"])
            if all(not value or value in desc for value in (row["Tool"], row["WorkCenter"], row["Sorting/ Lubricant"])):
                found = m_row
                break

        if found is not None:
            flag = ROUTING_INACTIVE if found["DELETION_FLAG"] == "X" else ROUTING_EXISTS
            skip_flags.append(flag)
            skip_reasons.append(SKIP_REASONS[flag])
            routing_descriptions.append(str(found["ROUTING_DESCRIPTION"]))
            routing_groups.append(found["ROUTING_GROUP"])
            group_counters.append(found["GROUP_COUNTER"])
        else:
            skip_flags.append(SAFE_TO_ADD)
            skip_reasons.append(SKIP_REASONS[SAFE_TO_ADD])
            routing_descriptions.append("")
            routing_groups.append("")
            group_counters.append("")

    df["group"] = routing_groups
    df["group counter"] = group_counters
    df["SKIP"] = skip_flags
    df["SKIP_REASON"] = skip_reasons
    df["ROUTING_DESCRIPTION"] = routing_descriptions
    return df


def summary(df):
    return (f"  Safe to add (0): {(df['SKIP'] == SAFE_TO_ADD).sum()}\n"
            f"  Routing exists (1): {(df['SKIP'] == ROUTING_EXISTS).sum()}\n"
            f"  Not at plant (2): {(df['SKIP'] == NOT_AT_PLANT).sum()}\n"
            f"  Inactive, untick deletion flag in SAP (3): {(df['SKIP'] == ROUTING_INACTIVE).sum()}")


def run(input_path, output_path=None, conn=None, plant=PLANT):
    """Read Excel, check, write back (in place by default)."""
    df = check_routing_exists(read_input(input_path), conn=conn, plant=plant)
    saved = write_output(df, output_path or input_path)
    print(f"Done. {len(df)} rows processed. Saved to: {saved}")
    print(summary(df))
    return df
