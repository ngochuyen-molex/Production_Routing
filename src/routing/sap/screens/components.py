"""Component allocation in CA02: choose the alt BOM, assign unassigned components to operations.

Screen code from SAP_automation/change_bom/routing.py (open_component_allocation, select_components,
assign_to_operation). Which operation a component goes to is a business rule: steps/components.py.
"""
from routing.sap import elements as el
from routing.sap import table
from routing.sap.screens import ca01
from routing.sap.session import SapError


def open_allocation(sap, alt_bom, alt_bom_count):
    """Operation overview -> CompAlloc -> 'Choose Alternative BOM' popup (by value).
    No popup = SAP opened the only BOM; only fine when the material has one active alt BOM."""
    sap.press(el.BTN_COMPONENT_ALLOCATION)
    if not sap.has_window(1):
        if alt_bom_count > 1:
            raise SapError(f"BOM popup not shown, but material has {alt_bom_count} active alt BOMs ({sap.where()})")
        return
    ca01.choose_alt_bom(sap, alt_bom)
    if not sap.exists(el.COMPONENT_TABLE):
        raise SapError(f"Component overview not shown ({sap.where()})")


def unassigned_components(sap):
    """[(visible row, description)] of components without an operation; visible page only,
    like SAP_automation (a warning is returned when the table has more rows)."""
    grid = sap.find(el.COMPONENT_TABLE)
    visible = min(int(grid.VisibleRowCount), int(grid.RowCount))
    rows = []
    for row in range(visible):
        cells = [table.cell_text(sap, el.COMPONENT_TABLE, col, row) for col in range(el.COMPONENT_OPERATION_COL)]
        if not any(cells):
            return rows, ""
        if not table.cell_text(sap, el.COMPONENT_TABLE, el.COMPONENT_OPERATION_COL, row):
            rows.append((row, table.cell_text(sap, el.COMPONENT_TABLE, el.COMPONENT_DESC_COL, row)))
    more = int(grid.RowCount) > visible
    return rows, (f"component table has more rows than visible ({visible}); rows below not checked" if more else "")


def assign(sap, rows, operation):
    """Tick `rows`, New Assignment, type `operation`, Enter. Other rows are unticked."""
    grid = sap.find(el.COMPONENT_TABLE)
    wanted = set(rows)
    for row in range(min(int(grid.VisibleRowCount), int(grid.RowCount))):
        line = sap.find(el.COMPONENT_TABLE).getAbsoluteRow(row)
        if row in wanted or line.selected:
            line.selected = row in wanted
    sap.find(f"{el.COMPONENT_TABLE}/{el.COMPONENT_SELECT.format(row=max(rows))}").setFocus()
    sap.press(el.BTN_NEW_ASSIGNMENT)
    if not sap.exists(el.NEW_ASSIGNMENT_OPERATION):
        raise SapError(f"New Assignment did not open the operation popup ({sap.where()})")
    sap.set_text(el.NEW_ASSIGNMENT_OPERATION, operation)
    sap.enter(window=1)
    sap.raise_on_error(f"assign to {operation}")
