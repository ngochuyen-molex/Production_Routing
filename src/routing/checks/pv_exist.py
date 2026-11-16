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
from routing.data import production_version as pv_data

ALL_BOM = "ALL BOM"

EXISTS = "Exists"
MISSING = "Missing"
ALL_BOM_NOT_CHECKED = "ALL BOM - not checked"
NO_ROUTING = "No routing (group / group counter blank)"
INVALID_ALT_BOM = "Invalid Alt Bom"


def _clean(series):
    return series.fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)


def alt_bom_number(alt_bom):
    """'2' for 2 / '2' / 'B2' / '02', None otherwise (incl. ALL BOM)."""
    value = str(alt_bom).strip().upper().removeprefix("B").lstrip("0")
    return value if value.isdigit() else None


def _describe(versions):
    return ", ".join(f"{r.PRODUCTION_VERSION} (B{r.ALT_BOM}{', locked' if r.LOCKED else ''})"
                     for r in versions.sort_values("PRODUCTION_VERSION").itertuples())


def check_pv_exists(df, conn=None, plant=PLANT):
    df = df.copy()
    df["Material"] = clean_material_series(df["Material"])
    for col in ["group", "group counter", "Alt Bom"]:
        df[col] = _clean(df[col]) if col in df.columns else ""
    df["group counter"] = df["group counter"].str.lstrip("0")

    with snowflake_session(conn) as c:
        pv_df = pv_data.by_routing(c, df["Material"].unique().tolist(), plant)
    for col in ["MATERIAL", "ROUTING_GROUP", "GROUP_COUNTER", "ALT_BOM"]:
        pv_df[col] = pv_df[col].fillna("").astype(str).str.strip()
    pv_df["LOCKED"] = pv_df["LOCK_STATUS"].fillna("").astype(str).str.strip() != ""

    found_col, check_col = [], []
    for _, row in df.iterrows():
        on_routing = pv_df[(pv_df["MATERIAL"] == row["Material"]) & (pv_df["ROUTING_GROUP"] == row["group"])
                           & (pv_df["GROUP_COUNTER"] == row["group counter"])]
        alt_bom = alt_bom_number(row["Alt Bom"])

        if not row["group"] or not row["group counter"]:
            found, status = "", NO_ROUTING
        elif row["Alt Bom"].upper() == ALL_BOM:
            # listed so partly existing ALL BOM routings can be spotted by hand
            found, status = _describe(on_routing), ALL_BOM_NOT_CHECKED
        elif alt_bom is None:
            found, status = "", INVALID_ALT_BOM
        else:
            match = on_routing[on_routing["ALT_BOM"] == alt_bom]
            found, status = _describe(match), EXISTS if len(match) else MISSING

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
