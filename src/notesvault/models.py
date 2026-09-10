from dataclasses import dataclass, field
from pathlib import Path

class AppError(Exception):
    """A safe, actionable message that may be shown in the UI."""


@dataclass
class ExportedNoteModel:
    note_id: str
    # Relative vault paths map to rendered bytes, downloaded assets, or reused exports.
    files: dict[str, bytes | Path]


@dataclass
class SnapshotModel:
    account: str
    notes: list[ExportedNoteModel]
    complete: bool = True
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    cursor: str | None = None
    # Providers with limited zone coverage must delete only explicit tombstones.
    deleted_ids: set[str] | None = None


@dataclass
class BackupResultModel:
    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    commit: str = "No changes"
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.added} added | {self.updated} updated | "
                f"{self.deleted} deleted | {self.skipped} skipped\nLocal Git: {self.commit}")


@dataclass(frozen=True)
class ConfigModel:
    apple_id: str = ""
    backup_folder: str = ""
    interval_minutes: int = 30
    download_attachments: bool = False


@dataclass(frozen=True)
class BackupStatusModel:
    last_backup: str = "Never"
    last_result: str = "No backup yet"
