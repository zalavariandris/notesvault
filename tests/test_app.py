import asyncio
import os
from dataclasses import replace
from datetime import datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import edifice as ed
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QPushButton, QLabel, QLineEdit

from notesvault.config import ConfigStore
from notesvault.models import AppError
from notesvault.ui.controller import Dashboard, NotesVaultApp


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def run_gui(controller, qapp, scenario):
    errors = []
    controller.gui = ed.App(Dashboard(controller), qapplication=qapp)
    async def exercise():
        try:
            await asyncio.sleep(0.15)
            await asyncio.wait_for(scenario(), timeout=15)
        except BaseException as exc:
            errors.append(exc)
        finally:
            controller.gui.stop()
    try:
        with controller.gui.start_loop() as loop:
            loop.create_task(exercise())
    finally:
        controller.cleanup()
    if errors:
        raise errors[0]


def button(qapp, title):
    return next(w for w in qapp.allWidgets() if isinstance(w, QPushButton) and w.text() == title and w.isVisible())


async def enter(qapp, name, value):
    field = next(w for w in qapp.allWidgets() if isinstance(w, QLineEdit)
                 and w.objectName() == name and w.isVisible())
    field.setText(value)
    field.textEdited.emit(value)
    await asyncio.sleep(0.03)
    return field


def test_login_form_verification_and_password_masking(tmp_path, qapp):
    from types import SimpleNamespace
    values = {}
    secrets = SimpleNamespace(get=values.get, set=lambda key, value: values.update({key: value}))
    provider = SimpleNamespace(connected=False)
    def login(account, password):
        assert account == "synthetic@example.invalid"
        assert password == "synthetic-password"
        return False
    def verify(code):
        if code != "123456":
            raise AppError("Invalid code")
        provider.connected = True
    provider.login, provider.verify = login, verify
    controller = NotesVaultApp(ConfigStore(tmp_path), secrets=secrets, provider=provider)
    async def scenario():
        assert controller.state.setup_step == ""
        QTest.mouseClick(button(qapp, "Login"), Qt.MouseButton.LeftButton)
        await asyncio.sleep(0.05)
        await enter(qapp, "apple-id", "synthetic@example.invalid")
        password = await enter(qapp, "password", "synthetic-password")
        assert password.echoMode() == QLineEdit.EchoMode.Password
        QTest.mouseClick(button(qapp, "Sign in"), Qt.MouseButton.LeftButton)
        await finished(controller)
        assert controller.state.setup_step == "verify"
        code = await enter(qapp, "verification-code", "wrong")
        assert code.echoMode() == QLineEdit.EchoMode.Normal
        QTest.mouseClick(button(qapp, "Verify code"), Qt.MouseButton.LeftButton)
        await finished(controller)
        assert controller.state.setup_error == "Invalid code"
        await enter(qapp, "verification-code", "123456")
        QTest.mouseClick(button(qapp, "Verify code"), Qt.MouseButton.LeftButton)
        await finished(controller)
        assert controller.state.connected
        assert controller.state.setup_step == ""
        assert values["icloud:synthetic@example.invalid"] == "synthetic-password"
        assert all("synthetic-password" not in line for line in controller.state.logs)
    run_gui(controller, qapp, scenario)


def test_fetch_prompts_for_folder_then_resumes(tmp_path, qapp):
    from notesvault.providers import DemoProvider
    controller = NotesVaultApp(ConfigStore(tmp_path / "config"), provider=DemoProvider())
    async def scenario():
        assert controller.state.setup_step == ""
        assert button(qapp, "Fetch iCloud now").isEnabled()
        QTest.mouseClick(button(qapp, "Fetch iCloud now"), Qt.MouseButton.LeftButton)
        await asyncio.sleep(0.05)
        assert controller.state.setup_step == "folder"
        await enter(qapp, "backup-folder", str(tmp_path / "backup"))
        QTest.mouseClick(button(qapp, "Save folder and continue"), Qt.MouseButton.LeftButton)
        for _ in range(300):
            await asyncio.sleep(0.02)
            if not controller.state.busy and controller.state.settings.last_backup != "Never":
                break
        assert "3 added" in controller.state.settings.last_result
        assert list((tmp_path / "backup" / "notes").rglob("*.md"))
        assert controller.state.setup_step == ""
    run_gui(controller, qapp, scenario)


def test_login_button_uses_saved_credentials(tmp_path, qapp):
    from types import SimpleNamespace
    from notesvault.config import Settings
    store = ConfigStore(tmp_path)
    store.save(Settings(apple_id="synthetic@example.invalid"))
    provider = SimpleNamespace(connected=False)
    def login(account, password):
        assert password == "saved-password"
        provider.connected = True
        return True
    provider.login = login
    secrets = SimpleNamespace(get=lambda _: "saved-password", set=lambda *a: None)
    controller = NotesVaultApp(store, provider=provider, secrets=secrets)
    async def scenario():
        QTest.mouseClick(button(qapp, "Login"), Qt.MouseButton.LeftButton)
        await finished(controller)
        assert controller.state.connected
        assert controller.state.setup_step == ""
    run_gui(controller, qapp, scenario)


async def finished(controller):
    while controller.state.busy:
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.05)


def test_edifice_dashboard_fetch_repeat_and_labels(tmp_path, qapp):
    controller = NotesVaultApp(ConfigStore(tmp_path), is_demo=True)
    async def scenario():
        labels = {w.text() for w in qapp.allWidgets() if isinstance(w, QLabel)}
        assert {"iCloud", "Disk", "GitHub", "Logs", "Settings"} <= labels
        assert not button(qapp, "Login").isEnabled()
        assert not button(qapp, "Publish to GitHub").isEnabled()
        QTest.mouseClick(button(qapp, "Fetch iCloud now"), Qt.MouseButton.LeftButton)
        assert controller.state.busy
        assert not controller.fetch_notes()  # No overlapping operations.
        event = QCloseEvent()
        assert controller.eventFilter(None, event)
        assert not event.isAccepted()
        await finished(controller)
        assert "3 added" in controller.state.settings.last_result
        assert list((tmp_path / "backups" / "notes").rglob("*.md"))
        QTest.mouseClick(button(qapp, "Fetch iCloud now"), Qt.MouseButton.LeftButton)
        await finished(controller)
        assert "No changes" in controller.state.settings.last_result
        assert button(qapp, "Fetch iCloud now").isEnabled()
    run_gui(controller, qapp, scenario)


def test_edifice_settings_save_and_validation(tmp_path, qapp):
    controller = NotesVaultApp(ConfigStore(tmp_path), is_demo=True)
    async def scenario():
        fields = [w for w in qapp.allWidgets() if isinstance(w, QLineEdit) and w.isVisible()]
        interval = next(w for w in fields if w.text() == "30")
        # Exercise the Qt textEdited signal used by Edifice's controlled input.
        interval.setText("0")
        interval.textEdited.emit("0")
        await asyncio.sleep(0.05)
        QTest.mouseClick(button(qapp, "Save settings"), Qt.MouseButton.LeftButton)
        await finished(controller)
        assert controller.state.settings.interval_minutes == 0
        assert controller.config_store.load().interval_minutes == 0
        assert controller.state.next_fetch is None
        controller.save_settings(str(tmp_path / "backups"), "invalid")
        await finished(controller)
        assert controller.state.settings.interval_minutes == 0
        assert "interval" in controller.state.logs[-1]
    run_gui(controller, qapp, scenario)


def test_failed_fetch_recovers_controls(tmp_path, qapp, monkeypatch):
    def fail(*args):
        raise AppError("Synthetic download failure")
    monkeypatch.setattr("notesvault.ui.app.run_backup", fail)
    controller = NotesVaultApp(ConfigStore(tmp_path), is_demo=True)
    async def scenario():
        QTest.mouseClick(button(qapp, "Fetch iCloud now"), Qt.MouseButton.LeftButton)
        await finished(controller)
        assert "Synthetic download failure" in controller.state.logs
        assert controller.state.settings.last_backup == "Never"
        assert button(qapp, "Fetch iCloud now").isEnabled()
    run_gui(controller, qapp, scenario)


def test_schedule_and_pause(tmp_path, qapp):
    controller = NotesVaultApp(ConfigStore(tmp_path), is_demo=True)
    async def scenario():
        controller._set(next_fetch=datetime.now() - timedelta(seconds=1))
        controller.tick()
        await finished(controller)
        assert "3 added" in controller.state.settings.last_result
        controller.save_settings(str(tmp_path / "backups"), "0")
        await finished(controller)
        assert controller.state.next_fetch is None
    run_gui(controller, qapp, scenario)


def test_login_opens_edifice_form(tmp_path, qapp):
    controller = NotesVaultApp(ConfigStore(tmp_path))
    async def scenario():
        assert button(qapp, "Login").isEnabled()
        QTest.mouseClick(button(qapp, "Login"), Qt.MouseButton.LeftButton)
        assert controller.state.setup_step == "login"
        await asyncio.sleep(0.05)
        assert button(qapp, "Sign in").isEnabled()
    run_gui(controller, qapp, scenario)


def test_disconnect_pauses_schedule_and_clears_saved_account(tmp_path, qapp):
    from types import SimpleNamespace
    from notesvault.config import Settings
    deleted = []
    provider = SimpleNamespace(connected=True)
    provider.logout = lambda: setattr(provider, "connected", False)
    store = ConfigStore(tmp_path)
    store.save(Settings(apple_id="synthetic@example.invalid", backup_folder=str(tmp_path / "backup")))
    controller = NotesVaultApp(store, provider=provider, secrets=SimpleNamespace(delete=deleted.append))
    async def scenario():
        QTest.mouseClick(button(qapp, "Disconnect iCloud"), Qt.MouseButton.LeftButton)
        await finished(controller)
        assert deleted == ["icloud:synthetic@example.invalid"]
        assert not controller.state.connected
        assert controller.state.next_fetch is None
        assert store.load().apple_id == ""
        assert button(qapp, "Login").isEnabled()
        assert button(qapp, "Fetch iCloud now").isEnabled()
    run_gui(controller, qapp, scenario)


def test_publish_failure_preserves_local_backup(tmp_path, qapp, monkeypatch):
    from types import SimpleNamespace
    from notesvault.backup import git
    def fail(*args):
        raise AppError("Synthetic publishing failure")
    monkeypatch.setattr("notesvault.ui.app.push_repository", fail)
    controller = NotesVaultApp(ConfigStore(tmp_path), is_demo=True,
                              secrets=SimpleNamespace(get=lambda _: "synthetic-token"))
    async def scenario():
        controller.fetch_notes()
        await finished(controller)
        head = git(tmp_path / "backups", "rev-parse", "HEAD").stdout
        controller._set(settings=replace(controller.state.settings, github_repo="owner/private"))
        await asyncio.sleep(0.05)
        QTest.mouseClick(button(qapp, "Publish to GitHub"), Qt.MouseButton.LeftButton)
        await finished(controller)
        assert "Synthetic publishing failure" in controller.state.logs
        assert git(tmp_path / "backups", "rev-parse", "HEAD").stdout == head
        assert button(qapp, "Publish to GitHub").isEnabled()
    run_gui(controller, qapp, scenario)
