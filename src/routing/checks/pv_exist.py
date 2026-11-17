"""Does a production version (MKAL) exist for each row's routing + alternative BOM?

Excel columns: Material, group, group counter, Alt Bom
  Alt Bom = 1, 2, ... -> check the version for that alt BOM on the row's routing
  Alt Bom = "ALL BOM" -> not checked for now; existing versions are listed (see docs/production_version.md)
Adds: PV_FOUND, PV_CHECK
"""
from routing.core.clean import clean_material_series
from routing.core.config import PLANT
from routing.core.db import snowflake_session
from routing.core.excel import read_input, write_output
from routing.model.entities import RoutingKey
from routing.model.requests import AltBomChoice, InputError
from routing.resolve import routings as routing_resolve

EXISTS = "Exists"
MISSING = "Missing"
ALL_BOM_NOT_CHECKED = "ALL BOM - not checked"
NO_ROUTING = "No routing (group / group counter blank)"
INVALID_ALT_BOM = "Invalid Alt Bom"


def _clean(series):
    return series.fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)


def alt_bom_choice(alt_bom):
    """AltBomChoice for 2 / '2' / 'B2' / '02' / 'ALL BOM'; None when blank or not readable."""
    if not str(alt_bom).strip():
        return None
    try:
        return AltBomChoice.parse(alt_bom)
    except InputError:
        return None


def _describe(versions):
    return ", ".join(v.describe() for v in versions)


def check_pv_exists(df, conn=None, plant=PLANT):
    df = df.copy()
    df["Material"] = clean_material_series(df["Material"])
    for col in ["group", "group counter", "Alt Bom"]:
        df[col] = _clean(df[col]) if col in df.columns else ""
    df["group counter"] = df["group counter"].str.lstrip("0")

    materials = df["Material"].unique().tolist()
    with snowflake_session(conn) as c:
        versions = routing_resolve.load_versions(c, materials, plant)

    found_col, check_col = [], []
    for _, row in df.iterrows():
        key = RoutingKey(row["Material"], row["group"], row["group counter"])
        choice = alt_bom_choice(row["Alt Bom"])

        if not row["group"] or not row["group counter"]:
            found, status = "", NO_ROUTING
        elif choice is not None and choice.all:
            # listed so partly existing ALL BOM routings can be spotted by hand
            found, status = _describe(versions[key.material].on(key)), ALL_BOM_NOT_CHECKED
        elif choice is None:
            found, status = "", INVALID_ALT_BOM
        else:
            match = [v for v in versions[key.material].on(key) if v.alt_bom == choice.number]
            found, status = _describe(match), EXISTS if match else MISSING

        found_col.append(found)
        check_col.append(status)

    df["PV_FOUND"] = found_col
    df["PV_CHECK"] = check_col
    return df


def summary(df):
    return (f"  Exists: {(df['PV_CHECK'] == EXISTS).sum()}\n"
            f"  Missing: {(df['PV_CHECK'] == MISSING).sum()}\n"
            f"  ALL BOM, not checked: {(df['PV_CHECK'] == ALL_BOM_NOT_CHECKED).sum()}\n"
            f"  No routing / invalid Alt Bom: {df['PV_CHECK'].isin([NO_ROUTING, INVALID_ALT_BOM]).sum()}")


def run(input_path, output_path=None, sheet_name="Sheet1", conn=None, plant=PLANT):
    df = check_pv_exists(read_input(input_path, sheet_name=sheet_name), conn=conn, plant=plant)
    saved = write_output(df, output_path or input_path)
    print(f"Done. {len(df)} rows processed. Saved to: {saved}")
    print(summary(df))
    return df
