"""BOM queries (MAST / STKO)."""
from routing.core.clean import to_sap_matnr
from routing.core.config import PLANT
from routing.core.db import query_in_batches

# Active alternative BOM = usage 1, status 01 (shared by both queries)
SQL_ACTIVE_ALT_BOMS = """
    FROM MLX_DATALAKE.MLX_SAP_ECC.MAST m
    JOIN MLX_DATALAKE.MLX_SAP_ECC.STKO s
        ON m.STLNR = s.STLNR AND m.STLAL = s.STLAL
    WHERE m.STLAN = '1' AND m.WERKS = %s AND s.STLST = '01'
        AND m.MATNR IN ({placeholders})
"""

SQL_ALT_BOM_COUNT = "SELECT m.MATNR, COUNT(DISTINCT m.STLAL) AS ALT_BOM_COUNT" + SQL_ACTIVE_ALT_BOMS + \
    "    GROUP BY m.MATNR\n"

SQL_ALT_BOM_NUMBERS = "SELECT DISTINCT m.MATNR, LTRIM(m.STLAL, '0') AS ALT_BOM" + SQL_ACTIVE_ALT_BOMS


def alt_bom_count(conn, materials, plant=PLANT):
    """Active alternative BOMs (usage 1, status 01) per material. Columns: MATNR, ALT_BOM_COUNT."""
    return query_in_batches(conn, SQL_ALT_BOM_COUNT, [to_sap_matnr(m) for m in materials],
                            params_before=[plant], columns=["MATNR", "ALT_BOM_COUNT"])


def alt_bom_numbers(conn, materials, plant=PLANT):
    """The active alternative BOM numbers themselves (1 and 3 when 2 is gone). Columns: MATNR, ALT_BOM.
    Used by: resolve/routings.py (production versions for ALL BOM)"""
    return query_in_batches(conn, SQL_ALT_BOM_NUMBERS, [to_sap_matnr(m) for m in materials],
                            params_before=[plant], columns=["MATNR", "ALT_BOM"])
