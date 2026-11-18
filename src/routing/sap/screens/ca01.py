"""CA01 - create routing by copying a routing of the same material (docs/uipath_flows.md 3)."""
from routing.core.config import PLANT
from routing.model.entities import RoutingKey
from routing.sap import elements as el
from routing.sap import table
from routing.sap.session import SapError


def _counter(value):
    return str(value).strip().lstrip("0") or "0"


def start(sap, material, plant=PLANT):
    """CA01 initial screen: material + plant, then Copy from."""
    sap.start_transaction("CA01")
    sap.set_text(el.INIT_MATERIAL, material)
    sap.set_text(el.INIT_PLANT, plant)
    sap.press(el.CA01_COPY_FROM)
    sap.check_initial(f"CA01 {material}")


def choose_target_group(sap, group):
    """'Entry Option: Group' popup (material already has groups): the new counter goes into `group`.
    No popup = SAP proposes the group itself."""
    if not sap.exists(el.GROUP_POPUP_TABLE):
        return
    row = table.find_row(sap, el.GROUP_POPUP_TABLE,
                         lambda r: table.cell_text(sap, el.GROUP_POPUP_TABLE, el.GROUP_POPUP_GROUP_COL, r) == group)
    if row is None:
        raise SapError(f"Group {group} not in the 'Entry Option: Group' popup")
    sap.double_click(table.cell_id(sap, el.GROUP_POPUP_TABLE, el.GROUP_POPUP_DESC_COL, row), window=1)


def choose_copy_source(sap, source: RoutingKey, routing_count, plant=PLANT):
    """Copy dialog after 'Copy from', as UiPath find_valid_routing_tocopy. Each screen may or may not
    appear:
      'Select Type' popup         -> Continue
      'Select Object to be Copied' -> material + plant, Continue
      copy list (2120)            -> pick the source by group + counter (UiPath: first status-4 row)
      none of them                -> SAP copied the only routing of the material itself and goes on
                                     (BOM popup / header); only accepted when the material has 1 routing
    routing_count = routings of the material in SAP (Snowflake). Returns a note ('' normally)."""
    if sap.window_title(1) == el.TITLE_SELECT_TYPE:
        sap.press(el.COPY_SELECT_TYPE_CONTINUE)
    if sap.exists(el.COPY_MATERIAL):
        sap.set_text(el.COPY_MATERIAL, source.material)
        sap.set_text(el.COPY_PLANT, plant)
        sap.press(f"wnd[1]/{el.BTN_ENTER}")
        sap.raise_on_error(f"Copy from {source}")

    if not sap.exists(el.COPY_LIST_TABLE):
        if routing_count > 1:
            raise SapError(f"Copy list not shown, but {source.material} has {routing_count} routings "
                           f"- cannot tell which one SAP copied ({sap.where()})")
        return "single routing, copied by SAP without list"
    current_group = {"value": ""}

    def is_source(r):
        group = table.cell_text(sap, el.COPY_LIST_TABLE, el.COPY_LIST_GROUP_COL, r)
        current_group["value"] = group or current_group["value"]     # group only on its first row
        counter = _counter(table.cell_text(sap, el.COPY_LIST_TABLE, el.COPY_LIST_COUNTER_COL, r))
        return current_group["value"] == source.group and counter == source.counter

    row = table.find_row(sap, el.COPY_LIST_TABLE, is_source, blank_col=el.COPY_LIST_COUNTER_COL)
    if row is None:
        raise SapError(f"Copy source {source.group}/{source.counter} not in the copy list")
    sap.double_click(table.cell_id(sap, el.COPY_LIST_TABLE, el.COPY_LIST_DESC_COL, row), window=1)
    return ""


def choose_alt_bom(sap, alt_bom):
    """'Choose Alternative BOM' popup, row found by the AltBOM value (not by position).
    # from SAP_automation/change_bom/routing.py:open_component_allocation"""
    if not sap.exists(el.BOM_POPUP):
        return
    row = 0
    while sap.exists(f"{el.BOM_POPUP}/txt[{row},{el.BOM_POPUP_ALT_COL}]"):
        cell = f"{el.BOM_POPUP}/txt[{row},{el.BOM_POPUP_ALT_COL}]"
        if _counter(sap.get_text(cell)) == str(alt_bom):
            usage_cell = f"{el.BOM_POPUP}/txt[{row},{el.BOM_POPUP_USAGE_COL}]"
            usage = sap.get_text(usage_cell) if sap.exists(usage_cell) else ""
            if usage and usage != el.PRODUCTION_BOM_USAGE:     # UiPath main_bom_assignment: "check bom again"
                raise SapError(f"Alt BOM {alt_bom} has BOM usage {usage}, expected "
                               f"{el.PRODUCTION_BOM_USAGE}: check the BOM")
            sap.double_click(cell, window=1)
            return
        row += 1
    raise SapError(f"Alt BOM {alt_bom} not in the 'Choose Alternative BOM' popup ({row} rows)")


def fill_header(sap, description, status="4"):
    """Header Data Check: description; read the new group + counter; Header Details: status.
    Returns (group, counter)."""
    if not sap.exists(el.HEADER_DESCRIPTION):
        raise SapError(f"Header data screen not shown ({sap.where()})")
    sap.set_text(el.HEADER_DESCRIPTION, description)
    group = sap.get_text(el.HEADER_GROUP)
    counter = _counter(sap.get_text(el.HEADER_COUNTER))
    sap.set_text(el.HEADER_STATUS, status)
    sap.enter()
    sap.pass_warnings("header")                 # UiPath mold / plt / stamping: second Enter here
    return group, counter


def open_operations(sap):
    if not sap.exists(el.OPERATION_TABLE):
        sap.press(el.BTN_OPERATIONS)
    if not sap.exists(el.OPERATION_TABLE):
        raise SapError(f"Operation overview not shown ({sap.where()})")
