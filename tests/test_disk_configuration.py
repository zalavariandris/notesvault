from dataclasses import replace

import pytest

from notesvault.config_store import ConfigStoreController
from notesvault.disk_vault_controller import DiskVaultController
from notesvault.models import AppError


@pytest.mark.parametrize("interval", ["invalid", "-1", "10081"])
def test_invalid_interval_preserves_saved_configuration(tmp_path, interval):
    store = ConfigStoreController(tmp_path / "config")
    saved = store.load()
    store.save(saved)
    with pytest.raises(AppError, match="interval"):
        DiskVaultController.save_configuration(store, str(tmp_path / "backup"), interval)
    assert store.load() == saved
    assert not (tmp_path / "backup").exists()


def test_configuration_initializes_vault_and_preserves_account(tmp_path):
    store = ConfigStoreController(tmp_path / "config")
    store.save(replace(store.load(), apple_id="synthetic@example.invalid"))
    folder = tmp_path / "backup"
    saved = DiskVaultController.save_configuration(store, str(folder), "0")
    assert saved == store.load()
    assert saved.apple_id == "synthetic@example.invalid"
    assert saved.interval_minutes == 0
    assert (folder / ".git").is_dir()
    with pytest.raises(AppError, match="replacing"):
        DiskVaultController.save_configuration(store, "", "30")
    assert store.load() == saved


def test_failed_vault_initialization_does_not_save_drafts(tmp_path):
    store = ConfigStoreController(tmp_path / "config")
    saved = store.load()
    folder = tmp_path / "source"
    folder.mkdir()
    (folder / "AGENTS.md").write_text("synthetic source", encoding="utf-8")
    with pytest.raises(AppError, match="separate"):
        DiskVaultController.save_configuration(store, str(folder), "0")
    assert store.load() == saved


def test_pending_fetch_requires_folder_but_interval_alone_can_save(tmp_path):
    store = ConfigStoreController(tmp_path)
    with pytest.raises(AppError, match="continue the fetch"):
        DiskVaultController.save_configuration(store, "", "0", require_folder=True)
    assert DiskVaultController.save_configuration(store, "", "0").interval_minutes == 0
