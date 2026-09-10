import json
from types import SimpleNamespace

import pytest
from pyicloud.services.notes.client import NotesApiError
from pyicloud.services.notes.service import NoteNotFound

from notesvault.backup_controller import BackupController
from notesvault.disk_vault_controller import git, MANIFEST
from notesvault.icloud_notes_provider import ICloudNotesProvider
from notesvault.models import AppError


def event(note_id, kind="updated", locked=False):
    return SimpleNamespace(type=kind, note=SimpleNamespace(id=note_id, is_locked=locked))


class Cloud:
    def __init__(self):
        self.cursor = "first"
        self.data = {"one": "First", "two": "Second"}
        self.events = []
        self.calls = []
        self.downloads = []
        self.expired = False
        self.failed = False
        self.missing = set()

    def sync_cursor(self):
        return self.cursor

    def iter_changes(self, *, since=None):
        self.calls.append(since)
        if since is not None:
            yield from self.events
            if self.expired:
                raise NotesApiError("expired", payload={"serverErrorCode": "BAD_SYNC_TOKEN"})
            if self.failed:
                raise NotesApiError("private diagnostic", payload={"serverErrorCode": "ACCESS_DENIED"})
        else:
            yield from (event(key) for key in self.data)

    def get(self, note_id, *, with_attachments=False):
        self.downloads.append((note_id, with_attachments))
        if note_id in self.missing:
            raise NoteNotFound("synthetic")
        return SimpleNamespace(id=note_id, title=self.data[note_id], text=self.data[note_id],
            html=f"<h1>{self.data[note_id]}</h1><p><b>Synthetic</b> text</p>", is_deleted=False,
            folder_name="Notes", folder_id="folder", modified_at=None, attachments=[])


@pytest.fixture
def backup(tmp_path):
    cloud = Cloud()
    provider = ICloudNotesProvider(SimpleNamespace(notes=cloud), "synthetic@example.invalid")
    controller = BackupController(tmp_path / "backup")
    def run(**kwargs):
        return controller.run_backup(provider, lambda _: None, **kwargs)
    return cloud, controller.vault.root, run


def test_only_changed_notes_download_and_renames_keep_identity(backup):
    cloud, root, run = backup
    assert run().added == 2
    original = next(root.rglob("*-First-*.md")).read_bytes()
    cloud.cursor, cloud.events = "second", [event("two")]
    cloud.data["two"] = "Renamed"
    result = run()
    assert result.updated == 1 and result.added == result.deleted == 0
    assert cloud.downloads == [("one", False), ("two", False), ("two", False)]
    assert cloud.calls == [None, "first"]
    assert next(root.rglob("*-First-*.md")).read_bytes() == original
    assert len(list(root.rglob("*-Renamed-*.md"))) == 1
    assert not list(root.rglob("*-Second-*.md"))
    assert run().commit == "No changes"
    assert len(cloud.downloads) == 3


def test_explicit_deletion_commits_without_downloading_remaining_notes(backup):
    cloud, root, run = backup
    run()
    cloud.cursor, cloud.events = "second", [event("one", "deleted")]
    cloud.data.pop("one")
    assert run().deleted == 1
    assert len(cloud.downloads) == 2
    assert not list(root.rglob("*-First-*.md"))
    assert git(root, "log", "--oneline").stdout.count(b"\n") == 2


def test_expired_cursor_discards_partial_delta_and_full_scans(backup):
    cloud, root, run = backup
    run()
    cloud.cursor, cloud.events, cloud.expired = "second", [event("one", "deleted")], True
    result = run()
    assert result.deleted == 0
    assert cloud.calls == [None, "first", None]
    assert len(cloud.downloads) == 4
    assert list(root.rglob("*-First-*.md"))
    assert json.loads((root / ".git/notesvault-fetch.json").read_text())["cursor"] == "second"


def test_network_or_page_failure_never_applies_partial_deletions(backup):
    cloud, root, run = backup
    run()
    cache = root / ".git/notesvault-fetch.json"
    original = cache.read_bytes()
    cloud.cursor, cloud.events, cloud.failed = "second", [event("one", "deleted")], True
    with pytest.raises(AppError, match="fetch failed") as error:
        run()
    assert "private diagnostic" not in str(error.value)
    assert cache.read_bytes() == original
    assert list(root.rglob("*-First-*.md"))
    assert cloud.calls == [None, "first"]


@pytest.mark.parametrize("locked", [False, True])
def test_inaccessible_note_defers_deletions_and_cache_until_retry(backup, locked):
    cloud, root, run = backup
    run()
    original = (root / ".git/notesvault-fetch.json").read_bytes()
    cloud.cursor, cloud.events = "second", [event("one", "deleted"), event("two", locked=locked)]
    if not locked:
        cloud.missing.add("two")
    result = run()
    assert result.skipped == 1 and result.deleted == 0
    assert (root / ".git/notesvault-fetch.json").read_bytes() == original
    assert list(root.rglob("*-First-*.md")) and list(root.rglob("*-Second-*.md"))
    cloud.missing.clear()
    cloud.events = [event("one", "deleted"), event("two")]
    assert run().deleted == 1


def test_full_scan_absence_does_not_delete_content_in_unscanned_zones(backup):
    cloud, root, run = backup
    run()
    (root / ".git/notesvault-fetch.json").write_text("invalid")
    cloud.data.pop("one")
    cloud.cursor = "second"
    result = run()
    assert result.deleted == 0
    assert list(root.rglob("*-First-*.md"))
    assert any("Separate shared zones" in warning for warning in result.warnings)


def test_attachment_option_and_export_version_invalidate_cache(backup, monkeypatch):
    from notesvault import provider_utils
    cloud, root, run = backup
    run()
    run(download_attachments=True)
    assert cloud.calls == [None, None]
    assert cloud.downloads[-2:] == [("one", True), ("two", True)]
    run(download_attachments=True)
    assert len(cloud.downloads) == 4
    monkeypatch.setattr(provider_utils, "EXPORT_VERSION", provider_utils.EXPORT_VERSION + 1)
    run(download_attachments=True)
    assert cloud.calls == [None, None, None]


def test_commit_failure_does_not_advance_incremental_cursor(backup, monkeypatch):
    cloud, root, run = backup
    run()
    cache = root / ".git/notesvault-fetch.json"
    original = cache.read_bytes()
    cloud.cursor, cloud.events = "second", [event("two")]
    cloud.data["two"] = "Changed"
    from notesvault import disk_vault_controller
    original_git = disk_vault_controller.git
    def fail_commit(root, *args, **kwargs):
        if "commit" in args:
            raise AppError("synthetic commit failure")
        return original_git(root, *args, **kwargs)
    monkeypatch.setattr(disk_vault_controller, "git", fail_commit)
    with pytest.raises(AppError, match="commit failure"):
        run()
    assert cache.read_bytes() == original
    assert list(root.rglob("*-Second-*.md"))
    assert not list(root.rglob("*-Changed-*.md"))


def test_folder_change_requires_full_metadata_refresh(backup, monkeypatch):
    from notesvault import icloud_notes_provider
    from notesvault.icloud_note_changes import NoteChange
    cloud, root, run = backup
    run()
    cloud.cursor = "second"
    calls = []
    def changes(service, since, control):
        calls.append(since)
        if since:
            yield NoteChange("folder", is_folder=True)
        else:
            yield from (NoteChange(key) for key in cloud.data)
    monkeypatch.setattr(icloud_notes_provider, "read_changes", changes)
    original = cloud.get
    def moved(*args, **kwargs):
        note = original(*args, **kwargs)
        note.folder_name = "Renamed folder"
        return note
    monkeypatch.setattr(cloud, "get", moved)
    assert run().updated == 2
    assert calls == ["first", None]
    assert len(cloud.downloads) == 4
    assert all("Renamed folder" in str(path.parent) for path in root.rglob("*.md"))


def test_remote_change_during_delta_retains_previous_snapshot(backup):
    cloud, root, run = backup
    run()
    cache = (root / ".git/notesvault-fetch.json").read_bytes()
    head = git(root, "rev-parse", "HEAD").stdout
    cloud.cursor, cloud.events = "second", [event("two")]
    original = cloud.get
    def changing(*args, **kwargs):
        cloud.cursor = "third"
        return original(*args, **kwargs)
    cloud.get = changing
    with pytest.raises(AppError, match="changed during"):
        run()
    assert git(root, "rev-parse", "HEAD").stdout == head
    assert (root / ".git/notesvault-fetch.json").read_bytes() == cache
