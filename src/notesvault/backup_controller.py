"""Orchestrate retrieval, staging, cursor caching, and local backup results."""
import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from . import provider_utils
from .backup_status_store import BackupStatusStore
from .config_store import ConfigStoreController
from .demo_provider import DemoProvider
from .fetch_control import FetchControl
from .disk_vault_controller import DiskVaultController, MANIFEST, digest, file_digest
from .icloud_notes_provider import ICloudNotesProvider
from .models import BackupResultModel, BackupStatusModel, ExportedNoteModel


class BackupController:
    def __init__(self, folder: str | Path):
        self.vault = DiskVaultController(folder)

    def _cached_fetch(self, provider: ICloudNotesProvider, download_attachments: bool):
        """Cache is disposable and never bypasses apply()'s local integrity checks."""
        cache_path = self.vault.root / ".git" / "notesvault-fetch.json"
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            if (cache["export_version"] != provider_utils.EXPORT_VERSION
                or cache.get("download_attachments") is not download_attachments
                or cache["account"] != digest(provider.account.strip().lower().encode())
                or cache["manifest"] != file_digest(self.vault.root / MANIFEST)
                or not isinstance(cache["cursor"], str) or not cache["cursor"]):
                return {}
            manifest = self.vault.read_manifest()
            previous = [ExportedNoteModel(note_id, {name: self.vault.path(name) for name in files})
                        for note_id, files in manifest["notes"].items()]
            return {"previous": previous, "previous_cursor": cache["cursor"]}
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def _save_fetch_cache(self, snapshot, download_attachments):
        if not snapshot.complete or snapshot.skipped or not snapshot.cursor:
            return
        cache = {"export_version": provider_utils.EXPORT_VERSION,
                 "download_attachments": download_attachments,
                 "account": digest(snapshot.account.strip().lower().encode()),
                 "manifest": file_digest(self.vault.root / MANIFEST), "cursor": snapshot.cursor}
        path = self.vault.root / ".git" / "notesvault-fetch.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(cache) + "\n", encoding="utf-8")
        temporary.replace(path)

    def run_backup(self, provider: ICloudNotesProvider | DemoProvider, staging_root: Path,
                   progress: Callable[[str], None], *, control: FetchControl | None = None,
                   download_attachments: bool = False) -> BackupResultModel:
        control = control or FetchControl()
        control.checkpoint()
        staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.vault.locked():
            control.checkpoint()
            with TemporaryDirectory(prefix="fetch-", dir=staging_root) as temporary:
                options = self._cached_fetch(provider, download_attachments) if isinstance(provider, ICloudNotesProvider) else {}
                snapshot = provider.fetch(Path(temporary), progress, control=control,
                                          download_attachments=download_attachments, **options)
                control.begin_save()
                progress("Saving local Git history…")
                result = self.vault.apply(snapshot)
                try:
                    self._save_fetch_cache(snapshot, download_attachments)
                except OSError:
                    result.warnings.append("Local backup saved; download cache could not be saved. The next fetch may download all notes.")
        return result


def fetch_backup(store: ConfigStoreController, provider, progress, *,
                 control: FetchControl | None = None) -> tuple[BackupStatusModel, BackupResultModel]:
    """Shared GUI/CLI workflow; preferences are never used as runtime state."""
    config = store.load()
    result = BackupController(config.backup_folder).run_backup(
        provider, store.directory / "staging", progress, control=control,
        download_attachments=config.download_attachments)
    status = BackupStatusModel(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), result.summary())
    try:
        BackupStatusStore(store.directory).save(status)
    except OSError:
        result.warnings.append("Local backup saved; the last backup status could not be saved.")
    return status, result
