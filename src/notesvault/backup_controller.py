"""Orchestrate retrieval, protected local saves, and backup results."""
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import nullcontext
from typing import Callable

from .fetch_cache import FetchCache
from .backup_status_store import BackupStatusStore
from .config_store import ConfigStoreController
from .demo_provider import DemoProvider
from .fetch_control import FetchControl
from .disk_vault_controller import DiskVaultController
from .icloud_notes_provider import ICloudNotesProvider
from .models import BackupResultModel, BackupStatusModel


class BackupController:
    def __init__(self, folder: str | Path):
        self.vault = DiskVaultController(folder)

    def run_backup(self, provider: ICloudNotesProvider | DemoProvider, progress: Callable[[str], None], *,
                   control: FetchControl | None = None,
                   download_attachments: bool = False) -> BackupResultModel:
        control = control or FetchControl()
        control.checkpoint()
        with self.vault.locked():
            control.checkpoint()
            cache = FetchCache(self.vault)
            downloads = (TemporaryDirectory(prefix="notes-downloads-", dir=self.vault.root / ".git")
                         if download_attachments else nullcontext(None))
            with downloads as temporary:
                options = cache.load(provider.account, download_attachments)
                snapshot = provider.fetch(Path(temporary) if temporary else None, progress, control=control,
                                          download_attachments=download_attachments, **options)
                control.begin_save()
                progress("Saving local Git history…")
                result = self.vault.apply(snapshot)
                try:
                    cache.save(snapshot, download_attachments)
                except OSError:
                    result.warnings.append("Local backup saved; download cache could not be saved. The next fetch may download all notes.")
        return result


def fetch_backup(store: ConfigStoreController, provider, progress, *,
                 control: FetchControl | None = None) -> tuple[BackupStatusModel, BackupResultModel]:
    """Shared GUI/CLI workflow; preferences are never used as runtime state."""
    config = store.load()
    result = BackupController(config.backup_folder).run_backup(
        provider, progress, control=control,
        download_attachments=config.download_attachments)
    status = BackupStatusModel(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), result.summary())
    try:
        BackupStatusStore(store.directory).save(status)
    except OSError:
        result.warnings.append("Local backup saved; the last backup status could not be saved.")
    return status, result
