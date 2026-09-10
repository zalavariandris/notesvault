import json

from notesvault.config import ConfigStore


def test_retired_options_preserve_local_settings(tmp_path):
    store = ConfigStore(tmp_path)
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
    assert settings.last_result == "1 added\nLocal Git: abc123"
    store.save(settings)
    saved = json.loads(store.path.read_text(encoding="utf-8"))
    assert "auth_method" not in saved
    assert "github_repo" not in saved
