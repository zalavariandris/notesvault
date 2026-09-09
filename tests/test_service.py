import pytest

from notesvault.config import Settings
from notesvault.models import AppError
from notesvault.providers import DemoProvider
from notesvault.service import run_backup


def test_push_failure_keeps_local_commit(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from notesvault.backup import git
    def failed_push(*args):
        raise AppError("simulated push failure")
    monkeypatch.setattr("notesvault.service.push_repository", failed_push)
    settings = Settings(backup_folder=str(tmp_path / "backup"), github_repo="owner/repo")
    result = run_backup(DemoProvider(), settings, SimpleNamespace(get=lambda _: "token"),
                        tmp_path / "staging", lambda _: None)
    assert result.added == 3
    assert result.push == "simulated push failure"
    assert git(tmp_path / "backup", "rev-parse", "--verify", "HEAD").returncode == 0
    assert not list((tmp_path / "staging").iterdir())


def cloud_provider(tmp_path):
    from types import SimpleNamespace
    from notesvault.providers import ICloudProvider

    class Notes:
        cursor = "first"
        downloads = 0
        scans = 0
        fail = False
        def sync_cursor(self):
            return self.cursor
        def iter_all(self):
            self.scans += 1
            return [SimpleNamespace(id="one", is_deleted=False)]
        def get(self, *args, **kwargs):
            self.downloads += 1
            if self.fail:
                raise RuntimeError("synthetic failure")
            return SimpleNamespace(id="one", is_deleted=False, text="synthetic",
                attachments=[], title="Example", folder_name="Notes", folder_id="folder",
                modified_at=None)

    notes = Notes()
    provider = ICloudProvider(tmp_path / "sessions")
    provider.account = "synthetic@example.invalid"
    provider.api = SimpleNamespace(notes=notes, requires_2fa=False, requires_2sa=False)
    return provider, notes


def test_unchanged_cloud_reuses_files_but_rejects_local_edits(tmp_path):
    from notesvault.backup import git
    provider, notes = cloud_provider(tmp_path)
    settings = Settings(backup_folder=str(tmp_path / "backup"))
    def run():
        return run_backup(provider, settings, None, tmp_path / "staging", lambda _: None)
    assert run().added == 1
    head = git(tmp_path / "backup", "rev-parse", "HEAD").stdout
    assert run().commit == "No changes"
    assert notes.downloads == notes.scans == 1
    assert git(tmp_path / "backup", "rev-parse", "HEAD").stdout == head
    target = next((tmp_path / "backup" / "notes").rglob("*.md"))
    target.write_text("user edit", encoding="utf-8")
    with pytest.raises(AppError, match="edited"):
        run()
    assert target.read_text(encoding="utf-8") == "user edit"


def test_changed_cursor_failure_does_not_advance_cache(tmp_path):
    provider, notes = cloud_provider(tmp_path)
    settings = Settings(backup_folder=str(tmp_path / "backup"))
    def run():
        return run_backup(provider, settings, None, tmp_path / "staging", lambda _: None)
    run()
    cache = tmp_path / "backup" / ".git" / "notesvault-fetch.json"
    original = cache.read_bytes()
    notes.cursor, notes.fail = "second", True
    with pytest.raises(AppError, match="fetch failed"):
        run()
    assert cache.read_bytes() == original
    notes.fail = False
    run()
    assert cache.read_bytes() != original
    assert notes.downloads == 3


@pytest.mark.parametrize("invalidation", ["corrupt", "export", "skipped"])
def test_cache_fallback(tmp_path, monkeypatch, invalidation):
    from pyicloud.services.notes.service import NoteLockedError
    provider, notes = cloud_provider(tmp_path)
    settings = Settings(backup_folder=str(tmp_path / "backup"))
    def run():
        return run_backup(provider, settings, None, tmp_path / "staging", lambda _: None)
    if invalidation == "skipped":
        original_get = notes.get
        def locked(*a, **kw):
            raise NoteLockedError("synthetic")
        notes.get = locked
        assert run().skipped == 1
        notes.get = original_get
    else:
        run()
        if invalidation == "corrupt":
            (tmp_path / "backup" / ".git" / "notesvault-fetch.json").write_text("invalid", encoding="utf-8")
        else:
            monkeypatch.setattr("notesvault.service.EXPORT_VERSION", 999)
    run()
    assert notes.scans == 2
