from types import SimpleNamespace

import pytest

from notesvault.github import push_repository, validate_repository
from notesvault.models import AppError


def response(private=True, push=True):
    return SimpleNamespace(status_code=200, json=lambda: {
        "private": private, "permissions": {"push": push}, "default_branch": "main"})


def test_public_repository_never_pushed(tmp_path, monkeypatch):
    monkeypatch.setattr("notesvault.github.requests.get", lambda *a, **k: response(private=False))
    def unexpected(*args, **kwargs):
        pytest.fail("A public repository must not reach Git push")
    monkeypatch.setattr("notesvault.github.subprocess.run", unexpected)
    with pytest.raises(AppError, match="private"):
        push_repository(tmp_path, "owner/repo", "secret-token")


def test_write_permissions_required(monkeypatch):
    monkeypatch.setattr("notesvault.github.requests.get", lambda *a, **k: response(push=False))
    with pytest.raises(AppError, match="write access"):
        validate_repository("owner/repo", "token")


def test_token_not_in_process_arguments_or_remote_url(tmp_path, monkeypatch):
    monkeypatch.setattr("notesvault.github.requests.get", lambda *a, **k: response())
    monkeypatch.setattr("notesvault.github.git", lambda *a, **k: SimpleNamespace(returncode=0))
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr("notesvault.github.subprocess.run", run)
    assert push_repository(tmp_path, "owner/repo", "secret-token").startswith("Published")
    assert "secret-token" not in str(calls[0][0])
    assert "--force" not in calls[0][0]
    assert calls[0][1]["env"]["GIT_CONFIG_KEY_0"].endswith(".extraheader")
