"""SAP GUI table controls: read cells, page through rows, find a row by value."""
from routing.sap.session import SapError


def cell_text(sap, table_id, col, row):
    """Cells are txt or ctxt depending on the field; try both.
    # from SAP_automation/change_bom/routing.py:get_cell_text"""
    for kind in ("txt", "ctxt"):
        element_id = f"{table_id}/{kind}[{col},{row}]"
        if sap.exists(element_id):
            return sap.get_text(element_id)
    return ""


def cell_id(sap, table_id, col, row):
    for kind in ("txt", "ctxt"):
        element_id = f"{table_id}/{kind}[{col},{row}]"
        if sap.exists(element_id):
            return element_id
    raise SapError(f"No cell [{col},{row}] in {table_id}")


def find_row(sap, table_id, match, blank_col=0):
    """Page through the table; return the VISIBLE row index of the first row for which
    match(row_index) is True, with the table scrolled to that page. None if not found.
    Stops at the first row whose `blank_col` and the next column are empty.
    # from SAP_automation/change_bom/routing.py:find_row (generalised to a predicate)"""
    table = sap.find(table_id)
    total_rows, visible_rows = int(table.RowCount), int(table.VisibleRowCount)

    position = 0
    while position < total_rows:
        sap.find(table_id).VerticalScrollbar.Position = position
        first_row = int(sap.find(table_id).VerticalScrollbar.Position)
        for row in range(min(visible_rows, total_rows - first_row)):
            if not cell_text(sap, table_id, blank_col, row) and not cell_text(sap, table_id, blank_col + 1, row):
                return None
            if match(row):
                return row
        if first_row + visible_rows >= total_rows:
            break
        position = first_row + visible_rows
    return None


def column_index(sap, table_id, titles):
    """Index of the first column whose title is one of `titles` (case-insensitive)."""
    wanted = {t.lower() for t in titles}
    columns = sap.find(table_id).Columns
    for index in range(int(columns.Count)):
        column = columns.ElementAt(index)
        if str(column.Title).strip().lower() in wanted:
            return index
    raise SapError(f"Column {titles} not found in {table_id}")
