"""Material / plant queries (MARC)."""
from routing.core.clean import to_sap_matnr
from routing.core.config import PLANT
from routing.core.db import query_in_batches

SQL_MATERIAL_STATUS = """
    SELECT LTRIM(mc.MATNR, '0') AS MATERIAL, TRIM(mc.MMSTA) AS MATERIAL_STATUS
    FROM MLX_DATALAKE.MLX_SAP_ECC.MARC mc
    WHERE mc.WERKS = %s
        AND mc.DW_SOFT_DELETE_FLAG = 0
        AND mc.MATNR IN ({placeholders})
"""


def material_status(conn, materials, plant=PLANT):
    """Plant-specific material status (MARC.MMSTA, e.g. E3 = not active in this plant, S1 / S2).
    Columns: MATERIAL (no leading zeros), MATERIAL_STATUS ('' = none).
    Used by: steps/base.Context.material_status (planner of `routing run`)"""
    return query_in_batches(conn, SQL_MATERIAL_STATUS, [to_sap_matnr(m) for m in materials],
                            params_before=[plant], columns=["MATERIAL", "MATERIAL_STATUS"])
