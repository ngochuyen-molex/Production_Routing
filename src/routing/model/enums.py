from enum import Enum


class Action(str, Enum):
    CREATE = "Add"                  # the name used in the request files (UiPath "Add")
    DELETE = "Delete"
    ASSIGN = "Assign Components"    # existing routing: allocate unassigned components (UiPath main_bom_assignment)
    # later: CHANGE_CAPACITY, CHANGE_WORK_CENTER, RENAME

    @classmethod
    def parse(cls, value):
        """'Add' / 'add ' / 'Create' -> Action.CREATE; None when unknown."""
        text = str(value or "").strip().lower()
        text = ACTION_ALIASES.get(text, text)
        return next((a for a in cls if a.value.lower() == text), None)


ACTION_ALIASES = {"create": "add"}      # older wording, still accepted


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
