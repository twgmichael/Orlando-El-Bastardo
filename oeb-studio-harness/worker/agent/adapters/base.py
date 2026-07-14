from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from abc import ABC, abstractmethod


@dataclass
class AdapterResult:
    success: bool
    log_output: str = ""
    error: Optional[str] = None
    artifacts: list[Path] = field(default_factory=list)
    artifact_type: str = "output"
    output_summary: Optional[dict] = None


class Adapter(ABC):
    name: str = ""

    @abstractmethod
    def execute(self, job: dict) -> AdapterResult:
        """Execute the job synchronously. Called from a thread executor."""
        ...

    def can_handle(self, job: dict) -> bool:
        """Return True if this adapter can handle the given job."""
        return False
