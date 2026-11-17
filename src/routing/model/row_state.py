"""What flows through the phases for one Excel row."""
from dataclasses import dataclass, field

from routing.model.entities import ProductionVersion, Routing, RoutingKey
from routing.model.enums import Status
from routing.model.requests import Request
from routing.model.result import StepResult


@dataclass
class Plan:
    """Decided before SAP is touched (Snowflake only)."""
    steps: list[str] = field(default_factory=list)
    layout: str = ""                                   # layout id, e.g. "MD_SORTING"
    copy_from: Routing | None = None                   # create: routing of the same material to copy
    target: Routing | None = None                      # the routing the row works on (existing or just created)
    alt_boms: list[int] = field(default_factory=list)  # pv phase: alt BOMs that still need a version
    component_alt_boms: list[int] = field(default_factory=list)   # components phase: alt BOMs to allocate
    existing_versions: list[ProductionVersion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skip: dict[str, str] = field(default_factory=dict)  # step name -> reason: written as Skipped, not run
    errors: dict[str, str] = field(default_factory=dict)  # step name -> planning error: Failed, retried next run


@dataclass
class RowState:
    request: Request
    plan: Plan = field(default_factory=Plan)
    key: RoutingKey | None = None                      # target routing: file, Snowflake or SAP screen
    results: dict[str, StepResult] = field(default_factory=dict)   # step name -> result

    def __post_init__(self):
        if self.key is None:
            self.key = self.request.key

    def done(self, step_name):
        result = self.results.get(step_name)
        return result is not None and result.status in (Status.DONE, Status.SKIPPED)

    def has_failed(self):
        return any(r.status is Status.FAILED for r in self.results.values())


@dataclass
class InvalidRow:
    """Excel row that could not be read; reported, never run."""
    excel_row: int
    message: str
