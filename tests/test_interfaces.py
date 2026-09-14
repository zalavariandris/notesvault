from io import StringIO
from contextlib import contextmanager
import subprocess
import sys
from threading import Event
import time
from types import SimpleNamespace

import pytest
from rich.console import Console

from notesvault.application import Application
from notesvault.config_store import ConfigStoreController
from notesvault.fetch_control import FetchControl
from notesvault.models import AppError, ConfigModel
from notesvault.tui.tui import TerminalUI


def terminal(tmp_path, authentication=None):
    app = Application(ConfigStoreController(tmp_path / "settings"), is_demo=authentication is None,
                      authentication=authentication)
    return TerminalUI(app, Console(file=StringIO(), width=100))


def test_shared_setup_and_repeat_backup(tmp_path):
    ui = terminal(tmp_path)
    assert ui.app.prerequisite() == "folder"
    ui.app.save_settings(str(tmp_path / "vault"), "0", require_folder=True)
    assert ui.app.prerequisite() == "ready"
    _, first = ui.app.fetch(lambda _: None, FetchControl())
    _, second = ui.app.fetch(lambda _: None, FetchControl())
    assert first.added == 3
    assert second.added == second.updated == second.deleted == 0
    assert second.commit == "No changes"
    ui.tasks.close()


def test_terminal_saved_login_verification_retry(tmp_path, monkeypatch):
    calls = []
    auth = SimpleNamespace(connected=False, clear=lambda: calls.append("clear"), cancel=lambda: calls.append("cancel"))
    def login(account):
        calls.append(account)
        return False
    def verify(code):
        calls.append(code)
        if code == "bad":
            raise AppError("Code rejected")
        auth.connected = True
    auth.login, auth.verify = login, verify
    ui = terminal(tmp_path, auth)
    ui.app.store.save(ConfigModel(apple_id="synthetic@example.invalid"))
    codes = iter(["bad", "123456"])
    monkeypatch.setattr("notesvault.tui.tui.Prompt.ask", lambda *a, **kw: next(codes))
    monkeypatch.setattr("notesvault.tui.tui.Confirm.ask", lambda *a, **kw: True)
    assert ui.login()
    assert calls == ["synthetic@example.invalid", "bad", "123456"]
    ui.tasks.close()


def test_terminal_cancel_clears_pending_auth(tmp_path, monkeypatch):
    calls = []
    auth = SimpleNamespace(connected=False, login=lambda account: False,
                           cancel=lambda: calls.append("cancel"), clear=lambda: calls.append("clear"))
    ui = terminal(tmp_path, auth)
    ui.app.store.save(ConfigModel(apple_id="synthetic@example.invalid"))
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr("notesvault.tui.tui.Prompt.ask", interrupt)
    with pytest.raises(KeyboardInterrupt):
        ui.login()
    assert calls == ["cancel", "clear"]
    assert ui.app.store.load().apple_id == "synthetic@example.invalid"
    ui.tasks.close()


def test_terminal_cancel_waits_for_worker_and_releases_task(tmp_path, monkeypatch):
    ui = terminal(tmp_path)
    started = Event()
    def fetch(progress, control):
        started.set()
        while control.state != "cancelling":
            time.sleep(0.01)
        control.checkpoint()
    monkeypatch.setattr(ui.app, "fetch", fetch)
    ui.fetch(lambda: "q" if started.is_set() else "")
    assert ui.quitting
    assert not ui.tasks.busy
    assert any("cancelled" in entry.message for entry in ui.logs)
    ui.tasks.close()


def test_terminal_quit_during_save_finishes_save(tmp_path, monkeypatch):
    ui = terminal(tmp_path)
    saving, released, completed = Event(), Event(), Event()
    def fetch(progress, control):
        control.begin_save()
        saving.set()
        assert released.wait(3)
        assert control.state == "saving"
        completed.set()
        return None, SimpleNamespace(summary=lambda: "Saved", warnings=[])
    def key():
        if saving.is_set():
            released.set()
            return "q"
        return ""
    monkeypatch.setattr(ui.app, "fetch", fetch)
    ui.fetch(key)
    assert completed.is_set() and ui.quitting and not ui.tasks.busy
    ui.tasks.close()


def test_terminal_saved_login_failure_uses_masked_password(tmp_path, monkeypatch):
    calls = []
    auth = SimpleNamespace(connected=False, cancel=lambda: None, clear=lambda: None)
    def login(account, password=""):
        calls.append((account, password))
        if not password:
            raise AppError("Enter password")
        auth.connected = True
        return True
    auth.login = login
    ui = terminal(tmp_path, auth)
    ui.app.store.save(ConfigModel(apple_id="synthetic@example.invalid"))
    def prompt(label, **kwargs):
        if label == "Password":
            assert kwargs["password"] is True
            return "synthetic-password"
        return "synthetic@example.invalid"
    monkeypatch.setattr("notesvault.tui.tui.Prompt.ask", prompt)
    assert ui.login()
    assert calls == [("synthetic@example.invalid", ""), ("synthetic@example.invalid", "synthetic-password")]
    assert "synthetic-password" not in ui.console.file.getvalue()
    ui.tasks.close()


def test_terminal_plain_text_and_schedule(tmp_path):
    ui = terminal(tmp_path)
    ui.app.save_settings(str(tmp_path / "vault"), "1")
    ui.log("[red]synthetic[/red]")
    ui.console.print(ui.render())
    assert "[red]synthetic[/red]" in ui.console.file.getvalue()
    ui.schedule()
    assert ui.next_fetch is not None
    ui.app.save_settings(str(tmp_path / "vault"), "0")
    ui.schedule()
    assert ui.next_fetch is None
    ui.tasks.close()


def test_tui_import_does_not_import_qt():
    result = subprocess.run([sys.executable, "-c", "import notesvault.tui; import sys; assert not any(k.startswith(('edifice', 'PySide6')) for k in sys.modules)"], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_tui_rejects_redirected_input():
    result = subprocess.run([sys.executable, "-m", "notesvault", "--demo", "--tui"], input="", capture_output=True, text=True, timeout=15)
    assert result.returncode == 1
    assert "interactive terminal" in result.stdout


def test_cancelled_reconnection_resets_terminal_schedule(tmp_path, monkeypatch):
    ui = terminal(tmp_path)
    attempts = iter([True, False])
    keys = iter(["f", "q"])
    schedules = []
    @contextmanager
    def keyboard():
        yield lambda: next(keys)
    monkeypatch.setattr("notesvault.tui.tui.keyboard", keyboard)
    monkeypatch.setattr(ui, "setup", lambda: next(attempts))
    monkeypatch.setattr(ui, "schedule", lambda: schedules.append("scheduled"))
    ui.run()
    assert len(schedules) == 2  # Startup and cancelled reconnection, before quitting.
    assert ui.tasks.closed
