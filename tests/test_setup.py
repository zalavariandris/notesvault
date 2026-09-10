from dataclasses import replace
from types import SimpleNamespace

import pytest

from notesvault.config_store import ConfigStoreController
from notesvault.icloud_authentication_controller import ICloudAuthenticationController
from notesvault.models import AppError


class Secrets:
    def __init__(self):
        self.values = {}
    def get(self, key):
        return self.values.get(key)
    def set(self, key, value):
        self.values[key] = value
    def delete(self, key):
        self.values.pop(key, None)


class Session:
    requires_2fa = False
    requires_2sa = False
    security_key_names = []
    notes = object()

    def __init__(self):
        self.requests = 0
        self.trusted = False
        self.logged_out = False
        self.persistence_removed = False
        self.session = self

    def request_2fa_code(self):
        self.requests += 1

    def validate_2fa_code(self, code):
        if code != "123456":
            return False
        self.requires_2fa = False
        return True

    def trust_session(self):
        self.trusted = True

    def logout(self):
        self.logged_out = True

    def clear_persistence(self, *, remove_files):
        self.persistence_removed = remove_files


@pytest.fixture
def authentication(tmp_path, monkeypatch):
    session = Session()
    calls = []
    def create(account, password=None, **options):
        calls.append((account, password, options))
        return session
    monkeypatch.setattr("pyicloud.PyiCloudService", create)
    controller = ICloudAuthenticationController(ConfigStoreController(tmp_path), Secrets())
    return controller, session, calls


def test_verification_retries_and_only_then_saves_password(authentication, capsys):
    controller, session, _ = authentication
    session.requires_2fa = True
    assert not controller.login(" Synthetic@example.invalid ", " synthetic-password ")
    assert session.requests == 1
    assert controller.secrets.values == {}
    assert not controller.connected
    with pytest.raises(AppError, match="Reconnect"):
        controller.session
    with pytest.raises(AppError, match="not accepted"):
        controller.verify("wrong")
    controller.verify(" 123456 ")
    assert session.trusted
    assert controller.connected
    assert controller.session is session
    assert controller.secrets.get("icloud:synthetic@example.invalid") == " synthetic-password "
    assert controller._password is None
    assert "synthetic-password" not in controller.store.path.read_text(encoding="utf-8")
    assert capsys.readouterr() == ("", "")


def test_cancel_preserves_saved_settings_and_credentials(authentication):
    controller, session, _ = authentication
    saved = replace(controller.store.load(), apple_id="synthetic@example.invalid", backup_folder="saved-folder")
    controller.store.save(saved)
    controller.secrets.set("icloud:synthetic@example.invalid", "saved-password")
    session.requires_2fa = True
    controller.login(saved.apple_id, "pending-password")
    controller.cancel()
    assert session.logged_out and session.persistence_removed
    assert controller._password is None
    assert not controller.connected
    assert controller.store.load() == saved
    assert controller.secrets.get("icloud:synthetic@example.invalid") == "saved-password"


def test_saved_login_is_shared_with_noninteractive_workflow(authentication):
    controller, session, calls = authentication
    controller.store.save(replace(controller.store.load(), apple_id="synthetic@example.invalid"))
    controller.secrets.set("icloud:synthetic@example.invalid", "saved-password")
    controller.login_saved()
    assert calls[0][:2] == ("synthetic@example.invalid", "saved-password")
    assert controller.connected
    assert session.requests == 0
    controller.clear()
    assert not controller.connected
    assert not session.persistence_removed
    assert controller.store.load().apple_id == "synthetic@example.invalid"


def test_noninteractive_verification_does_not_request_code(authentication):
    controller, session, _ = authentication
    controller.store.save(replace(controller.store.load(), apple_id="synthetic@example.invalid"))
    controller.secrets.set("icloud:synthetic@example.invalid", "saved-password")
    session.requires_2fa = True
    with pytest.raises(AppError, match="before running --once"):
        controller.login_saved()
    assert session.requests == 0
    assert controller._password is None
    assert not controller.connected


@pytest.mark.parametrize("apple_id,password", [("", ""), ("synthetic@example.invalid", "")])
def test_missing_saved_credentials_do_not_contact_icloud(authentication, apple_id, password):
    controller, _, calls = authentication
    controller.store.save(replace(controller.store.load(), apple_id=apple_id))
    with pytest.raises(AppError):
        controller.login_saved()
    assert not calls


def test_account_switch_cleans_old_session_before_saving_new_login(authentication):
    controller, session, calls = authentication
    controller.store.save(replace(controller.store.load(), apple_id="old@example.invalid"))
    controller.secrets.set("icloud:old@example.invalid", "old-password")
    assert controller.login("new@example.invalid", "new-password")
    assert calls[0][0] == "old@example.invalid"
    assert calls[0][2]["authenticate"] is False
    assert calls[0][2]["cookie_directory"] != calls[1][2]["cookie_directory"]
    assert session.persistence_removed
    assert controller.store.load().apple_id == "new@example.invalid"
    assert controller.secrets.values == {"icloud:new@example.invalid": "new-password"}


def test_logout_removes_saved_identity_even_if_remote_logout_fails(authentication, monkeypatch):
    controller, session, _ = authentication
    controller.login("synthetic@example.invalid", "synthetic-password")
    controller.store.save(replace(controller.store.load(), backup_folder="saved-folder"))
    def fail():
        raise RuntimeError("offline")
    monkeypatch.setattr(session, "logout", fail)
    controller.logout()
    assert session.persistence_removed
    assert not controller.connected
    assert controller.store.load().apple_id == ""
    assert controller.store.load().backup_folder == "saved-folder"
    assert controller.secrets.values == {}


@pytest.mark.parametrize("verification", [False, True])
def test_credential_save_failure_does_not_expose_ready_session(authentication, monkeypatch, verification):
    controller, session, _ = authentication
    session.requires_2fa = verification
    def fail(*args):
        raise AppError("Credential storage unavailable")
    monkeypatch.setattr(controller.secrets, "set", fail)
    if verification:
        controller.login("synthetic@example.invalid", "synthetic-password")
    with pytest.raises(AppError, match="Credential storage"):
        if verification:
            controller.verify("123456")
        else:
            controller.login("synthetic@example.invalid", "synthetic-password")
    assert controller._password is None
    assert not controller.connected
    assert controller.store.load().apple_id == ""


@pytest.mark.parametrize("mode", ["hardware", "legacy", "network"])
def test_failed_or_unsupported_authentication_has_safe_errors(authentication, monkeypatch, mode):
    controller, session, _ = authentication
    if mode == "hardware":
        session.requires_2fa = True
        session.security_key_names = ["synthetic key"]
    elif mode == "legacy":
        session.requires_2sa = True
    else:
        def fail(*args, **kwargs):
            raise RuntimeError("private diagnostic")
        monkeypatch.setattr("pyicloud.PyiCloudService", fail)
    with pytest.raises(AppError) as error:
        controller.login("synthetic@example.invalid", "synthetic-password")
    assert "private diagnostic" not in str(error.value)
    assert not controller.connected
    assert controller._password is None
    assert not controller.secrets.values


def test_expired_session_requires_reconnection(authentication):
    controller, session, _ = authentication
    controller.login("synthetic@example.invalid", "synthetic-password")
    session.requires_2fa = True
    assert not controller.connected
    with pytest.raises(AppError, match="Reconnect"):
        controller.session
