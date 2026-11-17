"""`routing run`: plan every row (Snowflake), then run the steps phase by phase (docs/architecture.md 6.7)."""
from dataclasses import dataclass, field

from routing.model.enums import PHASES, Action
from routing.model.requests import InputError, request_from_row
from routing.model.result import StepResult
from routing.model.row_state import InvalidRow, RowState
from routing.pipelines import recipes as recipe_book
from routing.pipelines.workbook import RequestWorkbook
from routing.steps.base import Context


@dataclass
class RunSummary:
    path: str = ""
    planned: int = 0
    invalid: int = 0
    counts: dict = field(default_factory=dict)          # "Done" / "Skipped" / "Failed" / "Not run" -> n

    def add(self, status):
        self.counts[status] = self.counts.get(status, 0) + 1

    def __str__(self):
        parts = ", ".join(f"{k}: {v}" for k, v in sorted(self.counts.items())) or "no steps run"
        return f"{self.planned} rows planned, {self.invalid} invalid. Steps - {parts}. Saved to: {self.path}"


def parse_rows(rows, only=None, row_numbers=None):
    """[(row number, values)] -> RowState list + InvalidRow list."""
    states, invalid = [], []
    for number, values in rows:
        if row_numbers and number not in row_numbers:
            continue
        try:
            request = request_from_row(number, values)
        except InputError as error:
            invalid.append(InvalidRow(number, str(error)))
            continue
        if only and request.action is not only:
            continue
        states.append(RowState(request=request))
    states.sort(key=lambda s: s.request.action is not Action.DELETE)     # deletes first, stable
    return states, invalid


def plan_rows(states, ctx, phases=PHASES, recipes=recipe_book.RECIPES):
    ctx.load_routings([s.request.material for s in states])
    for row in states:
        steps = recipe_book.steps_for(row, phases, recipes)
        row.plan.steps = [s.name for s in steps]
        for step in steps:
            if row.done(step.name):
                continue
            try:
                step.plan(row, ctx)
            except Exception as error:          # never stop the whole plan for one row
                row.plan.errors[step.name] = f"planning failed: {error}"


def safe_run(step, row, ctx):
    try:
        return step.run(row, ctx)
    except Exception as error:
        message = str(error) or type(error).__name__
        if ctx._sap is not None:
            try:
                ctx.sap.reset()                 # leave SAP without saving, next row starts clean
            except Exception as reset_error:
                message += f" (SAP reset failed: {reset_error})"
        return StepResult.failed(message)


def execute(states, book, ctx, summary, phases=PHASES, recipes=recipe_book.RECIPES):
    for phase in PHASES:
        if phase not in phases:
            continue
        for row in states:
            changed = False
            for step in recipe_book.steps_for(row, [phase], recipes):
                if row.done(step.name):
                    continue
                if step.name in row.plan.skip:
                    result = StepResult.skipped(row.plan.skip[step.name])
                elif step.name in row.plan.errors:
                    result = StepResult.failed(row.plan.errors[step.name])
                elif recipe_book.earlier_failed(row, step, recipes):
                    summary.add("Not run")
                    continue
                else:
                    print(f"Row {row.request.excel_row} {row.request.material}: {step.name} ...")
                    result = safe_run(step, row, ctx)
                    print(f"  -> {result.cell()}")
                row.results[step.name] = result
                book.write_result(row, step.name)
                book.log(row, step.name, result)
                summary.add(result.status.value)
                changed = True
            if changed:
                book.save()                     # after every row


def run(path, phases=PHASES, only=None, rows=None, dry_run=False, slow=False, sheet=None,
        ctx=None, recipes=recipe_book.RECIPES):
    book = RequestWorkbook(path, sheet=sheet)
    step_names = [s.name for s in recipe_book.all_steps(recipes)]
    states, invalid = parse_rows(book.rows(), only=only, row_numbers=rows)
    values_by_row = dict(book.rows())
    for row in states:
        row.results = book.previous_results(values_by_row[row.request.excel_row], step_names)

    own_ctx = ctx is None
    ctx = ctx or Context(dry_run=dry_run, slow=slow)
    summary = RunSummary(planned=len(states), invalid=len(invalid))
    try:
        plan_rows(states, ctx, phases, recipes)
        book.write_plan(states, invalid)
        if not dry_run:
            execute(states, book, ctx, summary, phases, recipes)
        summary.path = str(book.save())
    finally:
        if own_ctx:
            ctx.close()
    print(summary)
    return summary
