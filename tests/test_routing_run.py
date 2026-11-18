"""Routing automation (routing run): no SAP and no Snowflake needed."""
import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

from routing.layouts import select as layouts
from routing.model.entities import (MaterialRoutings, MaterialVersions, Operation, ProductionVersion,
                                    Routing, RoutingKey)
from routing.model.enums import Action, Dept, OperationRole, Status
from routing.model.requests import AltBomChoice, InputError, request_from_row
from routing.model.result import StepResult
from routing.pipelines import recipes, run as runner
from routing.resolve import routings as resolve
from routing.steps.base import Context, Step
from routing.steps.routing import InactivateRouting

MAT = "5052760989"


def create_row(**extra):
    row = {"Action": "Create", "Dept": "MD", "Material": MAT, "Resource": "MN15-20", "Tool": "L505276B",
           "Capacity": 900, "Tool Cavity": 8, "Efficiency": 0.98, "Utilization": 0.9, "Alt Bom": 1}
    row.update(extra)
    return row


def routing(counter, description, ops, status="4", deleted=False, group="M0527609"):
    return Routing(RoutingKey(MAT, group, counter), description, status, deleted,
                   tuple(Operation(n, k, wc) for n, k, wc in ops))


MOLD_LUBE = [("0005", "PP07", "TMC"), ("0010", "PPQM", "XQA"), ("0020", "PP01", "MN15-14"),
             ("0030", "PP96", "YMHI-1"), ("0040", "PP94", "OMINS")]
MOLD = [("0005", "PP07", "TMC"), ("0010", "PPQM", "XQA"), ("0020", "PP01", "MF15-17"),
        ("0030", "PP94", "OMINS")]


# ---------------------------------------------------------------- requests
def test_request_parsing():
    request = request_from_row(2, create_row(**{"Alt Bom": "ALL BOM"}))
    assert request.action is Action.CREATE and request.dept is Dept.MD
    assert request.params.alt_bom == AltBomChoice(all=True)
    assert request.params.capacity_x_cavity == 7200
    with pytest.raises(InputError, match="Capacity missing"):
        request_from_row(2, create_row(Capacity=None))
    with pytest.raises(InputError, match="Action"):
        request_from_row(2, create_row(Action="Copy"))
    with pytest.raises(InputError, match="Sorting/ Lubricant Capacity"):
        request_from_row(2, create_row(**{"Sorting/ Lubricant": "YMHI-1"}))


# ---------------------------------------------------------------- layouts
def test_md_with_sorting_uses_md_sorting_layout():
    request = request_from_row(2, create_row(**{"Sorting/ Lubricant": "YMHI-1",
                                                 "Sorting/ Lubricant Capacity": 100000}))
    layout = layouts.layout_for(request)
    assert layout.id == "MD_SORTING"
    assert layouts.description(layout, request) == "MN15-20 - L505276B - YMHI-1"
    values = {v.role: v for v in layouts.operation_values(layout, request)}
    assert values[OperationRole.PRODUCTION].work_center == "MN15-20"
    assert dict(values[OperationRole.PRODUCTION].details)["setup"] == 1
    assert values[OperationRole.SORTING].base_quantity == 100000
    assert (values[OperationRole.FINAL].row, values[OperationRole.FINAL].base_quantity) == (5, 7200)


def test_layout_reports_missing_inputs_and_long_description():
    request = request_from_row(2, create_row(Tool="", **{"Tool Cavity": None}))
    assert layouts.missing_inputs(layouts.layout_for(request), request) == ["Tool", "Tool Cavity"]
    long = request_from_row(2, create_row(Resource="X" * 30))
    with pytest.raises(ValueError, match="longer than 40"):
        layouts.description(layouts.layout_for(long), long)


def test_copy_source_check_and_ranking():
    md = layouts.LAYOUTS["MD"]
    lube, plain = routing("13", "MN15-14-5052760989-L505276B-YMHI-1", MOLD_LUBE), routing("15", "5052760989 - MF15-17", MOLD)
    assert layouts.check_copy_source(md, plain) == []
    assert "YMHI" in layouts.check_copy_source(md, lube)[0]
    routings = MaterialRoutings(MAT, (lube, plain, routing("16", "MDTRIAL x", MOLD), routing("17", "old", MOLD, deleted=True)))
    best = routings.copy_source(fits=lambda r: not layouts.check_copy_source(md, r), resource="MN15-20")
    assert best.key.counter == "15"        # fits the layout; newer TRIAL / flagged routings are never copied
    assert routings.copy_source(fits=lambda r: True, needs_sorting=True).key.counter == "13"


def test_matching_uses_routing_condition_rule():
    # resource = work center of an operation, tool in the description; a trial routing only counts
    # for a trial resource (routing automation); routing_condition (trial_rule=False) still counts it
    flagged = routing("14", "MN15-14 - L505276B", MOLD_LUBE, deleted=True)
    active = routing("13", "MN15-14-5052760989-L505276B-YMHI-1", MOLD_LUBE)
    trial = routing("12", "MN15-14 L505276B TRIAL", MOLD_LUBE)
    only_text = routing("18", "MN15-14 - L505276B", MOLD)            # MN15-14 only in the text, not a work center
    routings = MaterialRoutings(MAT, (flagged, trial, active, only_text))
    assert [r.key.counter for r in routings.matching("MN15-14", "L505276B")] == ["13", "14"]
    assert [r.key.counter for r in routings.matching("MN15-14", "L505276B", trial_rule=False)] == ["13", "12", "14"]
    assert routings.matching("MN15-14", "L505276X") == []


MDTRIAL_OPS = [("0005", "PP07", "TMC"), ("0010", "PPQM", "XQA"), ("0020", "PP01", "MDTRIAL"),
               ("0030", "PP94", "OMINS")]


def test_trial_resource_only_finds_and_copies_trial_routings():
    normal = routing("15", "MF15-17 - 5052760989 - L505276A", MOLD)
    trial = routing("20", "MDTRIAL-MF15-17 - 5052760989 - L505276A", MDTRIAL_OPS)
    ctx = FakeContext({MAT: [normal, trial]})
    assert trial.is_trial and not normal.is_trial

    # Add with a normal resource: copies the normal routing, never the trial one
    assert plan_steps(create_row(Resource="MF15-20", Tool="L505276A"), ctx).plan.copy_from.key.counter == "15"
    # Add with MDTRIAL: the trial routing already exists for this tool -> skipped as existing
    exists = plan_steps(create_row(Resource="MDTRIAL", Tool="L505276A"), ctx)
    assert exists.plan.skip["CreateRouting"] == "routing already exists M0527609/20"
    # Add with MDTRIAL and another tool: copies the trial routing, not the normal one
    new_trial = plan_steps(create_row(Resource="MDTRIAL", Tool="L505276Z"), ctx)
    assert new_trial.plan.copy_from.key.counter == "20"
    # COPY_FROM a normal routing for a trial resource (and the reverse) is refused
    wrong = plan_steps(create_row(Resource="MDTRIAL", Tool="L505276Z", COPY_FROM_GROUP="M0527609", COPY_FROM_GC="15"), ctx)
    assert wrong.plan.skip["CreateRouting"] == "COPY_FROM M0527609/15 must be a trial routing, status 4, not flagged"
    # no trial routing of the material at all -> skipped, never falls back to a normal one
    none = plan_steps(create_row(Resource="MDTRIAL", Tool="L505276Z"), FakeContext({MAT: [normal]}))
    assert none.plan.skip["CreateRouting"].startswith("no trial routing of this material to copy from")


def test_delete_never_picks_a_trial_routing_for_a_normal_resource():
    normal = routing("15", "MF15-17 - L505276A", MOLD)
    trial = routing("20", "MF15-17 - L505276A TRIAL", MOLD)          # same machine, TRIAL in the name
    ctx = FakeContext({MAT: [normal, trial]})
    delete = {"Action": "Delete", "Dept": "MD", "Material": MAT, "Resource": "MF15-17", "Tool": "L505276A"}
    assert str(plan_steps(delete, ctx).key) == "M0527609/15"         # not ambiguous: trial not counted
    only_trial = plan_steps(delete, FakeContext({MAT: [trial]}))
    assert only_trial.plan.skip["InactivateRouting"] == "routing not found"
    by_key = plan_steps(dict(delete, group="M0527609", **{"group counter": "20"}), ctx)
    assert str(by_key.key) == "M0527609/20"                          # group + counter given: exactly that one


def test_operation_roles_and_versions():
    lube = routing("13", "x", MOLD_LUBE)
    assert lube.operation(OperationRole.PRODUCTION).work_center == "MN15-14"
    assert lube.operation(OperationRole.SORTING).work_center == "YMHI-1"
    assert lube.operation(OperationRole.FINAL).number == "0040"
    key = RoutingKey("5013300800", "M5013300", "25")
    versions = MaterialVersions("5013300800", (
        ProductionVersion("5013300800", "0001", key, 1), ProductionVersion("5013300800", "0005", key, 2),
        ProductionVersion("5013300800", "5001", key, 3)))
    assert versions.has(key, 2) and versions.missing(key, [1, 2, 3, 4]) == [4]
    assert versions.next_number() == "0006"                           # versions >= 5000 not counted
    assert ProductionVersion.text_for(Routing(key, "MF50-03 - L501330A"), 2) == "MF50-03 - L501330A B2"


def test_routings_from_operations_groups_operations():
    df = pd.DataFrame([
        ("000000005052760989", "M0527609", "13", "desc", "4", " ", "0020", "PP01", "MN15-14", 923.0),
        ("000000005052760989", "M0527609", "13", "desc", "4", " ", "0040", "PP94", "OMINS", 7384.0)],
        columns=["MATNR", "ROUTING_GROUP", "GROUP_COUNTER", "ROUTING_DESCRIPTION", "ROUTING_STATUS",
                 "DELETION_FLAG", "OPERATION_NUMBER", "CONTROL_KEY", "WORK_CENTER", "BASE_QUANTITY"])
    (only,) = resolve.routings_from_operations(df)[MAT].routings
    assert only.key == RoutingKey(MAT, "M0527609", "13") and only.work_centers() == ["MN15-14", "OMINS"]


# ---------------------------------------------------------------- run (plan + execute)
class FakeContext(Context):
    """Routings / versions / alt BOMs given up front; SAP is a fake object or absent."""

    def __init__(self, routings_by_material, sap=None, dry_run=False, versions=None, alt_boms=None, statuses=None):
        super().__init__(dry_run=dry_run, sf=object(), sap=sap)
        self._routings = {m: MaterialRoutings(m, tuple(r)) for m, r in routings_by_material.items()}
        self._fake_versions = versions or {}
        self._fake_alt_boms = alt_boms or {}
        self._fake_statuses = statuses or {}

    def load_routings(self, materials):
        for m in materials:
            self._routings.setdefault(m, MaterialRoutings(m))

    def load_material_status(self, materials):
        for m in materials:
            self._status.setdefault(m, self._fake_statuses.get(m, ""))

    def versions(self, material):
        return MaterialVersions(material, tuple(self._fake_versions.get(material, ())))

    def alt_boms(self, material):
        return self._fake_alt_boms.get(material, [1])


def write_book(path, rows):
    book = Workbook()
    sheet = book.active
    columns = list(dict.fromkeys(c for r in rows for c in r))
    sheet.append(columns)
    for r in rows:
        sheet.append([r.get(c) for c in columns])
    book.save(path)


def test_dry_run_writes_plan_and_copy_source(tmp_path):
    path = tmp_path / "requests.xlsx"
    write_book(path, [
        create_row(),                                                       # new routing
        create_row(Resource="MN15-14"),                                     # exists already
        {"Action": "Delete", "Dept": "MD", "Material": MAT, "Resource": "MF15-17", "Tool": "L505276A"},
        create_row(Action="Copy"),                                          # invalid
    ])
    ctx = FakeContext({MAT: [routing("13", "MN15-14-5052760989-L505276B-YMHI-1", MOLD_LUBE),
                             routing("15", "5052760989 - MF15-17 - L505276A", MOLD)]}, dry_run=True)
    summary = runner.run(path, dry_run=True, ctx=ctx)
    assert (summary.planned, summary.invalid, summary.counts) == (3, 1, {})

    book = load_workbook(path)
    plan = list(book["Plan"].iter_rows(min_row=2, values_only=True))
    by_row = {r[0]: r for r in plan}
    assert by_row[4][1] == "Delete" and plan[0][0] == 4                     # deletes planned first
    assert by_row[2][7] == "MD" and by_row[2][8].startswith("M0527609/15")  # copy source = compatible routing
    assert "already exists M0527609/13" in by_row[3][10]
    assert "input: Action" in by_row[5][12]
    sheet = book[book.sheetnames[0]]
    header = [c.value for c in sheet[1]]
    assert sheet.cell(2, header.index("COPY_FROM_PLANNED") + 1).value.startswith("M0527609/15")
    assert "COPY_FROM_GC" not in header                                    # only the user fills the override


class RecordingStep(Step):
    def __init__(self, name, phase, outcome):
        self.name, self.phase, self.outcome, self.calls = name, phase, outcome, 0

    def run(self, row, ctx):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_execute_resumes_and_blocks_after_failure(tmp_path):
    path = tmp_path / "requests.xlsx"
    write_book(path, [create_row(), create_row(Resource="MN15-30", progress="done ca01")])
    first = RecordingStep("First", "routing", RuntimeError("SAP popup"))
    second = RecordingStep("Second", "pv", StepResult.done("ok"))
    book_recipes = {Action.CREATE: [first, second]}

    runner.run(path, ctx=FakeContext({}), recipes=book_recipes)
    assert (first.calls, second.calls) == (2, 0)                    # failed routing -> pv not run
    sheet = load_workbook(path).active
    header = [c.value for c in sheet[1]]
    assert sheet.cell(2, header.index("RESULT_FIRST") + 1).value == "Failed: SAP popup"

    first.outcome = StepResult.done("created")
    runner.run(path, ctx=FakeContext({}), recipes=book_recipes)    # rerun retries the failed step
    assert (first.calls, second.calls) == (4, 2)
    runner.run(path, ctx=FakeContext({}), recipes=book_recipes)    # everything done -> nothing runs
    assert (first.calls, second.calls) == (4, 2)
    assert list(load_workbook(path)["Run log"].iter_rows(min_row=2, max_row=2, values_only=True))[0][3] == "First"


def test_old_uipath_progress_is_ignored_and_results_use_short_columns(tmp_path):
    path = tmp_path / "requests.xlsx"
    write_book(path, [create_row(progress="done mm02")])            # UiPath value: not read
    routing_step = RecordingStep("CreateRouting", "routing", StepResult.done("M0527609/20"))
    comp_step = RecordingStep("AllocateComponents", "components", StepResult.done("B1 0020: 3"))
    pv_step = RecordingStep("CreateProductionVersion", "pv", StepResult.skipped("versions exist"))
    runner.run(path, ctx=FakeContext({}), recipes={Action.CREATE: [routing_step, comp_step, pv_step]})
    assert (routing_step.calls, comp_step.calls, pv_step.calls) == (1, 1, 1)
    sheet = load_workbook(path).active
    header = [c.value for c in sheet[1]]
    assert [sheet.cell(2, header.index(c) + 1).value for c in ("RESULT_ROUTING", "RESULT_COMPALLOC", "RESULT_MM02")] \
        == ["Done: M0527609/20", "Done: B1 0020: 3", "Skipped: versions exist"]
    runner.run(path, ctx=FakeContext({}), recipes={Action.CREATE: [routing_step, comp_step, pv_step]})
    assert (routing_step.calls, comp_step.calls, pv_step.calls) == (1, 1, 1)        # rerun: nothing repeated


# ---------------------------------------------------------------- SAP screens with a fake session
class FakeElement:
    def __init__(self, sap, element_id, text=""):
        self.sap, self.id, self.text, self.selected = sap, element_id, text, False

    def press(self):
        self.sap.actions.append(("press", self.id))

    def setFocus(self):
        self.sap.focus = self.id

    def sendVKey(self, key):
        self.sap.actions.append(("vkey", key, self.sap.focus))


class FakeSap:
    """findById on a dict of elements; enough to drive a step through known screens."""

    def __init__(self, texts):
        self.actions, self.focus = [], None
        self.elements = {k: FakeElement(self, k, v) for k, v in texts.items()}

    def findById(self, element_id, raise_error=True):
        return self.elements.get(element_id)


def test_inactivate_routing_opens_by_counter_and_sets_flag():
    from routing.sap import elements as el
    from routing.sap.session import SapSession

    list_table = el.HEADER_LIST_TABLE
    fake = FakeSap({"wnd[0]": "", el.OKCODE: "", el.STATUS_BAR: "", el.INIT_MATERIAL: "", el.INIT_PLANT: "",
                    list_table: "", f"{list_table}/txt[0,0]": "12", f"{list_table}/txt[1,0]": "a",
                    f"{list_table}/txt[0,1]": "13", f"{list_table}/txt[1,1]": "b",
                    el.BTN_HEADER: "", el.HEADER_DELETION_FLAG: "", el.HEADER_STATUS: "4", el.BTN_SAVE: ""})
    table = fake.elements[list_table]
    table.RowCount, table.VisibleRowCount = 2, 10
    table.VerticalScrollbar = type("Bar", (), {"Position": 0})()

    target = routing("13", "MN15-14 - L505276B", MOLD_LUBE)
    ctx = FakeContext({MAT: [routing("12", "x", MOLD), target]}, sap=SapSession(fake))
    row = runner.RowState(request=request_from_row(2, {"Action": "Delete", "Dept": "MD", "Material": MAT,
                                                       "Resource": "MN15-14", "Tool": "L505276B"}))
    step = InactivateRouting()
    step.plan(row, ctx)
    result = step.run(row, ctx)

    assert result.status is Status.DONE and result.message.startswith("M0527609/13 inactive")
    assert ("vkey", 2, f"{list_table}/txt[1,1]") in fake.actions                 # double-click row of GrC 13
    assert fake.elements[el.HEADER_DELETION_FLAG].selected and fake.elements[el.HEADER_STATUS].text == "1"
    assert ("press", el.BTN_SAVE) in fake.actions


def status_sap(kind, text):
    from routing.sap import elements as el
    from routing.sap.session import SapSession
    fake = FakeSap({"wnd[0]": "", el.STATUS_BAR: text})
    fake.elements[el.STATUS_BAR].MessageType = kind
    return fake, SapSession(fake)


def test_initial_screen_skips_e3_and_not_exist_but_not_other_material_status():
    from routing.sap.session import SapError, SapSkip
    for text in ("Material 5013300800 has status E3", "Material does not exist"):
        with pytest.raises(SapSkip):
            status_sap("W", text)[1].check_initial("CA02 x")
    fake, sap = status_sap("W", "Plant-specific material status S1 'S+E in this plant' is set")
    sap.check_initial("CA02 x")                                     # S1 / S2: Enter, no skip
    assert [a for a in fake.actions if a[0] == "vkey"] == [("vkey", 0, None)] * 2
    with pytest.raises(SapError):
        status_sap("E", "Group ME31 locked by user")[1].check_initial("CA02 x")    # E3 only as a word


def test_e3_material_is_skipped_while_planning_for_every_action():
    ctx = FakeContext({MAT: [routing("15", "MF15-17 - L505276A", MOLD)]}, statuses={MAT: "E3"})
    for values in (create_row(),
                   {"Action": "Delete", "Dept": "MD", "Material": MAT, "Resource": "MF15-17", "Tool": "L505276A"},
                   {"Action": "Assign Components", "Dept": "MD", "Material": MAT, "Resource": "MF15-17",
                    "Tool": "L505276A"}):
        row = runner.RowState(request=request_from_row(2, values))
        runner.plan_rows([row], ctx)
        assert row.plan.steps and all(row.plan.skip[s] == "material status E3 (not active in this plant)"
                                      for s in row.plan.steps)
    ok = runner.RowState(request=request_from_row(2, create_row()))
    runner.plan_rows([ok], FakeContext({MAT: [routing("15", "MF15-17 - L505276A", MOLD)]}, statuses={MAT: "S1"}))
    assert "CreateRouting" not in ok.plan.skip                     # S1 / S2 are planned normally


def test_initial_screen_warning_gets_extra_enter():
    fake, sap = status_sap("W", "Routing has dependent objects")
    sap.check_initial("CA02 x")                                     # warning: no error raised
    assert [a for a in fake.actions if a[0] == "vkey"] == [("vkey", 0, None)] * 2


def test_sap_skip_is_skipped_not_failed():
    from routing.sap.session import SapSkip

    class Refused:
        name, phase = "CreateRouting", "routing"

        def run(self, row, ctx):
            raise SapSkip("CA01 x: material has status E3")

    ctx = FakeContext({}, sap=type("S", (), {"reset": lambda self: None})())
    result = runner.safe_run(Refused(), None, ctx)
    assert result.status is Status.SKIPPED and "E3" in result.message


def test_recipes_skip_phases_not_requested():
    row = runner.RowState(request=request_from_row(2, create_row()))
    assert [s.name for s in recipes.steps_for(row, ("pv",))] == ["CreateProductionVersion"]
    assert [s.name for s in recipes.steps_for(row, ("opc",))] == []
    assert [s.name for s in recipes.steps_for(row)] == ["CreateRouting", "AllocateComponents", "CreateProductionVersion"]


def test_delete_without_tool_never_guesses_between_routings():
    # PLT: no tool, two active routings with the same resource -> skip, ask for group / counter
    plt_ops = [("0010", "PPQM", "XQA"), ("0020", "PP01", "PM2-A"), ("0030", "PP94", "OPMINS")]
    plating = [routing("21", "PM2-A - 5052760989", plt_ops), routing("22", "PM2-A - 5052760989", plt_ops)]
    delete = {"Action": "Delete", "Dept": "PLT", "Material": MAT, "Resource": "PM2-A"}
    step = InactivateRouting()

    row = runner.RowState(request=request_from_row(2, delete))
    step.plan(row, FakeContext({MAT: plating}))
    assert row.plan.skip["InactivateRouting"] == "2 routings match (M0527609/22, M0527609/21), fill group / group counter"

    row = runner.RowState(request=request_from_row(2, {**delete, "group": "M0527609", "group counter": "21"}))
    step.plan(row, FakeContext({MAT: plating}))
    assert "InactivateRouting" not in row.plan.skip and row.key.counter == "21"


# ---------------------------------------------------------------- components + production versions
from routing.steps.components import planned_operation  # noqa: E402

PV_MAT = "5013300800"
KEY_25 = RoutingKey(PV_MAT, "M5013300", "25")
KEY_34 = RoutingKey(PV_MAT, "M5013300", "34")
PV_ROUTINGS = {PV_MAT: [Routing(KEY_25, "MF50-03 - L501330A", "4", operations=(Operation("0020", "PP01", "MF50-03"),)),
                        Routing(KEY_34, "MF50-09 - L501330A", "4", operations=(Operation("0020", "PP01", "MF50-09"),))]}
PV_VERSIONS = {PV_MAT: [ProductionVersion(PV_MAT, "0001", KEY_25, 1), ProductionVersion(PV_MAT, "0005", KEY_25, 2),
                        ProductionVersion(PV_MAT, "0004", KEY_34, 1)]}


def pv_row(**extra):
    values = {**create_row(Material=PV_MAT, Resource="MF50-09", Tool="L501330A"), **extra}
    return runner.RowState(request=request_from_row(2, values))


def plan_all(row, ctx):
    steps = recipes.steps_for(row)
    row.plan.steps = [s.name for s in steps]
    for step in steps:
        step.plan(row, ctx)
    return row.plan


def test_all_bom_creates_only_missing_versions():
    # ALL BOM concern (production_version.md): M5013300/34 already has B1 -> only B2, B3, no duplicate
    ctx = FakeContext(PV_ROUTINGS, versions=PV_VERSIONS, alt_boms={PV_MAT: [1, 2, 3]})
    plan = plan_all(pv_row(**{"Alt Bom": "ALL BOM"}), ctx)
    assert plan.skip["CreateRouting"] == "routing already exists M5013300/34"
    assert plan.alt_boms == [2, 3] and plan.component_alt_boms == [1, 2, 3]


def test_version_for_one_alt_bom_is_skipped_when_it_exists():
    ctx = FakeContext(PV_ROUTINGS, versions=PV_VERSIONS, alt_boms={PV_MAT: [1, 2, 3]})
    plan = plan_all(pv_row(**{"Alt Bom": 1}), ctx)
    assert plan.skip["CreateProductionVersion"] == "versions exist: 0004 (B1)"


def test_new_routing_gets_versions_after_the_routing_phase():
    # MF50-20 does not exist: the routing is created in this run, versions are planned for it
    ctx = FakeContext(PV_ROUTINGS, versions=PV_VERSIONS, alt_boms={PV_MAT: [1, 2, 3]})
    plan = plan_all(pv_row(Resource="MF50-20", **{"Alt Bom": "ALL BOM"}), ctx)
    assert "CreateRouting" not in plan.skip and plan.copy_from.key == KEY_34
    assert plan.alt_boms == [1, 2, 3] and "CreateProductionVersion" not in plan.skip


def test_plating_has_no_component_allocation_and_delete_targets_versions():
    assert "AllocateComponents" not in [s.name for s in recipes.steps_for(pv_row(Dept="PLT"))]
    ctx = FakeContext(PV_ROUTINGS, versions=PV_VERSIONS)
    row = runner.RowState(request=request_from_row(2, {"Action": "Delete", "Dept": "MD", "Material": PV_MAT,
                                                       "Resource": "MF50-03", "Tool": "L501330A"}))
    plan_all(row, ctx)
    assert row.key == KEY_25 and [v.version for v in row.plan.existing_versions] == ["0001", "0005"]


def test_component_rule_from_sap_automation():
    assert planned_operation("CARTON BOX 300x200", "") == ("0030", "packaging")
    assert planned_operation("Lubricant oil", "YMHI-1")[0] == "0030"
    assert planned_operation("Lubricant oil", "OMINS")[0] == "0020"
    assert planned_operation("TERMINAL", "YMHI-1")[0] == "0020"


def test_version_text_drops_material_when_too_long():
    routing = Routing(RoutingKey("5019400308", "M", "1"), "MF15-13 - 5019400308 - L501940E 03 #03")
    assert ProductionVersion.text_for(routing, 2) == "MF15-13 - L501940E 03 #03 B2"


# ---------------------------------------------------------------- UiPath main_bom_assignment
def plan_steps(values, ctx):
    row = runner.RowState(request=request_from_row(2, values))
    for step in recipes.steps_for(row):
        row.plan.steps.append(step.name)
        step.plan(row, ctx)
    return row


def test_assign_components_action_on_existing_routing():
    ctx = FakeContext({MAT: [routing("13", "MN15-14 - L505276B - YMHI-1", MOLD_LUBE),
                             routing("15", "MF15-17 - L505276A", MOLD), routing("16", "MF15-17 - L505276C", MOLD)]},
                      alt_boms={MAT: [1, 2]})
    assign = {"Action": "Assign Components", "Dept": "MD", "Material": MAT, "Resource": "MN15-14",
              "Tool": "L505276B", "Alt Bom": "ALL BOM"}
    row = plan_steps(assign, ctx)
    assert row.plan.steps == ["AllocateComponents"]
    assert str(row.key) == "M0527609/13" and row.plan.component_alt_boms == [1, 2]

    ambiguous = plan_steps(dict(assign, Resource="MF15-17", Tool=""), ctx)
    assert ambiguous.plan.skip["AllocateComponents"].startswith("2 routings match")
    missing = plan_steps(dict(assign, Tool="L505276X"), ctx)
    assert missing.plan.skip["AllocateComponents"] == "routing not found"


# ---------------------------------------------------------------- CA01 / CA02 popup branches
def copy_sap(**windows):
    """Fake SAP after CA01 'Copy from'. windows: select_type / select_object / copy_list (rows)."""
    from routing.sap import elements as el
    texts = {"wnd[0]": "", el.STATUS_BAR: ""}
    if windows.get("select_type"):
        texts.update({"wnd[1]": el.TITLE_SELECT_TYPE, el.COPY_SELECT_TYPE_CONTINUE: ""})
    if windows.get("select_object"):
        texts.update({"wnd[1]": "Create Using Copy Function: Select Object to be Copied",
                      el.COPY_MATERIAL: "", el.COPY_PLANT: "", f"wnd[1]/{el.BTN_ENTER}": ""})
    rows = windows.get("copy_list")
    if rows:
        texts.setdefault("wnd[1]", "Entry Option: Group")
        texts[el.COPY_LIST_TABLE] = ""
        for r, (group, counter) in enumerate(rows):
            texts[f"{el.COPY_LIST_TABLE}/txt[0,{r}]"] = group
            texts[f"{el.COPY_LIST_TABLE}/txt[1,{r}]"] = counter
            texts[f"{el.COPY_LIST_TABLE}/txt[2,{r}]"] = "desc"
    fake = FakeSap(texts)
    if rows:
        table = fake.elements[el.COPY_LIST_TABLE]
        table.RowCount, table.VisibleRowCount = len(rows), 10
        table.VerticalScrollbar = type("Bar", (), {"Position": 0})()
    return fake


def test_ca01_copy_dialog_all_popups():
    from routing.sap import elements as el
    from routing.sap.screens import ca01
    from routing.sap.session import SapSession
    fake = copy_sap(select_type=True, select_object=True, copy_list=[("M0527609", "12"), ("", "13"), ("", "15")])
    source = RoutingKey(MAT, "M0527609", "13")
    assert ca01.choose_copy_source(SapSession(fake), source, 3) == ""
    assert ("press", el.COPY_SELECT_TYPE_CONTINUE) in fake.actions
    assert fake.elements[el.COPY_MATERIAL].text == MAT
    assert ("vkey", 2, f"{el.COPY_LIST_TABLE}/txt[2,1]") in fake.actions        # group carried to row 1


def test_ca01_copy_dialog_only_list_and_none():
    from routing.sap import elements as el
    from routing.sap.screens import ca01
    from routing.sap.session import SapError, SapSession
    source = RoutingKey(MAT, "M0527609", "13")
    fake = copy_sap(copy_list=[("M0527609", "13")])                              # no Select Type / Object
    assert ca01.choose_copy_source(SapSession(fake), source, 1) == ""
    assert not any(a[0] == "press" for a in fake.actions)
    # nothing shown: SAP copied the only routing itself -> fine with 1 routing, error with more
    assert ca01.choose_copy_source(SapSession(copy_sap()), source, 1) == "single routing, copied by SAP without list"
    with pytest.raises(SapError, match="has 2 routings"):
        ca01.choose_copy_source(SapSession(copy_sap()), source, 2)


def test_ca02_without_group_popup_or_header_list():
    from routing.sap import elements as el
    from routing.sap.screens import ca02
    from routing.sap.session import SapError, SapSession
    texts = {"wnd[0]": "", el.OKCODE: "", el.STATUS_BAR: "", el.INIT_MATERIAL: "", el.INIT_PLANT: ""}
    key = RoutingKey(MAT, "M0527609", "13")
    assert ca02.open_routing(SapSession(FakeSap(texts)), key, 1) == "single routing in group"
    with pytest.raises(SapError, match="has 2 routings"):
        ca02.open_routing(SapSession(FakeSap(texts)), key, 2)


# ---------------------------------------------------------------- blank optional values per department
@pytest.mark.parametrize("dept, extra, expected", [
    ("PLT", {"Resource": "PM2-A", "Tool": None}, "PM2-A - 5052760989"),            # plating, no tool
    ("PLT", {"Resource": "PM2-A", "Tool": "0"}, "PM2-A - 5052760989"),             # UiPath "0" = no tool
    ("PLT", {"Resource": "PM2-A", "Tool": "L505276P"}, "PM2-A - 5052760989 - L505276P"),
    ("AS", {"Resource": "AS-01", "Tool": None}, "AS-01 - 5052760989"),
    ("AS", {"Resource": "AS-01", "Tool": "NULL"}, "AS-01 - 5052760989"),
    ("MD", {"Sorting/ Lubricant": None}, "MN15-20 - 5052760989 - L505276B"),      # mold without sorting
    ("MD", {"Sorting/ Lubricant": float("nan")}, "MN15-20 - 5052760989 - L505276B"),
    ("MD", {"Sorting/ Lubricant": "YMHI-1", "Sorting/ Lubricant Capacity": 100000},
     "MN15-20 - L505276B - YMHI-1"),
])
def test_blank_tool_or_sorting_never_breaks_names(dept, extra, expected):
    request = request_from_row(2, create_row(Dept=dept, **extra))
    layout = layouts.layout_for(request)
    text = layouts.description(layout, request)
    assert text == expected and not text.endswith("-") and "None" not in text and "nan" not in text
    assert ProductionVersion.text_for(Routing(RoutingKey(MAT, "G", "1"), text), 1) == f"{expected} B1"


def test_blank_values_needed_by_the_layout_skip_the_row_not_the_run():
    # mold / stamping need a tool and cavity: the row is skipped with a reason, nothing crashes
    row = plan_steps(create_row(Tool=None, **{"Tool Cavity": None}), FakeContext({MAT: [routing("15", "x", MOLD)]}))
    assert row.plan.skip["CreateRouting"] == "missing Tool, Tool Cavity for layout MD"
    # sorting given without its capacity: the row is invalid, the message says which column
    with pytest.raises(InputError, match="Sorting/ Lubricant Capacity missing"):
        request_from_row(2, create_row(**{"Sorting/ Lubricant": "YMHI-1"}))


# ---------------------------------------------------------------- copy source: sorting shape
def test_copy_source_sorting_shape_comes_from_operations_not_name():
    lube = routing("13", "MN15-14 - L505276B", MOLD_LUBE)                     # YMHI-1 op, name without YMHI
    named_only = routing("14", "MN15-14 - L505276B - YMHI-1", MOLD)           # YMHI in name, no YMHI op
    plain = routing("15", "MF15-17 - L505276A", MOLD)
    trial = routing("16", "MDTRIAL YMHI-1", MOLD_LUBE)                        # never copied
    ctx = FakeContext({MAT: [lube, named_only, plain, trial]})
    sorting = {"Sorting/ Lubricant": "YMHI-1", "Sorting/ Lubricant Capacity": 100000}

    assert plan_steps(create_row(**sorting), ctx).plan.copy_from.key.counter == "13"    # by the operation
    assert plan_steps(create_row(), ctx).plan.copy_from.key.counter == "15"            # newest without YMHI op
    # override with the wrong shape is refused, not just warned
    wrong = plan_steps(create_row(COPY_FROM_GROUP="M0527609", COPY_FROM_GC="15", **sorting), ctx)
    assert wrong.plan.skip["CreateRouting"] == "COPY_FROM M0527609/15 must be a routing with a YMHI sorting step"
    # no routing with a sorting step at all -> skip with the reason
    none = plan_steps(create_row(**sorting), FakeContext({MAT: [plain, named_only]}))
    assert "with a YMHI sorting step" in none.plan.skip["CreateRouting"]


def test_copy_source_prefers_same_sorting_work_center():
    ymhi4 = [("0005", "PP07", "TMC"), ("0010", "PPQM", "XQA"), ("0020", "PP01", "MN15-14"),
             ("0030", "PP96", "YMHI-4"), ("0040", "PP94", "OMINS")]
    routings = MaterialRoutings(MAT, (routing("13", "a", MOLD_LUBE), routing("17", "b", ymhi4)))
    assert routings.copy_source(lambda r: True, needs_sorting=True, sorting="YMHI-1").key.counter == "13"
    assert routings.copy_source(lambda r: True, needs_sorting=True, sorting="YMHI-4").key.counter == "17"


# ---------------------------------------------------------------- BOM allocation (as SAP_automation)
def test_bom_allocation_all_bom_two_passes_per_alt_bom(monkeypatch):
    from routing.steps import components as step_module
    calls, table = [], {}

    def open_routing(sap, key, size, plant):
        calls.append(("open", str(key)))
        return ""

    def open_allocation(sap, alt_bom, count):
        calls.append(("bom", alt_bom))
        table.clear()
        table.update({0: ("CARTON BOX", ""), 1: ("RESIN", ""), 2: ("Lubricant oil", ""), 3: ("PIN", "0020")})
        return None

    def unassigned(sap):
        return [(r, d) for r, (d, op) in table.items() if not op], ""

    def assign(sap, rows, operation):
        calls.append(("assign", operation, tuple(rows)))
        for r in rows:
            table[r] = (table[r][0], operation)

    monkeypatch.setattr(step_module.ca02, "open_routing", open_routing)
    monkeypatch.setattr(step_module.ca02, "save", lambda sap, what: calls.append(("save", what)) or "")
    monkeypatch.setattr(step_module.components, "open_allocation", open_allocation)
    monkeypatch.setattr(step_module.components, "unassigned_components", unassigned)
    monkeypatch.setattr(step_module.components, "assign", assign)

    lube = routing("13", "MN15-14 - L505276B - YMHI-1", MOLD_LUBE)
    ctx = FakeContext({MAT: [lube]}, sap=object(), alt_boms={MAT: [1, 3]})          # active: 1 and 3 (2 gone)
    row = plan_steps({"Action": "Assign Components", "Dept": "MD", "Material": MAT, "Resource": "MN15-14",
                      "Tool": "L505276B", "Alt Bom": "ALL BOM"}, ctx)
    assert row.plan.component_alt_boms == [1, 3]                  # every active alt BOM, by number
    result = step_module.AllocateComponents().run(row, ctx)

    per_bom = [("open", "M0527609/13"), ("bom", None), ("assign", "0030", (0, 2)), ("assign", "0020", (1,)),
               ("save", None)]
    assert [c[0] for c in calls] == [c[0] for c in per_bom] * 2
    assert [c[1] for c in calls if c[0] == "bom"] == [1, 3]
    assert ("assign", "0030", (0, 2)) in calls and ("assign", "0020", (1,)) in calls   # PIN kept (already 0020)
    assert result.status is Status.DONE and result.message == "B1 0030: 2, 0020: 1; B3 0030: 2, 0020: 1"

    one = plan_steps({"Action": "Assign Components", "Dept": "MD", "Material": MAT, "Resource": "MN15-14",
                      "Tool": "L505276B", "Alt Bom": 3}, ctx)
    assert one.plan.component_alt_boms == [3]                     # a number = only that alt BOM
    gone = plan_steps({"Action": "Assign Components", "Dept": "MD", "Material": MAT, "Resource": "MN15-14",
                       "Tool": "L505276B", "Alt Bom": 2}, ctx)
    assert gone.plan.skip["AllocateComponents"] == "alt BOM 2 not active (active: 1, 3)"


# ---------------------------------------------------------------- UiPath defects fixed
def test_failed_row_resets_sap_and_run_continues_but_stops_when_reset_fails(tmp_path):
    path = tmp_path / "requests.xlsx"
    write_book(path, [create_row(), create_row(Resource="MN15-30"), create_row(Resource="MN15-31")])

    class Boom(RecordingStep):
        def run(self, row, ctx):
            self.calls += 1
            raise RuntimeError("unexpected popup 'Information'")

    class Sap:
        resets, fail = 0, False

        def reset(self):
            Sap.resets += 1
            if Sap.fail:
                raise RuntimeError("session gone")

    step = Boom("CreateRouting", "routing", StepResult.done("x"))
    ctx = FakeContext({MAT: []}, sap=Sap())
    summary = runner.run(path, ctx=ctx, recipes={Action.CREATE: [step]})
    assert step.calls == 3 and Sap.resets == 3 and summary.counts == {"Failed": 3} and not summary.aborted
    sheet = load_workbook(path).active
    assert str(sheet.cell(2, [c.value for c in sheet[1]].index("RESULT_ROUTING") + 1).value).startswith(
        "Failed: unexpected popup")

    write_book(path, [create_row(), create_row(Resource="MN15-30")])
    Sap.fail, step.calls = True, 0
    summary = runner.run(path, ctx=FakeContext({MAT: []}, sap=Sap()), recipes={Action.CREATE: [step]})
    assert step.calls == 1 and summary.aborted.startswith("stopped after row 2")       # row 3 not touched


def test_action_is_case_insensitive_and_unknown_action_does_nothing():
    for text in ("Add", "add", " ADD ", "create", "CREATE", " Create "):   # Add = file name, Create = alias
        assert request_from_row(2, create_row(Action=text)).action is Action.CREATE
    assert request_from_row(2, {"Action": "assign components", "Dept": "MD", "Material": MAT,
                                "Resource": "X"}).action is Action.ASSIGN
    with pytest.raises(InputError, match="unknown"):
        request_from_row(2, create_row(Action="CHANGE"))
