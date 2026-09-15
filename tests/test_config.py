import json

from notesvault.config_store import ConfigStoreController
from notesvault.backup_status_store import BackupStatusStore
from notesvault.models import BackupStatusModel, ConfigModel
from notesvault.application import Application


def test_application_uses_default_per_user_settings(tmp_path, monkeypatch):
    directory = tmp_path / "NotesVault"
    def default_location(name, *, appauthor):
        assert name == "NotesVault" and appauthor is False
        return directory
    monkeypatch.setattr("notesvault.config_store.user_data_path", default_location)
    settings = ConfigModel(apple_id="synthetic@example.invalid", backup_folder=str(tmp_path / "vault"))
    ConfigStoreController(directory).save(settings)
    app = Application()
    assert app.store.directory == directory
    assert app.store.load() == settings
    assert app.authentication.store is app.store


def test_new_settings_ignore_retired_environment_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("ICLOUD_APPLE_ID", "synthetic@example.invalid")
    monkeypatch.setenv("LOCAL_EXPORT_DIR", str(tmp_path / "retired-backup"))
    store = ConfigStoreController(tmp_path)
    assert store.load() == ConfigModel()


def test_retired_options_preserve_local_settings(tmp_path):
    store = ConfigStoreController(tmp_path)
    original = {
        "apple_id": "synthetic@example.invalid",
        "backup_folder": str(tmp_path / "backup"),
        "interval_minutes": 60,
        "auth_method": "obsolete-method",
        "github_repo": "synthetic/retired",
        "last_result": "1 added\nLocal Git: abc123\nGitHub: Published to synthetic/retired",
    }
    store.path.write_text(json.dumps(original), encoding="utf-8")
    settings = store.load()
    assert settings.apple_id == original["apple_id"]
    assert settings.backup_folder == original["backup_folder"]
    assert settings.interval_minutes == 60
    status_store = BackupStatusStore(tmp_path)
    assert status_store.load().last_result == "1 added\nLocal Git: abc123"
    store.save(settings)
    saved = json.loads(store.path.read_text(encoding="utf-8"))
    assert "auth_method" not in saved
    assert "github_repo" not in saved
    assert set(saved) == {"apple_id", "backup_folder", "interval_minutes", "download_attachments"}
    assert settings.download_attachments is False
    assert status_store.load().last_result == "1 added\nLocal Git: abc123"


def test_saving_preferences_does_not_replace_newer_backup_status(tmp_path):
    store = ConfigStoreController(tmp_path)
    store.path.write_text(json.dumps({"last_backup": "legacy", "last_result": "old"}), encoding="utf-8")
    statuses = BackupStatusStore(tmp_path)
    latest = BackupStatusModel("new", "3 added")
    statuses.save(latest)
    store.save(ConfigModel(interval_minutes=0))
    assert statuses.load() == latest


def test_failed_status_migration_keeps_legacy_settings(tmp_path, monkeypatch):
    import pytest

    store = ConfigStoreController(tmp_path)
    original = json.dumps({"last_backup": "legacy", "last_result": "old"})
    store.path.write_text(original, encoding="utf-8")
    def fail(*args):
        raise OSError("synthetic disk failure")
    monkeypatch.setattr(BackupStatusStore, "save", fail)
    with pytest.raises(OSError):
        store.save(ConfigModel())
    assert store.path.read_text(encoding="utf-8") == original
