"""UI-independent application operations shared by desktop and terminal adapters.

Adapters own drafts, presentation and event loops. Call operations serially using
TaskManager; controllers own credentials, validation and protected disk writes.
"""
from pathlib import Path

from .backup_controller import fetch_backup
from .demo_provider import DemoProvider
from .disk_vault_controller import DiskVaultController
from .icloud_authentication_controller import ICloudAuthenticationController
from .icloud_notes_provider import ICloudNotesProvider
from .icloud_secret_store import SecretStoreController
from .icloud_errors import ReconnectRequired


class Application:
    def __init__(self, store, *, is_demo=False, authentication=None):
        self.store = store
        self.is_demo = is_demo
        self.authentication = authentication or ICloudAuthenticationController(store, SecretStoreController())

    @property
    def connected(self):
        return self.is_demo or self.authentication.connected

    def prerequisite(self):
        folder = self.store.load().backup_folder
        if not folder or not (Path(folder).expanduser() / ".git").is_dir():
            return "folder"
        return "ready" if self.connected else "login"

    def save_settings(self, folder, interval, *, require_folder=False, download_attachments=None):
        return DiskVaultController.save_configuration(
            self.store, folder, interval, require_folder=require_folder,
            download_attachments=download_attachments)

    def fetch(self, progress, control):
        control.checkpoint()
        try:
            provider = (DemoProvider() if self.is_demo else
                        ICloudNotesProvider(self.authentication.session, self.authentication.account))
            return fetch_backup(self.store, provider, progress, control=control)
        except ReconnectRequired:
            self.authentication.clear()
            raise
