"""Check logic with a fake connection: no Snowflake needed."""
import pandas as pd

from routing.checks import alt_bom, operation_values, routing_condition
from routing.pipelines import pre_uipath


class FakeCursor:
    def __init__(self, responses):
        self.responses = responses
        self.description = None
        self._rows = []
        self.executed = []

    def execute(self, sql, params):
        self.executed.append((sql, params))
        for key, (columns, rows) in self.responses.items():
            if key in sql:
                self.description = [(c,) for c in columns]
                self._rows = rows
                return
        raise AssertionError(f"unexpected SQL: {sql[:80]}")

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, responses):
        self.cur = FakeCursor(responses)

    def cursor(self):
        return self.cur


MAT = "000000000000012345"
RESPONSES = {
    "SELECT DISTINCT mp.MATNR\n": (["MATNR"], [(MAT,)]),
    "pk.KTEXT AS ROUTING_DESCRIPTION": (
        ["MATNR", "RESOURCE", "ROUTING_DESCRIPTION", "ROUTING_GROUP", "GROUP_COUNTER", "DELETION_FLAG"],
        [(MAT, "MD01", "MD01 T555 production", "M0001", "02", " ")]),
    "ALT_BOM_COUNT": (["MATNR", "ALT_BOM_COUNT"], [(MAT, 2)]),
}


def input_df():
    return pd.DataFrame({
        "Material": [12345.0, 12345.0, 12345.0, 99999.0],
        "Resource": ["MD01", "MD01", "MD02", "MD01"],
        "Tool": ["T555", "T777", "", ""],
    })


def test_routing_condition_flags():
    out = routing_condition.check_routing_exists(input_df(), conn=FakeConn(RESPONSES))
    assert out["SKIP"].tolist() == [1, 0, 0, 2]
    assert out.loc[0, "group"] == "M0001"
    assert out.loc[0, "group counter"] == "2"
    assert out["SKIP_REASON"].tolist()[-1] == "Material not at plant"


def test_routing_condition_flags_deleted_routing_for_reactivation():
    # like 522690630: GC 15 (L52269#5) has the deletion flag, GC 14 (L52269#5) is active
    rows = [(MAT, "MF50-11", "MF50-11 - 12345 - L52269#5", "M0001", "15", "X"),
            (MAT, "MF50-10", "MF50-10 - 12345 - L52269#5", "M0001", "14", " "),
            (MAT, "MF50-10", "MF50-10 - 12345 - L52269#5", "M0001", "13", "X")]
    responses = {**RESPONSES, "pk.KTEXT AS ROUTING_DESCRIPTION": (
        RESPONSES["pk.KTEXT AS ROUTING_DESCRIPTION"][0], rows)}
    df = pd.DataFrame({"Material": [12345, 12345], "Resource": ["MF50-11", "MF50-10"],
                       "Tool": ["L52269#5", "L52269#5"]})
    out = routing_condition.check_routing_exists(df, conn=FakeConn(responses))
    assert out["SKIP"].tolist() == [3, 1]
    assert out["SKIP_REASON"].tolist() == ["Inactive", "Routing already exists"]
    assert out["group counter"].tolist() == ["15", "14"]   # active GC 14 wins over flagged GC 13


def test_queries_use_bound_params():
    conn = FakeConn(RESPONSES)
    routing_condition.check_routing_exists(input_df(), conn=conn)
    for sql, params in conn.cur.executed:
        assert MAT not in sql          # material is a parameter, not pasted into SQL
        assert "1901" in params


def test_alt_bom_count_fills_zero():
    df = pd.DataFrame({"Material": ["12345", "99999"]})
    out = alt_bom.check_alt_bom_count(df, conn=FakeConn(RESPONSES))
    assert out["ALT_BOM_COUNT"].tolist() == [2, 0]


def test_pre_uipath_adds_both_results():
    out = pre_uipath.pre_uipath_checks(input_df(), conn=FakeConn(RESPONSES))
    assert {"SKIP", "SKIP_REASON", "ALT_BOM_COUNT"} <= set(out.columns)
    assert out["ALT_BOM_COUNT"].tolist() == [2, 2, 2, 0]


OP_COLUMNS = ["MATNR", "ROUTING_GROUP", "GROUP_COUNTER", "ROUTING_DESCRIPTION", "OPERATION_NUMBER",
              "OPERATION_TEXT", "CONTROL_KEY", "RESOURCE_NAME", "BASE_QUANTITY", "BASE_QUANTITY_UNIT",
              "CONV_HEADER_QTY", "CONV_OPERATION_QTY",
              "SETUP_TIME", "SETUP_UNIT", "SETUP_ACTIVITY",
              "MACHINE_TIME", "MACHINE_UNIT", "MACHINE_ACTIVITY",
              "LABOR_TIME", "LABOR_UNIT", "LABOR_ACTIVITY",
              "EFFICIENCY", "UTILIZATION"]
NORMAL, LUBE, BAD = "000000005052771989", "000000005052760989", "000000005016441810"


def op(matnr, group, counter, description, operation, control_key, resource, quantity, unit,
       setup=1.0, machine=1.0, labor=1.0, time_unit="H", efficiency=0.0, utilization=0.0,
       header_qty=8, operation_qty=1):
    """One routing operation row in OP_COLUMNS order."""
    return (matnr, group, counter, description, operation, description, control_key, resource,
            quantity, unit, header_qty, operation_qty,
            setup, time_unit, "", machine, time_unit, "MLMC", labor, time_unit, "LABMLD",
            efficiency, utilization)


OP_RESPONSES = {"AS CONTROL_KEY": (OP_COLUMNS, [
    # normal routing: production 0020, final PP94 at 0030
    op(NORMAL, "M5052771", "09", "MN15-09 NEX150", "0020", "PP01", "MN15-09", 1000.0, "CYL",
       efficiency=0.975, utilization=0.85),
    op(NORMAL, "M5052771", "09", "MN15-09 NEX150", "0030", "PP94", "OMINS", 8000.0, "PC"),
    # lubricant routing: YMHI sorting at 0030 pushes final PP94 to 0040
    op(LUBE, "M5052760", "13", "MN15-14NEX150-1EC", "0020", "PP01", "MN15-14", 923.0, "CYL",
       efficiency=0.99, utilization=0.88),
    op(LUBE, "M5052760", "13", "MN15-14NEX150-1EC", "0030", "PP96", "YMHI-1", 100000.0, "PC"),
    op(LUBE, "M5052760", "13", "MN15-14NEX150-1EC", "0040", "PP94", "OMINS", 7384.0, "PC"),
    # setup 0.000 with a blank unit, as seen on PM5-A plating; header qty 12 against cavity 12
    op(BAD, "M0164418", "15", "IOM-8 MOLDING", "0020", "PP01", "IOM-8", 450.0, "CYL",
       setup=0.0, time_unit="", efficiency=1.01, utilization=0.82, header_qty=12),
])}


def capacity_df():
    return pd.DataFrame({
        "Material": ["5052771989", "5052760989", "5052760989"],
        "Resource": ["MN15-09", "MN15-14", "MN15-14"],
        "Capacity": [1000, 923, 923],
        "Tool Cavity": [8, 8, 8],
        "Sorting Capacity": [None, 100000, 90000],
        "group counter": [None, None, None],
    })


def test_operation_values_finds_final_step_after_sorting():
    out = operation_values.check_routing_values(capacity_df(), conn=FakeConn(OP_RESPONSES))
    assert out["FINAL_OPERATION"].tolist() == ["0030", "0040", "0040"]
    assert out["CHECK_0020"].tolist() == ["Match"] * 3
    assert out["CHECK_FINAL"].tolist() == ["Match"] * 3
    assert out["CHECK_SORTING"].tolist() == ["", "Match", "Mismatch"]
    assert out["SORTING_OPERATION"].tolist() == ["", "0030", "0030"]


def test_final_step_is_pp94_only_zp04_is_trial():
    trial, no_final = "000000005000000001", "000000005000000002"
    responses = {"AS CONTROL_KEY": (OP_COLUMNS, OP_RESPONSES["AS CONTROL_KEY"][1] + [
        op(trial, "P0541470", "02", "TRIAL PM2-A", "0020", "PP01", "PM2-A", 500.0, "PC"),
        op(trial, "P0541470", "02", "TRIAL PM2-A", "0040", "ZP04", "OPMINS", 4000.0, "PC"),
        op(no_final, "M6750000", "01", "MD-Regrinding", "0020", "PP01", "MN15-09", 500.0, "PC"),
    ])}
    df = pd.DataFrame({"Material": ["5052771989", "5000000001", "5000000002", "99999"],
                       "Resource": ["MN15-09", "PM2-A", "MN15-09", "MN15-09"],
                       "Capacity": [1000, 500, 500, 1000], "Tool Cavity": [8, 8, 8, 8]})
    out = operation_values.check_routing_values(df, conn=FakeConn(responses))
    assert out["CHECK_FINAL"].tolist() == ["Match", "No final step PP94 (ZP04 = trial routing)",
                                           "No final step PP94", "No routing found"]
    assert out["FINAL_OPERATION"].tolist()[1] == ""     # ZP04 is never taken as the final step
    assert "Routing without final step PP94: 2" in operation_values.summary(out)


def test_standard_values_must_be_one_hour_at_0020():
    df = pd.DataFrame({
        "Material": ["5052771989", "5016441810", "99999"],
        "Resource": ["MN15-09", "IOM-8", "MN15-09"],
        "Capacity": [1000, 450, 1000],
        "Tool Cavity": [8, 8, 8],
    })
    out = operation_values.check_routing_values(df, conn=FakeConn(OP_RESPONSES))
    assert out["STD_VALUE_CHECK"].tolist() == [
        "Match",                                            # 1.000 H on all three
        "Setup 0.000; Machine unit blank; Labor unit blank",  # setup 0 and no unit
        "No routing found",
    ]
    assert out["SETUP_0020"].tolist()[:2] == [1.0, 0.0]


def test_efficiency_and_utilization_compared_at_0020():
    df = pd.DataFrame({
        "Material": ["5052771989", "5052760989", "5052771989"],
        "Resource": ["MN15-09", "MN15-14", "MN15-09"],
        "Capacity": [1000, 923, 1000],
        "Tool Cavity": [8, 8, 8],
        "Efficiency": [0.975, 0.80, None],
        "Utilization": [0.85, 0.88, None],
    })
    out = operation_values.check_routing_values(df, conn=FakeConn(OP_RESPONSES))
    assert out["RTG_EFFICIENCY"].tolist() == [0.975, 0.99, 0.975]
    assert out["EFF_CHECK"].tolist() == ["Match", "Mismatch", "No Excel efficiency"]
    assert out["UTIL_CHECK"].tolist() == ["Match", "Match", "No Excel utilization"]


def test_header_value_must_equal_tool_cavity_at_0020():
    df = pd.DataFrame({
        "Material": ["5052771989", "5016441810", "5052771989", "99999"],
        "Resource": ["MN15-09", "IOM-8", "MN15-09", "MN15-09"],
        "Capacity": [1000, 450, 1000, 1000],
        "Tool Cavity": [8, 12, 16, 8],   # row 3 disagrees with the routing's header qty of 8
    })
    out = operation_values.check_routing_values(df, conn=FakeConn(OP_RESPONSES))
    assert out["HEADER_QTY_0020"].tolist()[:3] == [8.0, 12.0, 8.0]
    assert out["CHECK_HEADER"].tolist() == [
        "Match",
        "Match",                        # header 12 = cavity 12, setup problem is reported separately
        "Header 8, Tool Cavity 16",
        "No routing found",
    ]


def test_operation_qty_is_reported_but_never_judged():
    """UMREN is 1 everywhere at plant 1901, so it is output for reference only."""
    df = pd.DataFrame({
        "Material": ["5052771989", "5052760989"],
        "Resource": ["MN15-09", "MN15-14"],
        "Capacity": [1000, 923],
        "Tool Cavity": [8, 8],
    })
    responses = {"AS CONTROL_KEY": (OP_COLUMNS, [
        op(NORMAL, "M5052771", "09", "MN15-09 NEX150", "0020", "PP01", "MN15-09", 1000.0, "CYL",
           header_qty=8, operation_qty=1),
        op(LUBE, "M5052760", "13", "MN15-14NEX150-1EC", "0020", "PP01", "MN15-14", 923.0, "CYL",
           header_qty=8, operation_qty=4),   # unusual value: reported, still a Match
    ])}
    out = operation_values.check_routing_values(df, conn=FakeConn(responses))
    assert out["OPERATION_QTY_0020"].tolist() == [1.0, 4.0]
    assert out["CHECK_HEADER"].tolist() == ["Match", "Match"]


def test_header_check_reports_missing_tool_cavity():
    df = pd.DataFrame({
        "Material": ["5052771989"],
        "Resource": ["MN15-09"],
        "Capacity": [1000],
    })
    out = operation_values.check_routing_values(df, conn=FakeConn(OP_RESPONSES))
    assert out["CHECK_HEADER"].tolist() == ["No Excel tool cavity"]


def test_operation_values_query_uses_bound_params():
    conn = FakeConn(OP_RESPONSES)
    operation_values.check_routing_values(capacity_df(), conn=conn)
    for sql, params in conn.cur.executed:
        assert NORMAL not in sql       # material is a parameter, not pasted into SQL
        assert "1901" in params


def test_missing_group_counter_column_is_tolerated():
    df = pd.DataFrame({
        "Material": ["5052771989"],
        "Resource": ["MN15-09"],
        "Capacity": [1000],
        "Tool Cavity": [8],
    })
    out = operation_values.check_routing_values(df, conn=FakeConn(OP_RESPONSES))
    assert out["MATCH_METHOD"].tolist() == ["Resource"]



PV_COLUMNS = ["MATERIAL", "ROUTING_GROUP", "GROUP_COUNTER", "ALT_BOM", "PRODUCTION_VERSION",
              "DESCRIPTION", "LOCK_STATUS"]
# like 5013300800: M5013300 / 25 has B1 + B2, M5013300 / 34 only B1
PV_RESPONSES = {"AS lock_status": (PV_COLUMNS, [
    ("5013300800", "M5013300", "25", "1", "0001", "MF50-03 - L501330A B1", " "),
    ("5013300800", "M5013300", "25", "2", "0005", "MF50-03 - L501330A B2", " "),
    ("5013300800", "M5013300", "34", "1", "0004", "MF50-09 - L501330A B1", " "),
])}


def test_pv_exist_checks_the_requested_alt_bom_only():
    from routing.checks import pv_exist
    df = pd.DataFrame({
        "Material": ["5013300800"] * 5,
        "group": ["M5013300", "M5013300", "M5013300", "", "M5013300"],
        "group counter": [34.0, 34.0, 25.0, None, 34.0],
        "Alt Bom": [2, 1, "ALL BOM", 1, "x"],
    })
    out = pv_exist.check_pv_exists(df, conn=FakeConn(PV_RESPONSES))
    assert out["PV_CHECK"].tolist() == [pv_exist.MISSING, pv_exist.EXISTS, pv_exist.ALL_BOM_NOT_CHECKED,
                                        pv_exist.NO_ROUTING, pv_exist.INVALID_ALT_BOM]
    assert out.loc[1, "PV_FOUND"] == "0004 (B1)"
    assert out.loc[2, "PV_FOUND"] == "0001 (B1), 0005 (B2)"   # ALL BOM: existing versions listed
