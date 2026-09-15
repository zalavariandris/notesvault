"""UI-independent application operations shared by desktop and terminal adapters.

Adapters own drafts, presentation and event loops. Call operations serially using
TaskManager; controllers own credentials, validation and protected disk writes.
"""
from pathlib import Path

from .backup_controller import fetch_backup
from .config_store import ConfigStoreController
from .disk_vault_controller import DiskVaultController
from .icloud_authentication_controller import ICloudAuthenticationController
from .icloud_notes_provider import ICloudNotesProvider
from .icloud_secret_store import SecretStoreController
from .icloud_errors import ReconnectRequired


class Application:
    def __init__(self, store=None, *, authentication=None, provider_factory=None):
        """Use per-user settings and iCloud unless dependencies are supplied explicitly."""
        self.store = store if store is not None else ConfigStoreController()
        self.authentication = (authentication if authentication is not None else
                               ICloudAuthenticationController(self.store, SecretStoreController()))
        self.provider_factory = provider_factory or ICloudNotesProvider

    @property
    def connected(self):
        return self.authentication.connected

    def prerequisite(self):
        folder = self.store.load().backup_folder
        if not folder or not (Path(folder).expanduser() / ".git").is_dir():
            return "folder"
        return "ready" if self.connected else "login"

    def save_settings(self, folder, interval, *, require_folder=False, download_attachments=None):
        return DiskVaultController.save_configuration(
            self.store, folder, interval, require_folder=require_folder,
            download_attachments=download_attachments)

    def local_note_count(self) -> int:
        folder = self.store.load().backup_folder
        return DiskVaultController(folder).count_notes() if folder else 0

    def fetch(self, progress, control):
        control.checkpoint()
        try:
            provider = self.provider_factory(self.authentication.session, self.authentication.account)
            return fetch_backup(self.store, provider, progress, control=control)
        except ReconnectRequired:
            self.authentication.clear()
            raise
