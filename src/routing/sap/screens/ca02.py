"""CA02 - change routing: open one routing by group + counter, header details, save.

Navigation from SAP_automation/change_bom/routing.py (open_routing, select_group, open_header_row).
"""
from routing.core.config import PLANT
from routing.sap import elements as el
from routing.sap import table
from routing.sap.session import SapError


def _counter(value):
    return str(value).strip().lstrip("0") or "0"


def open_routing(sap, key, group_size, plant=PLANT):
    """CA02 initial screen -> operation overview of `key` (RoutingKey).
    group_size = number of routings in the group (Snowflake); needed when SAP skips the lists.
    Returns a note for the result message ('' normally)."""
    sap.start_transaction("CA02")
    sap.set_text(el.INIT_MATERIAL, key.material)
    sap.set_text(el.INIT_PLANT, plant)
    sap.enter()
    sap.raise_on_error(f"CA02 {key.material}")

    if sap.exists(el.GROUP_POPUP_TABLE):
        row = table.find_row(sap, el.GROUP_POPUP_TABLE,
                             lambda r: table.cell_text(sap, el.GROUP_POPUP_TABLE, el.GROUP_POPUP_GROUP_COL, r) == key.group)
        if row is None:
            raise SapError(f"Group {key.group} not in the group popup")
        sap.double_click(table.cell_id(sap, el.GROUP_POPUP_TABLE, el.GROUP_POPUP_DESC_COL, row), window=1)

    if sap.exists(el.HEADER_LIST_TABLE):
        row = table.find_row(sap, el.HEADER_LIST_TABLE,
                             lambda r: _counter(table.cell_text(sap, el.HEADER_LIST_TABLE,
                                                                el.HEADER_LIST_COUNTER_COL, r)) == key.counter)
        if row is None:
            raise SapError(f"Group counter {key.counter} not in the header list of {key.group}")
        sap.double_click(table.cell_id(sap, el.HEADER_LIST_TABLE, el.HEADER_LIST_DESC_COL, row))
        return ""

    # SAP opened the only routing of the group directly: the counter can't be checked on screen,
    # so only continue when Snowflake says the group has one routing (SAP_automation A2 / UiPath risk 6)
    if group_size > 1:
        raise SapError(f"No header list shown, but group {key.group} has {group_size} routings ({sap.where()})")
    return "single routing in group"


def open_header_details(sap):
    """Operation overview -> Header Details (F5)."""
    sap.press(el.BTN_HEADER)


def set_inactive(sap):
    """Header Details: tick the deletion flag, status 1 (docs/uipath_flows.md 7.1)."""
    flag = sap.find(el.HEADER_DELETION_FLAG)
    if not flag.selected:
        flag.selected = True
    sap.set_text(el.HEADER_STATUS, "1")


def is_inactive(sap):
    return bool(sap.find(el.HEADER_DELETION_FLAG).selected) and sap.get_text(el.HEADER_STATUS) == "1"


def save(sap, what):
    sap.press(el.BTN_SAVE)
    sap.raise_on_error(f"Save {what}")
    return sap.status()[1]
