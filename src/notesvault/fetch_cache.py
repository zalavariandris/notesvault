"""Disposable fetch cursors, bound to account, export options, and committed manifest."""
import json

from . import provider_utils
from .disk_vault_controller import DiskVaultController, MANIFEST, digest, file_digest
from .models import ExportedNoteModel


class FetchCache:
    def __init__(self, vault: DiskVaultController):
        self.vault = vault

    def load(self, account: str, download_attachments: bool):
        """Cache is disposable and never bypasses apply()'s local integrity checks."""
        cache_path = self.vault.root / ".git" / "notesvault-fetch.json"
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            if (cache["export_version"] != provider_utils.EXPORT_VERSION
                or cache.get("download_attachments") is not download_attachments
                or cache["account"] != digest(account.strip().lower().encode())
                or cache["manifest"] != file_digest(self.vault.root / MANIFEST)
                or not isinstance(cache["cursor"], str) or not cache["cursor"]):
                return {}
            manifest = self.vault.read_manifest()
            previous = [ExportedNoteModel(note_id, {name: self.vault.path(name) for name in files})
                        for note_id, files in manifest["notes"].items()]
            return {"previous": previous, "previous_cursor": cache["cursor"]}
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def save(self, snapshot, download_attachments):
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

