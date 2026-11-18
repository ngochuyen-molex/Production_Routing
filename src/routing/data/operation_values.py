"""Values of the routing operations used by the operation check.

Returns the 0020 operation, every YMHI work-center operation (sorting / lubricant) and
every PP94 operation (final step), with base quantity (PLPO.BMSCH), the standard values
(setup / machine / labor) and efficiency / utilization (PLPO.USR04 / USR05).
Rules and known gaps: docs/operation_values.md
"""
from routing.core.clean import to_sap_matnr
from routing.core.config import PLANT
from routing.core.db import query_in_batches

COLUMNS = ["MATNR", "ROUTING_GROUP", "GROUP_COUNTER", "ROUTING_DESCRIPTION", "OPERATION_NUMBER",
           "OPERATION_TEXT", "CONTROL_KEY", "RESOURCE_NAME", "BASE_QUANTITY", "BASE_QUANTITY_UNIT",
           "CONV_HEADER_QTY", "CONV_OPERATION_QTY",
           "SETUP_TIME", "SETUP_UNIT", "SETUP_ACTIVITY",
           "MACHINE_TIME", "MACHINE_UNIT", "MACHINE_ACTIVITY",
           "LABOR_TIME", "LABOR_UNIT", "LABOR_ACTIVITY",
           "EFFICIENCY", "UTILIZATION"]

SQL_OPERATION_VALUES = """
    SELECT DISTINCT
        mp.MATNR,
        pk.PLNNR AS ROUTING_GROUP,
        pk.PLNAL AS GROUP_COUNTER,
        pk.KTEXT AS ROUTING_DESCRIPTION,
        po.VORNR AS OPERATION_NUMBER,
        po.LTXA1 AS OPERATION_TEXT,
        po.STEUS AS CONTROL_KEY,
        cr.ARBPL AS RESOURCE_NAME,
        po.BMSCH AS BASE_QUANTITY,
        po.MEINH AS BASE_QUANTITY_UNIT,
        po.UMREZ AS CONV_HEADER_QTY,      -- e.g. 8 PC
        po.UMREN AS CONV_OPERATION_QTY,   -- e.g. 1 CYL
        po.VGW01 AS SETUP_TIME,
        po.VGE01 AS SETUP_UNIT,
        po.LAR01 AS SETUP_ACTIVITY,
        po.VGW02 AS MACHINE_TIME,
        po.VGE02 AS MACHINE_UNIT,
        po.LAR02 AS MACHINE_ACTIVITY,
        po.VGW03 AS LABOR_TIME,
        po.VGE03 AS LABOR_UNIT,
        po.LAR03 AS LABOR_ACTIVITY,
        po.USR04 AS EFFICIENCY,           -- Eff. in Routing (only filled at 0020)
        po.USR05 AS UTILIZATION           -- Utl. in Routing (only filled at 0020)
    FROM MLX_DATALAKE.MLX_SAP_ECC.MAPL mp
    JOIN MLX_DATALAKE.MLX_SAP_ECC.PLKO pk
        ON mp.MANDT = pk.MANDT AND mp.PLNTY = pk.PLNTY
        AND mp.PLNNR = pk.PLNNR AND mp.PLNAL = pk.PLNAL
    JOIN MLX_DATALAKE.MLX_SAP_ECC.PLAS ps
        ON pk.MANDT = ps.MANDT AND pk.PLNTY = ps.PLNTY
        AND pk.PLNNR = ps.PLNNR AND pk.PLNAL = ps.PLNAL
        AND ps.LOEKZ = ' '
    JOIN MLX_DATALAKE.MLX_SAP_ECC.PLPO po
        ON ps.MANDT = po.MANDT AND ps.PLNTY = po.PLNTY
        AND ps.PLNNR = po.PLNNR AND ps.PLNKN = po.PLNKN
    LEFT JOIN MLX_DATALAKE.MLX_SAP_ECC.CRHD cr
        ON po.ARBID = cr.OBJID AND po.MANDT = cr.MANDT
        AND cr.OBJTY = 'A' AND cr.DW_SOFT_DELETE_FLAG = 0
    JOIN MLX_DATALAKE.MLX_SAP_ECC.MARC marc
        ON mp.MATNR = marc.MATNR AND mp.WERKS = marc.WERKS
        AND marc.DW_SOFT_DELETE_FLAG = 0
        AND TRIM(marc.LVORM) = ''   -- material not flagged for deletion
        AND marc.MMSTA != 'E3'      -- material not discontinued
    WHERE pk.WERKS = %s
        AND pk.LOEKZ = ' '
        AND mp.PLNTY = 'N' -- show only visible routing in sap
        AND (po.VORNR = '0020'            -- production
             OR cr.ARBPL LIKE 'YMHI%%'    -- sorting / lubricant
             OR po.STEUS = 'PP94'         -- final step (pack & send to WH)
             OR po.STEUS = 'ZP04')        -- trial routing: only to explain a missing PP94
        AND pk.DW_SOFT_DELETE_FLAG = 0
        AND mp.DW_SOFT_DELETE_FLAG = 0
        AND ps.DW_SOFT_DELETE_FLAG = 0 -- deleted sequences (e.g. old A505110D at GC 00)
        AND po.DW_SOFT_DELETE_FLAG = 0 -- deleted operations
        AND pk.DELKZ != 'X'
        AND mp.MATNR IN ({placeholders})
"""


def operation_values(conn, materials, plant=PLANT):
    """Operations of the given materials with capacity, standard values and eff / util.
    Used by: checks/operation_values.py"""
    return query_in_batches(
        conn, SQL_OPERATION_VALUES, [to_sap_matnr(m) for m in materials],
        params_before=[plant], columns=COLUMNS)
