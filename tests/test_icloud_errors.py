from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pyicloud import exceptions as cloud
from pyicloud.services.notes.client import NotesAuthError
from requests.exceptions import ConnectionError

from notesvault.fetch_control import FetchControl
from notesvault.icloud_errors import ReconnectRequired, TermsAcceptanceRequired, login_error
from notesvault.models import AppError
from test_interfaces import terminal
from test_service import cloud_provider
from test_setup import Secrets
from test_setup import Session
from notesvault.icloud_authentication_controller import ICloudAuthenticationController
from notesvault.icloud_notes_provider import ICloudNotesProvider


@pytest.mark.parametrize('error,expected', [
    (cloud.PyiCloudFailedLoginException('private diagnostic'), 'email and password'),
    (ConnectionError('private diagnostic'), 'internet connection'),
    (cloud.PyiCloudAcceptTermsException('private diagnostic'), 'updated iCloud terms'),
    (cloud.PyiCloudServiceUnavailable('private diagnostic'), 'Wait a few minutes'),
    (RuntimeError('private diagnostic'), 'try again'),
])
def test_safe_login_errors(error, expected):
    message = str(login_error(error))
    assert expected in message
    assert 'private diagnostic' not in message
    if isinstance(error, cloud.PyiCloudAcceptTermsException):
        assert isinstance(login_error(error), TermsAcceptanceRequired)


@pytest.mark.parametrize('stage', ['saved', 'password', 'verification'])
def test_terms_requirement_stops_terminal_credential_retry(tmp_path, monkeypatch, stage):
    ui = terminal(tmp_path)
    auth = ICloudAuthenticationController(ui.app.store, Secrets())
    ui.app.authentication = auth
    ui.app.store.save(replace(ui.app.store.load(), apple_id='synthetic@example.invalid'))
    auth.secrets.set('icloud:synthetic@example.invalid', 'saved-password')
    saved = ui.app.store.load()
    calls = []
    session = Session()
    session.requires_2fa = stage == 'verification'
    if stage == 'password':
        auth.secrets.delete('icloud:synthetic@example.invalid')
    original_secrets = dict(auth.secrets.values)
    def terms(*args):
        raise cloud.PyiCloudAcceptTermsException('private diagnostic')
    def create(*args, **kwargs):
        calls.append(kwargs)
        assert kwargs['accept_terms'] is False
        if stage == 'verification':
            return session
        terms()
    monkeypatch.setattr('pyicloud.PyiCloudService', create)
    if stage == 'verification':
        monkeypatch.setattr(session, 'validate_2fa_code', terms)
    answers = iter(['synthetic@example.invalid', 'synthetic-password'] if stage == 'password'
                   else ['123456'] if stage == 'verification' else [])
    monkeypatch.setattr('notesvault.terminal.Prompt.ask', lambda *a, **kw: next(answers))
    try:
        assert ui.login() is False
        assert len(calls) == 1
        assert not auth.connected and auth._password is None
        assert ui.app.store.load() == saved
        assert auth.secrets.values == original_secrets
        ui.schedule()
        assert ui.next_fetch is None
        output = ui.console.file.getvalue()
        assert 'icloud.com' in output and 'answer yes to retry sign-in' in output
        assert 'private diagnostic' not in output
        assert 'synthetic-password' not in output
    finally:
        ui.tasks.close()


def test_terminal_real_controller_retries_failed_password(tmp_path, monkeypatch):
    ui = terminal(tmp_path)
    auth = ICloudAuthenticationController(ui.app.store, Secrets())
    ui.app.authentication = auth
    attempts = []
    def create(account, password, **kwargs):
        attempts.append(password)
        if len(attempts) == 1:
            raise cloud.PyiCloudFailedLoginException('private diagnostic')
        return SimpleNamespace(requires_2fa=False, requires_2sa=False, notes=object())
    monkeypatch.setattr('pyicloud.PyiCloudService', create)
    answers = iter(['synthetic@example.invalid', 'wrong-secret', 'synthetic@example.invalid', 'new-secret'])
    monkeypatch.setattr('notesvault.terminal.Prompt.ask', lambda *a, **kw: next(answers))
    try:
        assert ui.login() and auth.connected
        assert len(attempts) == 2
        output = ui.console.file.getvalue()
        assert 'email and password' in output
        assert all(secret not in output for secret in ['private diagnostic', *attempts])
    finally:
        ui.tasks.close()


def test_terminal_verification_failure_can_restart_sign_in(tmp_path, monkeypatch):
    ui = terminal(tmp_path)
    auth = ICloudAuthenticationController(ui.app.store, Secrets())
    ui.app.authentication = auth
    first, second = Session(), Session()
    first.requires_2fa = True
    def fail(code):
        raise NotesAuthError('private diagnostic')
    first.validate_2fa_code = fail
    sessions = iter([first, second])
    monkeypatch.setattr('pyicloud.PyiCloudService', lambda *a, **kw: next(sessions))
    answers = iter(['synthetic@example.invalid', 'secret', '123456', 'synthetic@example.invalid', 'secret'])
    monkeypatch.setattr('notesvault.terminal.Prompt.ask', lambda *a, **kw: next(answers))
    monkeypatch.setattr('notesvault.terminal.Confirm.ask', lambda *a, **kw: True)
    try:
        assert ui.login() and auth.connected
        assert auth.session is second
        assert 'private diagnostic' not in ui.console.file.getvalue()
    finally:
        ui.tasks.close()


@pytest.mark.parametrize('expired', [True, False])
def test_fetch_auth_failure_preserves_backup_and_invalidates_only_expired_session(tmp_path, monkeypatch, expired):
    ui = terminal(tmp_path)
    ui.app.save_settings(str(tmp_path / 'vault'), '1', require_folder=True)
    provider, notes = cloud_provider(tmp_path)
    auth = SimpleNamespace(connected=True, session=provider.session, account=provider.account)
    auth.clear = lambda: setattr(auth, 'connected', False)
    ui.app.authentication = auth
    ui.app.provider_factory = ICloudNotesProvider
    try:
        ui.app.fetch(lambda _: None, FetchControl())
        paths = [* (tmp_path / 'vault').rglob('*.md'), tmp_path / 'vault/.git/notesvault-fetch.json',
                 ui.app.store.directory / 'backup-status.json']
        original = {p: p.read_bytes() for p in paths}
        notes.cursor = 'changed'
        def fail(*a, **kw):
            raise NotesAuthError('private diagnostic') if expired else ConnectionError('private diagnostic')
        monkeypatch.setattr(notes, 'get', fail)
        with pytest.raises(ReconnectRequired if expired else AppError):
            ui.fetch()
        assert auth.connected is not expired
        assert not ui.tasks.busy
        assert all(p.read_bytes() == value for p, value in original.items())
        ui.schedule()
        assert (ui.next_fetch is None) is expired
    finally:
        ui.tasks.close()


@pytest.mark.parametrize('cancel', [False, True])
def test_terminal_fetch_routes_to_login_after_keyboard_and_worker_cleanup(tmp_path, monkeypatch, cancel):
    ui = terminal(tmp_path)
    keys = iter(['y', '\n', 'q', '\n'])
    inside_keyboard = False
    @contextmanager
    def keyboard():
        nonlocal inside_keyboard
        inside_keyboard = True
        try:
            yield lambda: next(keys)
        finally:
            inside_keyboard = False
    monkeypatch.setattr('notesvault.terminal.keyboard', keyboard)
    monkeypatch.setattr(ui, 'setup', lambda: True)
    def fail(*args):
        raise ReconnectRequired('Sign in again')
    monkeypatch.setattr(ui.app, 'fetch', fail)
    attempts = []
    def login():
        assert not inside_keyboard and not ui.tasks.busy
        assert ui.next_fetch is None
        attempts.append(True)
        if cancel:
            raise KeyboardInterrupt()
        return True
    monkeypatch.setattr(ui, 'login', login)
    ui.run()
    assert attempts == [True]
    assert ui.tasks.closed
