"""What exists in SAP, read from Snowflake or from the SAP screen. Never changed during a run.

Each rule about a routing / production version lives here, once, and is used by the checks, the
planner and the steps (docs/architecture.md 5.5).
"""
from dataclasses import dataclass, field
import re

from routing.model.enums import OperationRole

PRODUCTION_STATUS = "4"         # PLKO-STATU: production / released
PRODUCTION_OPERATION = "0020"
SORTING_PREFIX = "YMHI"
FINAL_CONTROL_KEYS = ("PP94",)  # ZP04 = trial routing, never a final step
VERSION_LIMIT = 5000            # versions >= 5000 are not counted for the next number (UiPath add_production_detail)
VERSION_TEXT_LIMIT = 40         # MKAL-TEXT1


@dataclass(frozen=True)
class RoutingKey:
    material: str               # without leading zeros, e.g. "5013300800"
    group: str                  # PLNNR, e.g. "M5013300"
    counter: str                # PLNAL without leading zeros, e.g. "34"

    def __str__(self):
        return f"{self.group}/{self.counter}"


@dataclass(frozen=True)
class Operation:
    number: str                 # VORNR, e.g. "0020"
    control_key: str = ""       # STEUS, e.g. "PP01"
    work_center: str = ""
    base_quantity: float | None = None

    @property
    def is_sorting(self):
        return self.work_center.upper().startswith(SORTING_PREFIX)


@dataclass(frozen=True)
class Routing:
    key: RoutingKey
    description: str = ""       # KTEXT
    status: str = ""            # STATU: "4" production, "1" inactive
    deleted: bool = False       # DELKZ = X (deletion flag, still in SAP)
    operations: tuple[Operation, ...] = ()

    @property
    def is_trial(self):
        return "TRIAL" in self.description.upper()         # covers MDTRIAL

    @property
    def has_sorting(self):
        """Sorting / lubricant step = an operation with a YMHI work center after 0020 (Snowflake
        operations). Not the name: the description may say YMHI without the step, or the reverse."""
        return self.operation(OperationRole.SORTING) is not None

    def sorting_work_center(self):
        op = self.operation(OperationRole.SORTING)
        return op.work_center if op else ""

    @property
    def can_be_copied(self):
        """Valid copy source for CA01: production status, not flagged, never a trial routing."""
        return self.status == PRODUCTION_STATUS and not self.deleted and not self.is_trial

    def work_centers(self):
        return [op.work_center for op in self.operations]

    def matches(self, resource, *texts):
        """THE rule of checks/routing_condition: `resource` is the work center of one of the
        operations, and every non-blank text (tool, work center, sorting) is in the description."""
        if not resource or resource not in self.work_centers():
            return False
        return all(text in self.description for text in texts if text)

    def operation(self, role):
        """Operation playing `role` (docs/operation_values.md): production = 0020, sorting = YMHI
        after it, final = last PP94 after it (ZP04 = trial, never final). TOOL is a sub-operation, not in Snowflake: None."""
        ops = sorted(self.operations, key=lambda op: op.number)
        production = next((op for op in ops if op.number == PRODUCTION_OPERATION), None)
        if role is OperationRole.PRODUCTION:
            return production
        after = [op for op in ops if production is None or op.number > production.number]
        if role is OperationRole.SORTING:
            return next((op for op in after if op.is_sorting), None)
        if role is OperationRole.FINAL:
            return next((op for op in reversed(after) if op.control_key in FINAL_CONTROL_KEYS), None)
        return None


@dataclass(frozen=True)
class MaterialRoutings:
    """All routings of one material still in SAP (active or deletion-flagged)."""
    material: str
    routings: tuple[Routing, ...] = ()

    def get(self, key):
        return next((r for r in self.routings if r.key == key), None)

    def matching(self, resource, *texts):
        """Routings the row can mean, best first: active before flagged, then newest counter."""
        found = [r for r in self.routings if r.matches(resource, *texts)]
        return sorted(found, key=lambda r: (r.deleted, -_number(r.key.counter)))

    def group_size(self, group):
        return sum(1 for r in self.routings if r.key.group == group)

    def copy_source(self, fits, resource="", needs_sorting=False, sorting=""):
        """Best routing to copy in CA01, or None.
        Must: can_be_copied (status 4, not flagged, not TRIAL) and the same sorting shape as the
        request - a sorting step (YMHI work center after 0020, from the operations, not the name)
        exactly when the request has a Sorting/ Lubricant; otherwise the rows shift.
        Ranked by: fits(routing) (no layout warnings), same resource, same sorting work center, newest."""
        candidates = [r for r in self.routings if r.can_be_copied and r.has_sorting == needs_sorting]
        candidates.sort(key=lambda r: (not fits(r), resource not in r.work_centers(),
                                       bool(sorting) and r.sorting_work_center() != sorting,
                                       -_number(r.key.counter)))
        return candidates[0] if candidates else None


@dataclass(frozen=True)
class ProductionVersion:
    material: str
    version: str                # VERID, e.g. "0004"
    routing: RoutingKey
    alt_bom: int                # STLAL
    text: str = ""              # e.g. "MF50-09 - L501330A B1"
    locked: bool = False

    @staticmethod
    def text_for(routing, alt_bom):
        """'<routing description> B<alt bom>'. Longer than 40 -> drop ' - <material>' once
        ('MF15-13 - 5019400308 - L501940E 03 #03' -> 'MF15-13 - L501940E 03 #03'); still too long
        -> ValueError. # from SAP_automation/change_bom/production_version.py:version_text"""
        description = routing.description.strip()
        text = f"{description} B{alt_bom}"
        material = routing.key.material
        if len(text) > VERSION_TEXT_LIMIT and material and material in description:
            short = re.sub(rf"\s*-\s*{re.escape(material)}", "", description, count=1).strip()
            text = f"{short} B{alt_bom}"
        if len(text) > VERSION_TEXT_LIMIT:
            raise ValueError(f"Production version text longer than {VERSION_TEXT_LIMIT}: '{text}'")
        return text

    def describe(self):
        """'0004 (B1)' / '0004 (B1, locked)'."""
        return f"{self.version} (B{self.alt_bom}{', locked' if self.locked else ''})"


@dataclass(frozen=True)
class MaterialVersions:
    """All production versions of one material still in SAP."""
    material: str
    versions: tuple[ProductionVersion, ...] = field(default_factory=tuple)

    def on(self, key):
        return sorted((v for v in self.versions if v.routing == key), key=lambda v: v.version)

    def has(self, key, alt_bom):
        return any(v.alt_bom == alt_bom for v in self.on(key))

    def missing(self, key, alt_boms):
        return [b for b in alt_boms if not self.has(key, b)]

    def next_number(self):
        """Highest version below 5000 + 1, as '0000'."""
        return next_version_number(v.version for v in self.versions)


def next_version_number(numbers):
    """Highest version number below 5000 + 1, as '0000' ('0001' when none)."""
    values = [int(n) for n in numbers if str(n).isdigit() and int(n) < VERSION_LIMIT]
    return f"{max(values, default=0) + 1:04d}"


def _number(text):
    return int(text) if str(text).isdigit() else 0
