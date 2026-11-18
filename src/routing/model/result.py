from dataclasses import dataclass

from routing.model.enums import Status


@dataclass(frozen=True)
class StepResult:
    status: Status
    message: str = ""

    @classmethod
    def done(cls, message=""):
        return cls(Status.DONE, message)

    @classmethod
    def skipped(cls, message):
        return cls(Status.SKIPPED, message)

    @classmethod
    def failed(cls, message):
        return cls(Status.FAILED, message)

    def cell(self):
        """Text written to the step's result column (RESULT_ROUTING, ...), e.g. 'Done: M5013300/35'."""
        return f"{self.status.value}: {self.message}" if self.message else self.status.value

    @classmethod
    def from_cell(cls, text):
        """Inverse of cell(); None for a blank cell."""
        text = str(text or "").strip()
        if not text or text.lower() == "nan":
            return None
        head, _, message = text.partition(":")
        for status in Status:
            if head.strip().lower() == status.value.lower():
                return cls(status, message.strip())
        return cls(Status.FAILED, text)    # unknown text: treat as not done, run again
