import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_data_path

from .models import AppError


@dataclass
class Settings:
    apple_id: str = ""
    auth_method: str = "password"
    backup_folder: str = ""
    github_repo: str = ""
    interval_minutes: int = 30
    last_result: str = "No backups yet"
    last_backup: str = "Never"


class ConfigStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or user_data_path("NotesVault", appauthor=False)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "settings.json"

    def load(self) -> Settings:
        if not self.path.exists():
            owner, repo = os.getenv("GITHUB_REPO_OWNER", ""), os.getenv("GITHUB_REPO_NAME", "")
            return Settings(
                apple_id=os.getenv("ICLOUD_APPLE_ID", ""),
                backup_folder=os.getenv("LOCAL_EXPORT_DIR", ""),
                github_repo=f"{owner}/{repo}" if owner and repo else "",
            )
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            settings = Settings(**data)
            if not isinstance(settings.interval_minutes, int) or not 0 <= settings.interval_minutes <= 10080:
                raise ValueError()
            if any(not isinstance(getattr(settings, key), str) for key in (
                "apple_id", "backup_folder", "github_repo", "last_result", "last_backup"
            )):
                raise ValueError()
            if settings.auth_method not in {"password", "browser"}:
                raise ValueError()
            return settings
        except (ValueError, TypeError) as exc:
            raise AppError("Settings are invalid. Rename settings.json in the app data folder and restart.") from exc

    def save(self, settings: Settings) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


class SecretStore:
    """Use only an OS-backed keyring, never pyicloud's plaintext fallback."""

    def __init__(self):
        self._backend = None

    def backend(self):
        if self._backend is None:
            import sys
            if sys.platform == "win32":
                from keyring.backends.Windows import WinVaultKeyring
                self._backend = WinVaultKeyring()
            elif sys.platform == "darwin":
                from keyring.backends.macOS import Keyring
                self._backend = Keyring()
            else:
                from keyring.backends.SecretService import Keyring
                self._backend = Keyring()
        return self._backend

    def get(self, name: str) -> str | None:
        try:
            return self.backend().get_password("NotesVault", name)
        except Exception as exc:
            raise AppError("OS credential storage is unavailable. Unlock or configure your credential store.") from exc

    def set(self, name: str, value: str) -> None:
        try:
            self.backend().set_password("NotesVault", name, value)
        except Exception as exc:
            raise AppError("Could not save the credential in the OS credential store.") from exc

    def delete(self, name: str) -> None:
        if self.get(name) is not None:
            try:
                self.backend().delete_password("NotesVault", name)
            except Exception as exc:
                raise AppError("Could not remove the saved credential.") from exc
