"""Operation overview + Operation Details (CA01 and CA02 share these screens)."""
from routing.sap import elements as el
from routing.sap import table
from routing.sap.session import SapError


def _cell(sap, col, row):
    return table.cell_id(sap, el.OPERATION_TABLE, col, row)


def work_center_col(sap):
    return table.column_index(sap, el.OPERATION_TABLE, el.OPERATION_WORK_CENTER_TITLES)


def read_work_center(sap, row):
    return table.cell_text(sap, el.OPERATION_TABLE, work_center_col(sap), row)


def set_work_center(sap, row, value):
    sap.set_text(_cell(sap, work_center_col(sap), row), value)


def set_base_quantity(sap, row, value):
    sap.set_text(_cell(sap, el.OPERATION_BASE_QTY_COL, row), format_quantity(value))


def machine_name(sap, row):
    """Double-click the work center -> Display Work Center -> read its description -> Back."""
    sap.double_click(_cell(sap, work_center_col(sap), row))
    name = sap.get_text(el.WORK_CENTER_DISPLAY_TEXT)
    sap.press(el.BTN_BACK)
    return name


def set_details(sap, row, values):
    """Open Operation Details of `row`, type values {field: value}, Enter, Back.
    Field names: el.DETAIL_FIELDS; value "work_center_text" = copy the details' own WC text.
    Returns how many setups were filled after the Enter (fill_missing_setups)."""
    sap.double_click(_cell(sap, el.OPERATION_DESC_COL, row))
    if not sap.exists(el.DETAIL_BASE_QTY):
        raise SapError(f"Operation Details of row {row} did not open ({sap.where()})")
    for field, value in values:
        if value == "work_center_text":
            value = sap.get_text(el.DETAIL_WORK_CENTER_TEXT)
        if isinstance(value, float):
            value = format_quantity(value)
        sap.set_text(el.DETAIL_FIELDS[field], value)
    sap.enter()
    filled = fill_missing_setups(sap)
    sap.press(el.BTN_BACK)
    return filled


# ------------------------------------------------------------ missing setup (docs/verification.md I.4)
MAX_SETUP_CHECKS = 20                           # copied operations without setup, safety limit


def on_setup_check(sap):
    """SAP asks for the setup standard value: 'Create Routing: Operation - Check' screen and / or the
    status 'Enter standard value Setup'. Can follow any Enter of the operation entry (after the
    header, after the work centers, in Operation Details)."""
    return el.TITLE_OPERATION_CHECK in sap.window_title() or el.SETUP_MISSING_TEXT in sap.status()[1]


def _setup_unit_field(sap):
    """The unit field right of the setup value (same line, nearest to the right); None if not found."""
    setup = sap.find(el.DETAIL_SETUP)
    candidates = [c for c in setup.Parent.Children
                  if abs(int(c.Top) - int(setup.Top)) <= 3 and int(c.Left) > int(setup.Left)]
    return min(candidates, key=lambda c: int(c.Left)) if candidates else None


def fill_missing_setups(sap):
    """While SAP asks for the setup: blank STD Setup -> 1, blank unit -> H, Enter; repeated each time
    SAP asks again (once per operation). Call it after every Enter of the operation entry.
    Returns how many times it was filled (0 = SAP did not ask)."""
    filled = 0
    for _ in range(MAX_SETUP_CHECKS):
        if sap.exists(el.OPERATION_TABLE) or not on_setup_check(sap):
            return filled
        if not sap.exists(el.DETAIL_SETUP):
            raise SapError(f"Setup asked but no setup field on the screen ({sap.where()})")
        if not sap.get_text(el.DETAIL_SETUP):
            sap.set_text(el.DETAIL_SETUP, el.SETUP_DEFAULT)
        unit = _setup_unit_field(sap)
        if unit is None:
            raise SapError(f"Setup unit field not found ({sap.where()})")
        if not str(unit.text).strip():
            unit.text = el.SETUP_DEFAULT_UNIT
        sap.enter()
        filled += 1
        kind, text = sap.status()
        if kind in ("E", "A") and el.SETUP_MISSING_TEXT not in text:
            raise SapError(f"Operation - Check: {text}")
    raise SapError(f"SAP still asks for the setup after {MAX_SETUP_CHECKS} times ({sap.where()})")


def format_quantity(value):
    """923.0 -> '923', 0.99 -> '0.99' (SAP user format with '.' decimals assumed)."""
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"
