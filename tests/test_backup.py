import subprocess
from pathlib import Path

import pytest

from notesvault.backup import BackupRepository, MANIFEST, git
from notesvault.models import AppError, Snapshot
from notesvault.providers import write_export


def note(stage, note_id="one", title="A note", text="original", attachments=None):
    return write_export(stage, note_id, title, text, "Notes", "folder", None, attachments or [])


def apply(repo, notes, **kwargs):
    with repo.locked():
        return repo.apply(Snapshot("account", notes, **kwargs))


def test_backup_repeat_rename_delete_and_history(tmp_path):
    repo = BackupRepository(tmp_path / "backup")
    original = note(tmp_path / "stage")
    assert apply(repo, [original]).added == 1
    head = git(repo.root, "rev-parse", "HEAD").stdout
    assert apply(repo, [original]).commit == "No changes"
    assert git(repo.root, "rev-parse", "HEAD").stdout == head
    renamed = note(tmp_path / "stage2", title="Renamed", text="new content")
    assert apply(repo, [renamed]).updated == 1
    original_md = next(name for name in original.files if name.endswith(".md"))
    assert not (repo.root / original_md).exists()
    assert git(repo.root, "show", f"{head.decode().strip()}:{original_md}").stdout == b"original\n"
    assert apply(repo, []).deleted == 1
    assert git(repo.root, "status", "--porcelain").stdout == b""


@pytest.mark.parametrize("complete,skipped", [(False, 0), (True, 1)])
def test_partial_snapshot_retains_missing_notes(tmp_path, complete, skipped):
    repo = BackupRepository(tmp_path / "backup")
    original = note(tmp_path / "stage")
    apply(repo, [original])
    result = apply(repo, [], complete=complete, skipped=skipped)
    assert result.deleted == 0
    assert all((repo.root / name).exists() for name in original.files)


def test_local_edits_are_not_overwritten(tmp_path):
    repo = BackupRepository(tmp_path / "backup")
    original = note(tmp_path / "stage")
    apply(repo, [original])
    target = repo.root / next(iter(original.files))
    target.write_text("my edit")
    with pytest.raises(AppError, match="edited"):
        apply(repo, [note(tmp_path / "stage2", text="remote edit")])
    assert target.read_text() == "my edit"


def test_unrelated_files_not_committed_and_staged_changes_rejected(tmp_path):
    repo = BackupRepository(tmp_path / "backup")
    repo.initialize()
    (repo.root / "private.txt").write_text("unrelated")
    apply(repo, [note(tmp_path / "stage")])
    assert "private.txt" not in git(repo.root, "ls-tree", "-r", "--name-only", "HEAD").stdout.decode()
    git(repo.root, "add", "private.txt")
    with pytest.raises(AppError, match="staged"):
        apply(repo, [])
    assert git(repo.root, "diff", "--cached", "--name-only").stdout.strip() == b"private.txt"


def test_account_switch_blocked(tmp_path):
    repo = BackupRepository(tmp_path / "backup")
    apply(repo, [note(tmp_path / "stage")])
    with repo.locked(), pytest.raises(AppError, match="another iCloud account"):
        repo.apply(Snapshot("other", []))


def test_duplicate_ids_and_unrelated_collision_blocked(tmp_path):
    repo = BackupRepository(tmp_path / "backup")
    first = note(tmp_path / "stage")
    with pytest.raises(AppError, match="duplicate"):
        apply(repo, [first, first])
    target = repo.root / next(iter(first.files))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("unrelated")
    with pytest.raises(AppError, match="unrelated"):
        apply(repo, [first])
    assert target.read_text() == "unrelated"


def test_attachment_change_and_unicode_paths(tmp_path):
    repo = BackupRepository(tmp_path / "backup")
    original = note(tmp_path / "stage", title="Árvíztűrő [☁] / test",
                    attachments=[("image", "CON.jpg", b"old")])
    apply(repo, [original])
    updated = note(tmp_path / "stage2", title="Árvíztűrő [☁] / test",
                   attachments=[("image", "CON.jpg", b"new")])
    assert apply(repo, [updated]).updated == 1
    assert git(repo.root, "status", "--porcelain").stdout == b""


def test_commit_failure_restores_files_and_index(tmp_path, monkeypatch):
    import notesvault.backup as backup
    repo = BackupRepository(tmp_path / "backup")
    original = note(tmp_path / "stage")
    apply(repo, [original])
    prior = (repo.root / MANIFEST).read_bytes()
    real_git = backup.git
    def fail_commit(root, *args, **kwargs):
        if "commit" in args:
            raise AppError("simulated commit failure")
        return real_git(root, *args, **kwargs)
    monkeypatch.setattr(backup, "git", fail_commit)
    with pytest.raises(AppError, match="simulated"):
        apply(repo, [note(tmp_path / "stage2", title="different")])
    assert (repo.root / MANIFEST).read_bytes() == prior
    assert git(repo.root, "status", "--porcelain").stdout == b""


@pytest.mark.parametrize("path", ["../outside", "notes/../../outside", "/absolute", "notes\\escape", "notes/a:stream", ".git/config"])
def test_unsafe_paths_rejected(tmp_path, path):
    with pytest.raises(AppError):
        BackupRepository(tmp_path).path(path)


def test_repository_lock_blocks_second_instance(tmp_path):
    repo = BackupRepository(tmp_path / "backup")
    with repo.locked(), pytest.raises(AppError, match="Another backup"):
        with BackupRepository(repo.root).locked():
            pass
