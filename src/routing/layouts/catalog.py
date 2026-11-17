"""One OperationLayout per production workflow type.

Rows / fields from the UiPath department files (docs/uipath_flows.md 4.1, 4.2). Rows are the
0-based visible rows of the operation overview: 0 = 0005, 1 = 0010, 2 = 0020, ... as in the
5052760989 screenshot (2 = machine, 3 = tool sub-operation, 4 = next operation).
VERIFIED = False until one routing per layout was created from Python and checked in SAP.
"""
from dataclasses import dataclass

from routing.model.enums import OperationRole as Role

# where a work center value comes from
RESOURCE, TOOL, SORTING, KEEP = "resource", "tool", "sorting", "keep"
# base quantity formulas, see layouts/select.py:FORMULAS
CAPACITY, CAPACITY_X_CAVITY, SORTING_CAPACITY = "capacity", "capacity_x_cavity", "sorting_capacity"
# special values for Operation Details
MACHINE_NAME, WORK_CENTER_TEXT = "machine_name", "work_center_text"


@dataclass(frozen=True)
class OperationSlot:
    role: Role
    row: int
    work_center: str = KEEP                 # RESOURCE / TOOL / SORTING / KEEP (copy source value)
    base_qty: str | None = None             # overview base quantity formula, None = not typed
    details: tuple[tuple[str, str], ...] = ()   # (detail field, formula or special value)


@dataclass(frozen=True)
class OperationLayout:
    id: str
    description: str                        # routing description template
    slots: tuple[OperationSlot, ...]
    allocate_components: bool = True
    verified: bool = False

    def slot(self, role):
        return next((s for s in self.slots if s.role is role), None)

    def roles(self):
        return [s.role for s in self.slots]

    def slots_with_capacity(self):
        """Slots whose base quantity carries the capacity (used by a future ChangeCapacity)."""
        return [s for s in self.slots
                if s.base_qty in (CAPACITY, CAPACITY_X_CAVITY) or any(f == "base_qty" for f, _ in s.details)]


# Operation Details of the machine / tool line (STP and MD)
_LINE_DETAILS = (("base_qty", CAPACITY), ("cavity", "tool_cavity"),
                 ("efficiency", "efficiency"), ("utilization", "utilization"))

LAYOUTS = {
    "AS": OperationLayout(
        "AS", "{resource} - {material}",
        (OperationSlot(Role.PRODUCTION, 1, RESOURCE, CAPACITY),
         OperationSlot(Role.FINAL, 2, KEEP, CAPACITY))),
    "PLT": OperationLayout(
        "PLT", "{resource} - {material} - {tool}",
        (OperationSlot(Role.PRODUCTION, 1, RESOURCE, CAPACITY),
         OperationSlot(Role.FINAL, 2, KEEP, CAPACITY)),
        allocate_components=False),          # plating needs a new BOM (architecture.md 4.1)
    "STP": OperationLayout(
        "STP", "{resource} - {material} - {tool}",
        (OperationSlot(Role.PRODUCTION, 2, RESOURCE, details=_LINE_DETAILS),
         OperationSlot(Role.TOOL, 3, TOOL, details=(("op_text", WORK_CENTER_TEXT),) + _LINE_DETAILS),
         OperationSlot(Role.FINAL, 4, KEEP, CAPACITY_X_CAVITY))),
    "MD": OperationLayout(
        "MD", "{resource} - {material} - {tool}",
        (OperationSlot(Role.PRODUCTION, 2, RESOURCE,
                       details=(("op_text", MACHINE_NAME),) + _LINE_DETAILS + (("setup", "one"),)),
         OperationSlot(Role.TOOL, 3, TOOL, details=(("op_text", WORK_CENTER_TEXT),) + _LINE_DETAILS),
         OperationSlot(Role.FINAL, 4, KEEP, CAPACITY_X_CAVITY))),
    "MD_SORTING": OperationLayout(
        "MD_SORTING", "{resource} - {tool} - {sorting}",
        (OperationSlot(Role.PRODUCTION, 2, RESOURCE,
                       details=(("op_text", MACHINE_NAME),) + _LINE_DETAILS + (("setup", "one"),)),
         OperationSlot(Role.TOOL, 3, TOOL, details=(("op_text", WORK_CENTER_TEXT),) + _LINE_DETAILS),
         OperationSlot(Role.SORTING, 4, SORTING, SORTING_CAPACITY),
         OperationSlot(Role.FINAL, 5, KEEP, CAPACITY_X_CAVITY))),
}
