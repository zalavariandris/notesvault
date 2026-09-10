import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from .backup import BackupRepository, MANIFEST, digest, file_digest
from .models import AppError, ExportedNote
from .providers import ICloudProvider, utils


def cached_fetch(repository, provider):
    """Cache is disposable and never bypasses apply()'s local integrity checks."""
    cache_path = repository.root / ".git" / "notesvault-fetch.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if (cache["export_version"] != utils.EXPORT_VERSION
            or cache["account"] != digest(provider.account.strip().lower().encode())
            or cache["manifest"] != file_digest(repository.root / MANIFEST)
            or not isinstance(cache["cursor"], str) or not cache["cursor"]):
            return {}
        manifest = repository.read_manifest()
        previous = [ExportedNote(note_id, {name: repository.path(name) for name in files})
                    for note_id, files in manifest["notes"].items()]
        return {"previous": previous, "previous_cursor": cache["cursor"]}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def save_fetch_cache(repository, snapshot):
    if not snapshot.complete or snapshot.skipped or not snapshot.cursor:
        return
    cache = {"export_version": utils.EXPORT_VERSION,
             "account": digest(snapshot.account.strip().lower().encode()),
             "manifest": file_digest(repository.root / MANIFEST), "cursor": snapshot.cursor}
    path = repository.root / ".git" / "notesvault-fetch.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(cache) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_backup(provider, settings, staging_root: Path, progress: Callable[[str], None]):
    if not settings.backup_folder:
        raise AppError("Choose a backup folder in the Disk card first.")
    repository = BackupRepository(Path(settings.backup_folder))
    staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with repository.locked():
        with TemporaryDirectory(prefix="fetch-", dir=staging_root) as temporary:
            options = cached_fetch(repository, provider) if isinstance(provider, ICloudProvider) else {}
            snapshot = provider.fetch(Path(temporary), progress, **options)
            progress("Saving local Git history…")
            result = repository.apply(snapshot)
            try:
                save_fetch_cache(repository, snapshot)
            except OSError:
                result.warnings.append("Local backup saved; download cache could not be saved. The next fetch may download all notes.")
    return result
