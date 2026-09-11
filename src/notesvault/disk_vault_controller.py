"""Configure the vault and maintain safe local files and Git history."""
import hashlib
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from tempfile import mkdtemp

from filelock import FileLock, Timeout

from .models import AppError, BackupResultModel, SnapshotModel

MANIFEST = ".apple-notes-manifest.json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path, git_algorithm: str | None = None) -> str:
    checksum = hashlib.new(git_algorithm or "sha256")
    if git_algorithm:
        checksum.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            checksum.update(chunk)
    return checksum.hexdigest()


def git(root: Path, *args: str, input: bytes | None = None, check=True):
    env = os.environ.copy()
    # Do not inherit Git routing variables from a developer's shell.
    for key in list(env):
        if key.startswith("GIT_"):
            del env[key]
    env.update(GIT_TERMINAL_PROMPT="0", GIT_LITERAL_PATHSPECS="1")
    try:
        result = subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.hooksPath=",
                                 "-C", str(root), *args], input=input,
                                capture_output=True, env=env, timeout=120,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except FileNotFoundError as exc:
        raise AppError("Git is not installed or is not on PATH. Install Git and restart the app.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AppError("Git timed out. Check the backup repository before retrying.") from exc
    if check and result.returncode:
        raise AppError("Git could not complete the operation. Check repository permissions, locks, and conflicts.")
    return result


class DiskVaultController:
    @staticmethod
    def save_configuration(store, folder: str, interval: str, *, require_folder=False,
                           download_attachments: bool | None = None):
        """Validate drafts and prepare the repository before saving preferences."""
        settings = store.load()
        try:
            minutes = int(interval)
            if not 0 <= minutes <= 10080:
                raise ValueError()
        except ValueError:
            raise AppError("Enter an interval from 0 to 10080 minutes.") from None
        path = Path(folder.strip()).expanduser().absolute() if folder.strip() else None
        if not path and settings.backup_folder:
            raise AppError("Choose a backup folder before replacing the current location.")
        if not path and require_folder:
            raise AppError("Choose a backup folder to continue the fetch.")
        if path:
            DiskVaultController(path).initialize()
        if download_attachments is not None and type(download_attachments) is not bool:
            raise AppError("Choose whether to download attachments.")
        updated = replace(settings, backup_folder=str(path) if path else "", interval_minutes=minutes,
                          download_attachments=settings.download_attachments if download_attachments is None else download_attachments)
        if updated != settings:
            store.save(updated)
        return store.load()

    def __init__(self, folder: str | Path):
        if not str(folder).strip():
            raise AppError("Choose a backup folder in settings first.")
        self.root = Path(folder).expanduser().absolute()

    def initialize(self):
        if self.root.is_symlink() or self.root.resolve() != self.root:
            raise AppError("Choose a backup folder without symbolic links or junctions.")
        if (self.root / "pyproject.toml").exists() or (self.root / "AGENTS.md").exists():
            raise AppError("Choose a separate backup folder, not the application's source folder.")
        self.root.mkdir(parents=True, exist_ok=True)
        if not (self.root / ".git").exists():
            if git(self.root, "rev-parse", "--show-toplevel", check=False).returncode == 0:
                raise AppError("This folder is inside another Git repository. Choose a separate backup location.")
            git(self.root, "init", "--initial-branch=main")
        if not (self.root / ".git").is_dir() or (self.root / ".git").resolve() != self.root / ".git":
            raise AppError("Choose a standalone Git repository, not a linked worktree.")
        actual = Path(git(self.root, "rev-parse", "--show-toplevel").stdout.decode().strip()).resolve()
        if actual != self.root.resolve():
            raise AppError("The backup folder must be the Git repository root.")

    @contextmanager
    def locked(self):
        self.initialize()
        try:
            with FileLock(self.root / ".git" / "notesvault.lock", timeout=0):
                if (self.root / ".git" / "notesvault-save.json").exists():
                    raise AppError("An interrupted local save needs recovery. Existing recovery copies were retained. "
                                   "See README's interrupted-save recovery instructions before fetching again.")
                yield self
        except Timeout as exc:
            raise AppError("Another backup is running for this folder.") from exc

    def path(self, relative: str) -> Path:
        """Return the absolute path to a file in the backup, ensuring it is safe."""
        posix = PurePosixPath(relative)
        if (not posix.parts or "\\" in relative or ":" in relative or posix.is_absolute()
            or any(p in (".", "..", ".git") for p in posix.parts)
            or (relative != MANIFEST and posix.parts[0] not in ("notes", "attachments"))):
            raise AppError("Unsafe path in backup data; no files were changed.")
        target = self.root / relative
        if not target.resolve().is_relative_to(self.root.resolve()) or target.resolve() != target.absolute():
            raise AppError("Backup paths must not contain links or junctions.")
        return target

    def read_manifest(self)->dict:
        """
        Read and return the backup manifest as a dictionary.
        """
        
        target = self.path(MANIFEST)
        if not target.exists():
            return {"version": 1, "account": None, "notes": {}}
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            if data["version"] != 1 or not isinstance(data["notes"], dict):
                raise ValueError()
            seen = set()
            for files in data["notes"].values():
                if not isinstance(files, dict):
                    raise ValueError()
                for name, checksum in files.items():
                    self.path(name)
                    if name == MANIFEST or name.casefold() in seen or not isinstance(checksum, str):
                        raise ValueError()
                    seen.add(name.casefold())
            return data
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise AppError("The backup manifest is invalid. Restore it from Git history before fetching.") from exc

    def _validate_existing(self, account: str) -> dict:
        """Reject unsafe repository state before planning any changes."""
        old = self.read_manifest()
        if old["account"] not in (None, account):
            raise AppError("This backup belongs to another iCloud account. Choose another folder.")
        if git(self.root, "diff", "--cached", "--quiet", check=False).returncode:
            raise AppError("The repository has staged changes. Commit or unstage them before fetching.")
        if any((self.root / ".git" / name).exists() for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "rebase-merge", "rebase-apply")):
            raise AppError("Finish the repository's merge or rebase before fetching.")
        old_files = {name: checksum for files in old["notes"].values() for name, checksum in files.items()}
        for name, checksum in old_files.items():
            path = self.path(name)
            if not path.is_file() or file_digest(path) != checksum:
                raise AppError("A backed-up file was edited or removed locally. Preserve or restore your edits before fetching.")
        tracked = {}
        tree = git(self.root, "ls-tree", "-r", "-z", "HEAD", check=False)
        if tree.returncode == 0:
            for entry in tree.stdout.split(b"\0"):
                if entry:
                    header, name = entry.split(b"\t", 1)
                    mode, kind, oid = header.split()
                    tracked[name.decode("utf-8")] = (mode, oid.decode())
        for name in [*old_files, *([MANIFEST] if self.path(MANIFEST).exists() else [])]:
            # Existing exports must have a durable committed version before replacement.
            mode, oid = tracked.get(name, (b"", ""))
            if mode not in (b"100644", b"100755") or file_digest(self.path(name), "sha256" if len(oid) == 64 else "sha1") != oid:
                raise AppError("Backup files have uncommitted changes. Commit or restore them before fetching.")

        return old

    def _plan_snapshot(self, snapshot: SnapshotModel, old: dict, account: str):
        """Calculate managed changes without writing exports or altering Git."""
        old_files = {name: checksum for files in old["notes"].values() for name, checksum in files.items()}

        result = BackupResultModel(skipped=snapshot.skipped, warnings=list(snapshot.warnings))
        can_delete = snapshot.complete and not snapshot.skipped
        new_notes = {} if can_delete and snapshot.deleted_ids is None else dict(old["notes"])
        if can_delete and snapshot.deleted_ids is not None:
            for note_id in snapshot.deleted_ids:
                new_notes.pop(note_id, None)
        sources = {}
        ids = set()
        paths = set()
        for note in snapshot.notes:
            if note.note_id in ids:
                raise AppError("The source returned duplicate note identifiers. Backup was not changed.")
            ids.add(note.note_id)
            file_hashes = {}
            if not note.files:
                raise AppError("An empty note export was rejected.")
            for name, source in note.files.items():
                self.path(name)
                if name == MANIFEST or name.casefold() in paths:
                    raise AppError("Note filenames collide. Backup was not changed.")
                paths.add(name.casefold())
                sources[name] = source
                file_hashes[name] = digest(source) if isinstance(source, bytes) else file_digest(source)
            new_notes[note.note_id] = file_hashes
            if note.note_id not in old["notes"]:
                result.added += 1
            elif file_hashes != old["notes"][note.note_id]:
                result.updated += 1
        result.deleted = len(set(old["notes"]) - set(new_notes))
        all_paths = [name.casefold() for files in new_notes.values() for name in files]
        if len(all_paths) != len(set(all_paths)):
            raise AppError("Note filenames collide with retained backups.")
        new_files = {name: checksum for files in new_notes.values() for name, checksum in files.items()}
        for name in new_files.keys() - old_files.keys():
            if self.path(name).exists():
                raise AppError("An export would overwrite an unrelated file. Choose a clean backup location.")
        changed = {name: source for name, source in sources.items()
                   if old_files.get(name) != new_files[name]}
        deleted = old_files.keys() - new_files.keys()
        manifest = {"version": 1, "account": account, "notes": new_notes}
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        if not self.path(MANIFEST).exists() or self.path(MANIFEST).read_bytes() != manifest_bytes:
            changed[MANIFEST] = manifest_bytes
        return result, changed, deleted

    def apply(self, snapshot: SnapshotModel) -> BackupResultModel:
        """Caller holds locked() for the entire fetch/apply cycle."""
        account = digest(snapshot.account.strip().lower().encode())
        old = self._validate_existing(account)
        result, changed, deleted = self._plan_snapshot(snapshot, old, account)
        if changed or deleted:
            self._save_changes(changed, deleted)
            result.commit = git(self.root, "rev-parse", "--short", "HEAD").stdout.decode().strip()
        return result

    def _save_changes(self, changed: dict, deleted: set):
        """Install validated exports and commit only affected managed paths."""
        affected = sorted(set(changed) | deleted)
        # A durable marker blocks later fetches if the process stops mid-save.
        # Never auto-delete recovery copies when restoration itself fails.
        rollback = Path(mkdtemp(prefix="notes-rollback-", dir=self.root / ".git"))
        marker = self.root / ".git" / "notesvault-save.json"
        head = git(self.root, "rev-parse", "--verify", "HEAD", check=False).stdout.strip()
        before = {}
        for index, name in enumerate(affected):
            if self.path(name).exists():
                saved = rollback / str(index)
                shutil.copyfile(self.path(name), saved)
                before[name] = saved
            else:
                before[name] = None
        journal = {"head": head.decode(), "rollback": rollback.name,
                   "before": {name: saved.name if saved else None for name, saved in before.items()}}
        with marker.open("x", encoding="utf-8") as output:
            json.dump(journal, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        committed = False
        try:
            for name, content in changed.items():
                target = self.path(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, Path):
                    shutil.copyfile(content, target)
                else:
                    target.write_bytes(content)
            for name in deleted:
                self.path(name).unlink()
            pathspec = b"\0".join(name.encode("utf-8") for name in affected) + b"\0"
            git(self.root, "add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul", input=pathspec)
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            git(self.root, "-c", "user.name=Notes Vault", "-c", "user.email=backup@notesvault.local",
                "-c", "commit.gpgsign=false", "commit", "--only", "--pathspec-from-file=-", "--pathspec-file-nul",
                "-m", f"Back up Apple Notes ({timestamp})", input=pathspec)
            committed = True
        finally:
            if not committed:
                if git(self.root, "rev-parse", "--verify", "HEAD", check=False).stdout.strip() != head:
                    raise AppError("Git history changed during the save. Recovery copies were retained; "
                                   "review the interrupted-save instructions before retrying.")
                for name, content in before.items():
                    target = self.path(name)
                    if content is None:
                        target.unlink(missing_ok=True)
                    else:
                        shutil.copyfile(content, target)
                # Restore only our index paths; never reset the user's working tree.
                for name in affected:
                    if head:
                        git(self.root, "reset", "-q", "HEAD", "--", name)
                    else:
                        git(self.root, "rm", "--cached", "--ignore-unmatch", "--", name)
            marker.unlink()
            shutil.rmtree(rollback)

