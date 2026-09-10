from types import SimpleNamespace

import pytest

from notesvault.config import ConfigStore
from notesvault.models import AppError
from notesvault.setup import AccountSetup


class Secrets:
    def __init__(self):
        self.values = {}
    def get(self, key):
        return self.values.get(key)
    def set(self, key, value):
        self.values[key] = value
    def delete(self, key):
        self.values.pop(key, None)


def test_verification_retries_and_only_then_saves_password(tmp_path, capsys):
    store, secrets = ConfigStore(tmp_path), Secrets()
    def verify(code):
        if code != "123456":
            raise AppError("Invalid code")
    setup = AccountSetup(store, secrets, SimpleNamespace(login=lambda *a: False, verify=verify))
    assert not setup.login("Synthetic@example.invalid", " synthetic-password ")
    assert secrets.values == {}
    with pytest.raises(AppError, match="Invalid"):
        setup.verify("wrong")
    setup.verify("123456")
    assert secrets.get("icloud:synthetic@example.invalid") == " synthetic-password "
    assert setup._password is None
    assert "synthetic-password" not in store.path.read_text(encoding="utf-8")
    assert capsys.readouterr() == ("", "")


def test_cancel_clears_pending_password_and_session(tmp_path):
    calls = []
    setup = AccountSetup(ConfigStore(tmp_path), Secrets(),
                         SimpleNamespace(login=lambda *a: False, logout=lambda: calls.append("logout")))
    setup.login("synthetic@example.invalid", "synthetic-password")
    setup.cancel()
    assert calls == ["logout"]
    assert setup._password is None
    assert setup.secrets.values == {}


def test_saved_password_is_reused(tmp_path):
    secrets = Secrets()
    secrets.set("icloud:synthetic@example.invalid", "synthetic-password")
    def login(account, password):
        assert password == "synthetic-password"
        return True
    setup = AccountSetup(ConfigStore(tmp_path), secrets, SimpleNamespace(login=login))
    assert setup.login("synthetic@example.invalid", "")
    assert setup.store.load().apple_id == "synthetic@example.invalid"
