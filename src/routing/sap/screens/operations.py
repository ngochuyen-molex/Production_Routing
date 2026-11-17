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
    """Open Operation Details of `row`, type values {field: value}, Back.
    Field names: el.DETAIL_FIELDS; value "work_center_text" = copy the details' own WC text."""
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
    sap.press(el.BTN_BACK)


def format_quantity(value):
    """923.0 -> '923', 0.99 -> '0.99' (SAP user format with '.' decimals assumed)."""
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"
