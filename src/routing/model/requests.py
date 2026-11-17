"""What the user asks: one Request per Excel row = common part + the params of its action.

"params" = the extra input one action needs (CreateParams: capacity, cavity, eff, util, sorting,
alt BOM). Not related to the OpCenter / TPM "Spec" column.
"""
from dataclasses import dataclass

import pandas as pd

from routing.core.clean import clean_string, clean_tool
from routing.model.entities import RoutingKey
from routing.model.enums import Action, Dept

ALL_BOM = "ALL BOM"


class InputError(ValueError):
    """A row that cannot be turned into a request; the message is written to the row."""


@dataclass(frozen=True)
class AltBomChoice:
    """'ALL BOM' -> all=True; '2' -> number=2."""
    all: bool = False
    number: int | None = None

    @classmethod
    def parse(cls, value):
        text = clean_string(value).upper()
        if text == ALL_BOM:
            return cls(all=True)
        if not text:
            return cls(number=1)
        digits = text.removeprefix("B").lstrip("0") or "0"
        if not digits.isdigit() or int(digits) == 0:
            raise InputError(f"Alt Bom '{value}' is not a number or ALL BOM")
        return cls(number=int(digits))

    def __str__(self):
        return ALL_BOM if self.all else str(self.number)


@dataclass(frozen=True)
class CreateParams:
    capacity: float
    tool_cavity: int | None = None
    efficiency: float | None = None
    utilization: float | None = None
    sorting: str = ""                   # sorting / lubricant work center, e.g. "YMHI-1"
    sorting_capacity: float | None = None
    alt_bom: AltBomChoice = AltBomChoice(number=1)
    assign_components: bool = True

    @property
    def capacity_x_cavity(self):
        return self.capacity * (self.tool_cavity or 1)


@dataclass(frozen=True)
class DeleteParams:
    """The routing is identified by material / resource / tool or the given key."""


@dataclass(frozen=True)
class Request:
    excel_row: int                      # sheet row number (header = 1), e.g. 2 for the first data row
    action: Action
    dept: Dept
    material: str
    resource: str
    tool: str = ""
    key: RoutingKey | None = None       # group / group counter given in the file
    copy_from: RoutingKey | None = None # Create: COPY_FROM_GROUP / COPY_FROM_GC override in the file
    params: CreateParams | DeleteParams | None = None


# ============================================================
# Excel row -> Request
# ============================================================
def _text(values, column):
    return clean_string(values.get(column))


def _number(values, column, required=False, label=None):
    raw = values.get(column)
    number = pd.to_numeric(raw, errors="coerce") if raw is not None else float("nan")
    if pd.isna(number):
        if required:
            raise InputError(f"{label or column} missing")
        return None
    return float(number)


def _yes(values, column, default=True):
    text = _text(values, column).lower()
    if not text:
        return default
    return text not in ("no", "n", "0", "false")


def read_create_params(values):
    cavity = _number(values, "Tool Cavity")
    sorting = clean_tool(values.get("Sorting/ Lubricant"))
    sorting_capacity = _number(values, "Sorting/ Lubricant Capacity")
    if sorting and sorting_capacity is None:
        raise InputError("Sorting/ Lubricant Capacity missing")
    return CreateParams(
        capacity=_number(values, "Capacity", required=True),
        tool_cavity=int(cavity) if cavity else None,
        efficiency=_number(values, "Efficiency"),
        utilization=_number(values, "Utilization"),
        sorting=sorting,
        sorting_capacity=sorting_capacity,
        alt_bom=AltBomChoice.parse(values.get("Alt Bom")),
        assign_components=_yes(values, "Assign Components"),
    )


def read_delete_params(values):
    return DeleteParams()


PARAM_READERS = {Action.CREATE: read_create_params, Action.DELETE: read_delete_params}


def request_from_row(excel_row, values):
    """values = one Excel row as a dict (column name -> value). Raises InputError."""
    action = Action.parse(values.get("Action"))
    if action is None:
        raise InputError(f"Action '{_text(values, 'Action')}' unknown (use {', '.join(a.value for a in Action)})")
    dept = Dept.parse(values.get("Dept"))
    if dept is None:
        raise InputError(f"Dept '{_text(values, 'Dept')}' unknown (use {', '.join(d.value for d in Dept)})")
    material = _text(values, "Material")
    resource = _text(values, "Resource")
    if not material or not resource:
        raise InputError("Material or Resource missing")

    group = _text(values, "group")
    counter = _text(values, "group counter").lstrip("0")
    key = RoutingKey(material, group, counter) if group and counter else None
    copy_group = _text(values, "COPY_FROM_GROUP")
    copy_counter = _text(values, "COPY_FROM_GC").lstrip("0")
    copy_from = RoutingKey(material, copy_group, copy_counter) if copy_group and copy_counter else None

    return Request(excel_row=excel_row, action=action, dept=dept, material=material,
                   resource=resource, tool=clean_tool(values.get("Tool")), key=key,
                   copy_from=copy_from, params=PARAM_READERS[action](values))
