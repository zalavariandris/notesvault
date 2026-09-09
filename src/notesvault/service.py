from pathlib import Path
from tempfile import TemporaryDirectory

from .backup import BackupRepository
from .github import push_repository
from .models import AppError


def run_backup(provider, settings, secret_store, staging_root: Path, progress):
    if not settings.backup_folder:
        raise AppError("Choose a backup folder in Settings first.")
    repository = BackupRepository(Path(settings.backup_folder))
    staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with repository.locked():
        with TemporaryDirectory(prefix="fetch-", dir=staging_root) as temporary:
            snapshot = provider.fetch(Path(temporary), progress)
            progress("Saving local Git history…")
            result = repository.apply(snapshot)
        if settings.github_repo:
            progress("Publishing to GitHub…")
            try:
                token = secret_store.get("github")
                if not token:
                    raise AppError("GitHub token is missing. Reconnect in Settings.")
                result.push = push_repository(repository.root, settings.github_repo, token)
            except AppError as exc:
                result.push = str(exc)
    return result
