import json
import os
from dataclasses import asdict
from pathlib import Path

from platformdirs import user_data_path

from .backup_status_store import BackupStatusStore
from .models import AppError
from .models import ConfigModel


class ConfigStoreController:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or user_data_path("NotesVault", appauthor=False)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "settings.json"

    def load(self) -> ConfigModel:
        if not self.path.exists():
            return ConfigModel(
                apple_id=os.getenv("ICLOUD_APPLE_ID", ""),
                backup_folder=os.getenv("LOCAL_EXPORT_DIR", ""),
            )
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            # Discard retired options while preserving existing local backups.
            if isinstance(data, dict):
                data.pop("auth_method", None)
                data.pop("github_repo", None)
                data.pop("last_result", None)
                data.pop("last_backup", None)
            config = ConfigModel(**data)
            if type(config.download_attachments) is not bool:
                raise ValueError()
            if type(config.interval_minutes) is not int or not 0 <= config.interval_minutes <= 10080:
                raise ValueError()
            if any(not isinstance(getattr(config, key), str) for key in (
                "apple_id", "backup_folder"
            )):
                raise ValueError()
            return config
        except (ValueError, TypeError) as exc:
            raise AppError("Settings are invalid. Rename settings.json in the app data folder and restart.") from exc

    def save(self, settings: ConfigModel) -> None:
        BackupStatusStore(self.directory).migrate()
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
