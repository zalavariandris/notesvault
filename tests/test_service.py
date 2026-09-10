import pytest

from notesvault.models import AppError, ConfigModel
from notesvault.demo_provider import DemoProvider
from notesvault.backup_controller import BackupController


def test_demo_backup_commits_locally_and_cleans_staging(tmp_path):
    from notesvault.disk_vault_controller import git
    settings = ConfigModel(backup_folder=str(tmp_path / "backup"))
    result = BackupController(settings.backup_folder).run_backup(DemoProvider(), tmp_path / "staging", lambda _: None)
    assert result.added == 3
    assert git(tmp_path / "backup", "rev-parse", "--verify", "HEAD").returncode == 0
    assert not list((tmp_path / "staging").iterdir())


def test_fetch_workflow_saves_status_without_changing_preferences(tmp_path):
    from notesvault.backup_controller import fetch_backup
    from notesvault.backup_status_store import BackupStatusStore
    from notesvault.config_store import ConfigStoreController

    store = ConfigStoreController(tmp_path / "config")
    store.save(ConfigModel(apple_id="demo", backup_folder=str(tmp_path / "backup")))
    original = store.path.read_bytes()
    status, result = fetch_backup(store, DemoProvider(), lambda _: None)
    assert result.added == 3
    assert BackupStatusStore(store.directory).load() == status
    assert store.path.read_bytes() == original


def test_status_write_failure_keeps_successful_backup(tmp_path, monkeypatch):
    from notesvault.backup_controller import fetch_backup
    from notesvault.backup_status_store import BackupStatusStore
    from notesvault.config_store import ConfigStoreController
    from notesvault.disk_vault_controller import git

    store = ConfigStoreController(tmp_path / "config")
    store.save(ConfigModel(backup_folder=str(tmp_path / "backup")))
    def fail(*args):
        raise OSError("synthetic disk failure")
    monkeypatch.setattr(BackupStatusStore, "save", fail)
    status, result = fetch_backup(store, DemoProvider(), lambda _: None)
    assert result.added == 3
    assert status.last_result == result.summary()
    assert any("status could not be saved" in message for message in result.warnings)
    assert git(tmp_path / "backup", "rev-parse", "--verify", "HEAD").returncode == 0


def cloud_provider(tmp_path):
    from types import SimpleNamespace
    from notesvault.icloud_notes_provider import ICloudNotesProvider

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
    provider = ICloudNotesProvider(SimpleNamespace(notes=notes), "synthetic@example.invalid")
    return provider, notes


def test_unchanged_cloud_reuses_files_but_rejects_local_edits(tmp_path):
    from notesvault.disk_vault_controller import git
    provider, notes = cloud_provider(tmp_path)
    settings = ConfigModel(backup_folder=str(tmp_path / "backup"))
    def run():
        return BackupController(settings.backup_folder).run_backup(provider, tmp_path / "staging", lambda _: None)
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
    settings = ConfigModel(backup_folder=str(tmp_path / "backup"))
    def run():
        return BackupController(settings.backup_folder).run_backup(provider, tmp_path / "staging", lambda _: None)
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
    settings = ConfigModel(backup_folder=str(tmp_path / "backup"))
    def run():
        return BackupController(settings.backup_folder).run_backup(provider, tmp_path / "staging", lambda _: None)
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
            from notesvault import provider_utils
            monkeypatch.setattr(provider_utils, "EXPORT_VERSION", provider_utils.EXPORT_VERSION + 1)
    run()
    assert notes.scans == 2


def test_cancel_after_retrieval_preserves_backups_cache_and_status(tmp_path, monkeypatch):
    from notesvault.backup_controller import fetch_backup
    from notesvault.config_store import ConfigStoreController
    from notesvault.disk_vault_controller import git, MANIFEST
    from notesvault.fetch_control import FetchCancelled, FetchControl

    store = ConfigStoreController(tmp_path / "config")
    root = tmp_path / "backup"
    store.save(ConfigModel(backup_folder=str(root)))
    provider, notes = cloud_provider(tmp_path)
    fetch_backup(store, provider, lambda _: None)
    paths = [root / MANIFEST, root / ".git" / "notesvault-fetch.json",
             store.directory / "backup-status.json", *root.glob("notes/*.md")]
    original = {path: path.read_bytes() for path in paths}
    head = git(root, "rev-parse", "HEAD").stdout
    control = FetchControl()
    notes.cursor = "changed"
    fetch = provider.fetch
    def cancel_after_download(*args, **kwargs):
        snapshot = fetch(*args, **kwargs)
        assert snapshot.notes
        control.cancel()
        return snapshot
    monkeypatch.setattr(provider, "fetch", cancel_after_download)
    with pytest.raises(FetchCancelled):
        fetch_backup(store, provider, lambda _: None, control=control)
    assert all(path.read_bytes() == data for path, data in original.items())
    assert git(root, "rev-parse", "HEAD").stdout == head
    assert not list((store.directory / "staging").iterdir())
    # Cancellation releases the repository lock and leaves the next fetch usable.
    monkeypatch.setattr(provider, "fetch", fetch)
    assert fetch_backup(store, provider, lambda _: None)[1].commit == "No changes"


def test_pause_resume_reuses_current_fetch_without_redownloading(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from notesvault.fetch_control import FetchControl

    provider, notes = cloud_provider(tmp_path)
    paused = Event()
    control = FetchControl(lambda state: paused.set() if state == "paused" else None)
    original_get = notes.get
    def get(*args, **kwargs):
        note = original_get(*args, **kwargs)
        control.pause()
        return note
    monkeypatch.setattr(notes, "get", get)
    with ThreadPoolExecutor() as executor:
        future = executor.submit(BackupController(tmp_path / "backup").run_backup,
                                 provider, tmp_path / "stage", lambda _: None, control=control)
        try:
            assert paused.wait(5)
            assert not future.done()
            assert not list((tmp_path / "backup").glob("notes/*.md"))
            control.resume()
            assert future.result(timeout=10).added == 1
            assert notes.downloads == notes.scans == 1
        finally:
            control.cancel()


def test_cancel_during_local_save_finishes_commit_and_status(tmp_path, monkeypatch):
    from notesvault.backup_controller import fetch_backup
    from notesvault.backup_status_store import BackupStatusStore
    from notesvault.config_store import ConfigStoreController
    from notesvault.disk_vault_controller import DiskVaultController
    from notesvault.fetch_control import FetchControl

    control = FetchControl()
    store = ConfigStoreController(tmp_path / "config")
    store.save(ConfigModel(backup_folder=str(tmp_path / "backup")))
    apply = DiskVaultController.apply
    def save(vault, snapshot):
        assert control.state == "saving"
        assert not control.cancel()
        assert not control.pause()
        return apply(vault, snapshot)
    monkeypatch.setattr(DiskVaultController, "apply", save)
    status, result = fetch_backup(store, DemoProvider(), lambda _: None, control=control)
    assert result.added == 3
    assert BackupStatusStore(store.directory).load() == status
