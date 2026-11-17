"""Which layout a row uses, the values it types, and whether a routing fits as copy source."""
from dataclasses import dataclass

from routing.layouts.catalog import (CAPACITY, CAPACITY_X_CAVITY, KEEP, LAYOUTS, RESOURCE,
                                     SORTING, SORTING_CAPACITY, TOOL)
from routing.model.enums import Dept
from routing.model.enums import OperationRole as Role

ROUTING_TEXT_LIMIT = 40                 # PLKO-KTEXT length

FORMULAS = {                            # formula name -> value from (request, params)
    CAPACITY: lambda req, p: p.capacity,
    CAPACITY_X_CAVITY: lambda req, p: p.capacity_x_cavity,
    SORTING_CAPACITY: lambda req, p: p.sorting_capacity,
    "tool_cavity": lambda req, p: p.tool_cavity,
    "efficiency": lambda req, p: p.efficiency,
    "utilization": lambda req, p: p.utilization,
    "one": lambda req, p: 1,
}
WORK_CENTER_SOURCES = {
    RESOURCE: lambda req, p: req.resource,
    TOOL: lambda req, p: req.tool,
    SORTING: lambda req, p: p.sorting,
    KEEP: lambda req, p: "",
}


@dataclass(frozen=True)
class OperationValue:
    """What CreateRouting types into one row of the operation overview (layout + request)."""
    role: Role
    row: int
    work_center: str = ""       # "" = keep what the copy source has
    base_quantity: float | None = None
    details: tuple[tuple[str, object], ...] = ()   # (Operation Details field, value)


def layout_for(request):
    """Department + request features -> layout."""
    if request.dept is Dept.MD:
        return LAYOUTS["MD_SORTING" if request.params.sorting else "MD"]
    return LAYOUTS[request.dept.value]


def description(layout, request):
    """Routing description; ValueError when longer than SAP allows."""
    text = layout.description.format(resource=request.resource, material=request.material,
                                     tool=request.tool, sorting=request.params.sorting)
    if len(text) > ROUTING_TEXT_LIMIT:
        raise ValueError(f"Routing description longer than {ROUTING_TEXT_LIMIT}: '{text}'")
    return text


def operation_values(layout, request):
    """The layout filled with the request's values, in row order.
    Detail values SAP provides at run time (machine name, WC text) stay as their name."""
    params = request.params
    values = []
    for slot in layout.slots:
        details = []
        for field, source in slot.details:
            value = FORMULAS[source](request, params) if source in FORMULAS else source
            if value is not None:
                details.append((field, value))
        values.append(OperationValue(
            role=slot.role, row=slot.row,
            work_center=WORK_CENTER_SOURCES[slot.work_center](request, params),
            base_quantity=FORMULAS[slot.base_qty](request, params) if slot.base_qty else None,
            details=tuple(details)))
    return values


def missing_inputs(layout, request):
    """Request values the layout needs but the row does not have."""
    params, missing = request.params, []
    if layout.slot(Role.TOOL) and not request.tool:
        missing.append("Tool")
    if any(s.base_qty == CAPACITY_X_CAVITY for s in layout.slots) and not params.tool_cavity:
        missing.append("Tool Cavity")
    if layout.slot(Role.SORTING) and params.sorting_capacity is None:
        missing.append("Sorting/ Lubricant Capacity")
    return missing


def check_copy_source(layout, routing):
    """Warnings when the routing to copy does not have the operations the layout expects
    (rows would shift and values land on the wrong operation). Roles: Routing.operation()."""
    name = f"copy source {routing.key}"
    has_sorting = routing.operation(Role.SORTING) is not None
    warnings = []
    if routing.operation(Role.PRODUCTION) is None:
        warnings.append(f"{name} has no production operation 0020")
    if layout.slot(Role.SORTING) and not has_sorting:
        warnings.append(f"{name} has no YMHI sorting operation")
    if not layout.slot(Role.SORTING) and has_sorting:
        warnings.append(f"{name} has a YMHI sorting operation, layout {layout.id} expects none")
    if layout.slot(Role.FINAL) and routing.operation(Role.FINAL) is None:
        warnings.append(f"{name} has no final step (PP94 / ZP04)")
    return warnings
