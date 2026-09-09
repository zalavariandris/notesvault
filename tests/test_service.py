import pytest

from notes_vault.config import Settings
from notes_vault.models import AppError
from notes_vault.providers import DemoProvider
from notes_vault.service import run_backup


def test_push_failure_keeps_local_commit(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from notes_vault.backup import git
    def failed_push(*args):
        raise AppError("simulated push failure")
    monkeypatch.setattr("notes_vault.service.push_repository", failed_push)
    settings = Settings(backup_folder=str(tmp_path / "backup"), github_repo="owner/repo")
    result = run_backup(DemoProvider(), settings, SimpleNamespace(get=lambda _: "token"),
                        tmp_path / "staging", lambda _: None)
    assert result.added == 3
    assert result.push == "simulated push failure"
    assert git(tmp_path / "backup", "rev-parse", "--verify", "HEAD").returncode == 0
    assert not list((tmp_path / "staging").iterdir())
