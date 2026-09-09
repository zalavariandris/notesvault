import json

from notesvault.config import ConfigStore


def test_obsolete_auth_selector_preserves_settings(tmp_path):
    store = ConfigStore(tmp_path)
    original = {
        "apple_id": "synthetic@example.invalid",
        "backup_folder": str(tmp_path / "backup"),
        "interval_minutes": 60,
        "auth_method": "obsolete-method",
    }
    store.path.write_text(json.dumps(original), encoding="utf-8")
    settings = store.load()
    assert settings.apple_id == original["apple_id"]
    assert settings.backup_folder == original["backup_folder"]
    assert settings.interval_minutes == 60
    store.save(settings)
    assert "auth_method" not in json.loads(store.path.read_text(encoding="utf-8"))
