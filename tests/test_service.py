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
