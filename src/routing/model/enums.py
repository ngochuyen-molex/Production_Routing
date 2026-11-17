from enum import Enum


class Action(str, Enum):
    CREATE = "Create"
    DELETE = "Delete"
    # later: CHANGE_CAPACITY, CHANGE_WORK_CENTER, RENAME

    @classmethod
    def parse(cls, value):
        """'create' / 'CREATE ' -> Action.CREATE; None when unknown."""
        text = str(value or "").strip().lower()
        return next((a for a in cls if a.value.lower() == text), None)


class Dept(str, Enum):
    MD = "MD"
    AS = "AS"
    PLT = "PLT"
    STP = "STP"

    @classmethod
    def parse(cls, value):
        text = str(value or "").strip().upper()
        return next((d for d in cls if d.value == text), None)


class OperationRole(str, Enum):
    """Same vocabulary as checks/operation_values.py."""
    PRODUCTION = "production"
    TOOL = "tool"
    SORTING = "sorting"
    FINAL = "final"


class Status(str, Enum):
    DONE = "Done"
    SKIPPED = "Skipped"
    FAILED = "Failed"


# Phases always run in this order (docs/architecture.md 1)
PHASES = ("routing", "components", "pv", "opc")
