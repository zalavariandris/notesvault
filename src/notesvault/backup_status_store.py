"""Persist the last backup result separately from user preferences."""
import json
from dataclasses import asdict
from pathlib import Path

from .models import AppError, BackupStatusModel


class BackupStatusStore:
    def __init__(self, directory: Path):
        self.path = directory / "backup-status.json"
        self.legacy_path = directory / "settings.json"

    def load(self) -> BackupStatusModel:
        source = self.path if self.path.exists() else self.legacy_path
        if not source.exists():
            return BackupStatusModel()
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
            status = BackupStatusModel(**{
                key: data[key] for key in ("last_backup", "last_result") if key in data
            })
            if not isinstance(data, dict) or not all(isinstance(value, str) for value in asdict(status).values()):
                raise ValueError()
            return BackupStatusModel(status.last_backup, "\n".join(
                line for line in status.last_result.splitlines() if not line.startswith("GitHub:")
            ))
        except (ValueError, TypeError) as exc:
            raise AppError("Backup status is invalid. Rename backup-status.json in the app data folder and restart.") from exc

    def save(self, status: BackupStatusModel) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(status), indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def migrate(self) -> None:
        # Save legacy results before a preferences save removes the retired fields.
        if not self.path.exists() and self.legacy_path.exists():
            self.save(self.load())
