"""Opt-in synthetic desktop check; outside the Qt-free pytest suite.

Run: .venv/Scripts/python.exe scripts/smoke_desktop.py
"""
import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import edifice as ed
from PySide6.QtCore import Qt, QEvent, QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QScrollArea

from notesvault.config_store import ConfigStoreController
from notesvault.gui.dashboard import Dashboard


class SyntheticAuthentication:
    connected = False
    account = ""

    def __init__(self, *args):
        pass

    def login(self, account, password):
        self.account = account
        return False

    def verify(self, code):
        assert code == "123456"
        self.connected = True

    def clear(self):
        self.connected = False

    def cancel(self):
        self.clear()


def main():
    qt = QApplication.instance() or QApplication([])
    failures = []
    with TemporaryDirectory() as temporary, patch("notesvault.application.ICloudAuthenticationController", SyntheticAuthentication):
        app = ed.App(Dashboard(ConfigStoreController(Path(temporary))), qapplication=qt)

        def popup():
            return next((w for w in qt.topLevelWidgets() if w.windowTitle() == "Connect iCloud" and w.isVisible()), None)

        def button(title):
            return next(w for w in qt.allWidgets() if isinstance(w, QPushButton) and w.text() == title and w.isVisible())

        def click(title):
            widget = button(title)
            event = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(widget.rect().center()),
                                QPointF(widget.mapToGlobal(widget.rect().center())),
                                Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                                Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(widget, event)

        async def check():
            try:
                await asyncio.sleep(0.3)
                assert any(isinstance(w, QScrollArea) for w in qt.allWidgets())
                click("Login")
                await asyncio.sleep(0.3)
                assert popup() is not None, "Login popup did not mount"
                assert popup().windowModality() == Qt.WindowModality.ApplicationModal
                click("Cancel setup")
                await asyncio.sleep(0.3)
                assert popup() is None
                click("Login")
                await asyncio.sleep(0.3)
                fields = popup().findChildren(QLineEdit)
                account = next(w for w in fields if w.placeholderText() == "name@example.com")
                password = next(w for w in fields if w.echoMode() == QLineEdit.EchoMode.Password)
                account.setText("synthetic@example.invalid")
                account.textEdited.emit(account.text())
                password.setText("synthetic-password")
                password.textEdited.emit(password.text())
                await asyncio.sleep(0.2)
                click("Sign in")
                await asyncio.sleep(0.4)
                code = next(w for w in popup().findChildren(QLineEdit) if w.placeholderText() == "Verification code")
                code.setText("123456")
                code.textEdited.emit(code.text())
                await asyncio.sleep(0.2)
                click("Verify")
                await asyncio.sleep(0.4)
                assert popup() is None, "Successful login must close popup"
                assert button("Disconnect iCloud").isEnabled()
            except Exception as exc:
                failures.append(exc)
            finally:
                app.stop()

        with app.start_loop() as loop:
            loop.create_task(check())
    if failures:
        raise failures[0]
    print("Desktop smoke passed: scroll container, popup, cancel, password, 2FA, successful closure.")


if __name__ == "__main__":
    main()
