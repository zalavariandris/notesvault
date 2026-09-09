from dataclasses import dataclass, field
from pathlib import Path


class AppError(Exception):
    """A safe, actionable message that may be shown in the UI."""


@dataclass
class ExportedNote:
    id: str
    # Paths are relative to the backup root; values point to staged files.
    files: dict[str, Path]


@dataclass
class Snapshot:
    account: str
    notes: list[ExportedNote]
    complete: bool = True
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class BackupResult:
    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    commit: str = "No changes"
    push: str = "Not configured"
    warnings: list[str] = field(default_factory=list)
