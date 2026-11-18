"""The routing request workbook: read rows, write plan / results in place, save after every row.

openpyxl edits the file in place, so other sheets, columns and formatting are kept.
"""
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from routing.core.excel import clean_path
from routing.model.result import StepResult

PLAN_SHEET = "Plan"
LOG_SHEET = "Run log"
RESULT_PREFIX = "RESULT_"
# One result column per kind of work. A row has one Action, so Add and Delete share a column:
#   RESULT_ROUTING   CA01 create (Add)  /  CA02 deletion flag + status 1 (Delete)
#   RESULT_COMPALLOC CA02 component allocation (Add, Assign Components)
#   RESULT_MM02      MM02 production versions created (Add) / deleted (Delete)
RESULT_COLUMNS = {
    "CreateRouting": "RESULT_ROUTING",
    "InactivateRouting": "RESULT_ROUTING",
    "AllocateComponents": "RESULT_COMPALLOC",
    "CreateProductionVersion": "RESULT_MM02",
    "DeleteProductionVersion": "RESULT_MM02",
}
INPUT_RESULT_COLUMN = "RESULT_INPUT"            # row could not be read (unknown Action, missing Capacity, ...)
KEY_COLUMNS = ("group", "group counter")
COPY_PLANNED_COLUMN = "COPY_FROM_PLANNED"       # written by the planner, information only
# COPY_FROM_GROUP / COPY_FROM_GC are filled only by the user (override), never written here


def result_column(step_name):
    """Column holding a step's result; steps not listed get RESULT_<STEP NAME>."""
    return RESULT_COLUMNS.get(step_name, RESULT_PREFIX + step_name.upper())


class WorkbookLocked(RuntimeError):
    pass


class RequestWorkbook:
    def __init__(self, path, sheet=None):
        self.path = Path(clean_path(path))
        self.book = load_workbook(self.path)
        names = [n for n in self.book.sheetnames if n not in (PLAN_SHEET, LOG_SHEET)]
        self.sheet = self.book[sheet] if sheet else self.book[names[0]]
        self.columns = {}
        for cell in self.sheet[1]:
            if cell.value is not None and str(cell.value).strip():
                self.columns.setdefault(str(cell.value).strip(), cell.column)

    # ---------------------------------------------------------------- read
    def rows(self):
        """[(sheet row number, {column: value}), ...] until the first empty row."""
        result = []
        for number in range(2, self.sheet.max_row + 1):
            values = {name: self.sheet.cell(number, col).value for name, col in self.columns.items()}
            if all(v is None or str(v).strip() == "" for v in values.values()):
                break
            result.append((number, values))
        return result

    def previous_results(self, values, step_names):
        """{step name: StepResult} from the result columns (RESULT_COLUMNS). The old UiPath
        `progress` column is not read."""
        results = {}
        for name in step_names:
            result = StepResult.from_cell(values.get(result_column(name)))
            if result is not None:
                results[name] = result
        return results

    # ---------------------------------------------------------------- write
    def column(self, name):
        if name not in self.columns:
            col = self.sheet.max_column + 1
            self.sheet.cell(1, col, name)
            self.columns[name] = col
        return self.columns[name]

    def write(self, row_number, name, value):
        self.sheet.cell(row_number, self.column(name), value)

    def write_result(self, row, step_name):
        self.write(row.request.excel_row, result_column(step_name), row.results[step_name].cell())
        if row.key is not None:
            self.write(row.request.excel_row, KEY_COLUMNS[0], row.key.group)
            self.write(row.request.excel_row, KEY_COLUMNS[1], row.key.counter)

    def write_plan(self, states, invalid):
        """Plan sheet (replaced each run) + COPY_FROM_PLANNED on the request sheet."""
        if PLAN_SHEET in self.book.sheetnames:
            del self.book[PLAN_SHEET]
        sheet = self.book.create_sheet(PLAN_SHEET)
        sheet.append(["Excel row", "Action", "Dept", "Material", "Resource", "Tool", "Steps", "Layout",
                      "Copy from", "Target routing", "Skip", "Warnings", "Errors",
                      "Components for alt BOM", "New versions for alt BOM", "Existing versions"])
        for row in states:
            r, p = row.request, row.plan
            copy_from = f"{p.copy_from.key} {p.copy_from.description}" if p.copy_from else ""
            sheet.append([
                r.excel_row, r.action.value, r.dept.value, r.material, r.resource, r.tool,
                ", ".join(p.steps), p.layout, copy_from, str(row.key) if row.key else "",
                "; ".join(f"{k}: {v}" for k, v in p.skip.items()),
                "; ".join(p.warnings),
                "; ".join(f"{k}: {v}" for k, v in p.errors.items()),
                ", ".join(f"B{b}" for b in p.component_alt_boms),
                ", ".join(f"B{b}" for b in p.alt_boms),
                ", ".join(v.describe() for v in p.existing_versions)])
            if p.copy_from:
                self.write(r.excel_row, COPY_PLANNED_COLUMN, copy_from)
        for bad in invalid:
            sheet.append([bad.excel_row, "", "", "", "", "", "", "", "", "", "", "", f"input: {bad.message}"])
            self.write(bad.excel_row, INPUT_RESULT_COLUMN, f"Failed: {bad.message}")

    def log(self, row, step_name, result):
        sheet = self.book[LOG_SHEET] if LOG_SHEET in self.book.sheetnames else self._new_log()
        sheet.append([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), row.request.excel_row,
                      row.request.material, step_name, result.status.value, result.message])

    def _new_log(self):
        sheet = self.book.create_sheet(LOG_SHEET)
        sheet.append(["Time", "Excel row", "Material", "Step", "Status", "Message"])
        return sheet

    def save(self):
        try:
            self.book.save(self.path)
        except PermissionError as error:
            raise WorkbookLocked(f"Cannot save {self.path} - close it in Excel. "
                                 f"The run stopped so no SAP work is left unrecorded.") from error
        return self.path
