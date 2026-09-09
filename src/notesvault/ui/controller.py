"""PyEdifice desktop dashboard and background-operation controller."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
import warnings

import edifice as ed

from PySide6.QtCore import QCoreApplication, QObject, Signal, Slot, QTimer, QEvent, Qt
from PySide6.QtWidgets import QApplication

from ..backup import BackupRepository
from ..config import ConfigStore, SecretStore, Settings
from ..github import push_repository, validate_repository
from ..models import AppError
from ..providers import DemoProvider, ICloudProvider
from ..service import run_backup
from ..setup import AccountSetup


from .state import DashboardState


class NotesVaultController(QObject):
    changed = Signal(object)
    progress = Signal(str)
    completed = Signal(object)

    def __init__(self, config_store=None, is_demo=False, secrets=None, provider=None):
        super().__init__()
        self.config_store = config_store or ConfigStore()
        self.secrets_store = secrets or SecretStore()
        self.is_demo = is_demo
        self.provider = provider or (DemoProvider() if is_demo else ICloudProvider(self.config_store.directory / "sessions"))
        settings = self.config_store.load()
        if is_demo:
            settings = replace(settings, apple_id="demo", github_repo="",
                               backup_folder=str(self.config_store.directory / "backups"))
        self.state = DashboardState(settings, self.provider.connected)
        self.account = AccountSetup(self.config_store, self.secrets_store, self.provider)
        self._pending_fetch = False
        self._error_step = None
        self._after_operation = None
        self.gui = None
        self.window = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notesvault")
        self.progress.connect(self.log_output)
        self.completed.connect(self._finish)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self._schedule_fetch()

    def _set(self, **changes):
        self.state = replace(self.state, **changes)
        self.changed.emit(self.state)

    def _schedule_fetch(self):
        settings = self.state.settings
        next_fetch = (datetime.now() + timedelta(minutes=settings.interval_minutes)
                      if settings.interval_minutes and self.state.connected and settings.backup_folder and not self.state.setup_step else None)
        self._set(next_fetch=next_fetch)

    @Slot(str)
    def log_output(self, message):
        self._set(logs=(*self.state.logs, message)[-200:])

    def _start_task(self, operation, after=None, error_step=None):
        if self.state.busy:
            return False
        self._after_operation = after
        self._error_step = error_step
        self._set(busy=True, next_fetch=None, setup_error="")
        self.executor.submit(operation).add_done_callback(self.completed.emit)
        return True

    @Slot(object)
    def _finish(self, future):
        try:
            settings, messages = future.result()
            self._set(settings=settings)
            if self._after_operation:
                self._after_operation()
            for message in messages:
                self.log_output(message)
        except AppError as exc:
            self._set(setup_error=str(exc), setup_step=self._error_step or self.state.setup_step)
            self.log_output(str(exc))
        except Exception:
            self._set(setup_error="Operation failed. Check the connection and settings, then retry.",
                      setup_step=self._error_step or self.state.setup_step)
            self.log_output("Operation failed. Check connection, folder permissions, and account settings; then retry.")
        finally:
            self._after_operation = None
            self._set(busy=False, connected=self.provider.connected)
            self._schedule_fetch()
            if self._pending_fetch and not self.state.setup_step and self.state.connected:
                self._pending_fetch = False
                QTimer.singleShot(0, self.fetch_notes)

    def tick(self):
        if self.state.next_fetch and datetime.now() >= self.state.next_fetch and not self.state.busy:
            self.fetch_notes()

    def fetch_notes(self):
        if self.state.busy or self.state.setup_step:
            return False
        if not self._folder_ready() and not (self.is_demo and self.state.settings.backup_folder):
            self._pending_fetch = True
            self._set(setup_step="folder", setup_error="", next_fetch=None)
            return True
        if not self.state.connected:
            self._pending_fetch = True
            return self.login_button()
        settings = self.state.settings
        def task():
            result = run_backup(self.provider, settings, self.secrets_store,
                                self.config_store.directory / "staging", self.progress.emit)
            updated = replace(settings, last_backup=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                last_result=f"{result.added} added | {result.updated} updated | {result.deleted} deleted | {result.skipped} skipped"
                            f"\nLocal Git: {result.commit}\nGitHub: {result.push}")
            self.config_store.save(updated)
            return updated, result.warnings or ["Backup complete. Your local history is up to date."]
        return self._start_task(task)

    def save_settings(self, folder, interval):
        settings = self.state.settings
        def task():
            try:
                minutes = int(interval)
                if not folder.strip() or not 0 <= minutes <= 10080:
                    raise ValueError()
            except ValueError:
                raise AppError("Choose a backup folder and an interval from 0 to 10080 minutes.") from None
            path = Path(folder.strip()).expanduser().absolute()
            BackupRepository(path).initialize()
            updated = replace(settings, backup_folder=str(path), interval_minutes=minutes)
            self.config_store.save(updated)
            return updated, ["Settings saved."]
        return self._start_task(task, after=(lambda: self._set(setup_step="" if self.state.connected or not self._pending_fetch else "login"))
                           if self.state.setup_step == "folder" else None)

    def publish_to_github(self):
        settings = self.state.settings
        def task():
            if not settings.github_repo or not settings.backup_folder:
                raise AppError("Configure a local backup folder and private GitHub repository first.")
            token = self.secrets_store.get("github")
            if not token:
                raise AppError("Reconnect GitHub through Account setup.")
            repository = BackupRepository(Path(settings.backup_folder))
            with repository.locked():
                message = push_repository(repository.root, settings.github_repo, token)
            return settings, [message]
        return self._start_task(task)

    def disconnect_icloud(self):
        settings = self.state.settings
        def task():
            self.secrets_store.delete(f"icloud:{settings.apple_id}")
            self.provider.logout()
            updated = replace(settings, apple_id="")
            self.config_store.save(updated)
            return updated, ["Disconnected. Local backups and Git history are preserved."]
        return False if self.is_demo else self._start_task(task)

    def disconnect_github(self):
        settings = self.state.settings
        def task():
            self.secrets_store.delete("github")
            updated = replace(settings, github_repo="")
            self.config_store.save(updated)
            return updated, ["Disconnected. Local backups and Git history are preserved."]
        return False if self.is_demo else self._start_task(task)

    def _folder_ready(self):
        folder = self.state.settings.backup_folder
        return bool(folder) and (Path(folder).expanduser() / ".git").is_dir()

    def account_setup(self):
        if self.state.busy or self.is_demo:
            return False
        self._set(setup_step="login", setup_error="", next_fetch=None)
        return True

    def login_button(self):
        if self.state.busy or self.is_demo:
            warnings.warn("Login button pressed while busy or in demo mode.")
            return False
        if not self.state.settings.apple_id:
            warnings.warn("Login button pressed without an Apple ID configured.")
            return self.account_setup()
        return self.login_to_icloud(self.state.settings.apple_id, "")

    def login_to_icloud(self, account, password):
        def task():
            self.account.login(account, password)
            return self.config_store.load(), ["iCloud sign-in processed."]
        def after():
            step = "" if self.provider.connected else "verify"
            self._set(setup_step=step)
        return self._start_task(task, after, error_step="login")

    def verify_vertification_code(self, code):
        def task():
            self.account.verify(code)
            return self.config_store.load(), ["iCloud connected."]
        return self._start_task(task, lambda: self._set(setup_step=""))

    def connect_to_github(self, repo, token):
        settings = self.state.settings
        def task():
            credential = token or self.secrets_store.get("github") or ""
            validate_repository(repo.strip(), credential)
            self.secrets_store.set("github", credential)
            updated = replace(settings, github_repo=repo.strip())
            self.config_store.save(updated)
            return updated, ["Private GitHub repository connected."]
        return self._start_task(task, lambda: self._set(setup_step=""))

    def cancel_setup(self):
        if self.state.busy:
            return False
        self._pending_fetch = False
        def task():
            self.account.cancel()
            return self.config_store.load(), ["Account setup closed. Saved steps are preserved."]
        return self._start_task(task, lambda: self._set(setup_step=""))

    def finish_setup(self):
        if not self.state.busy:
            self._set(setup_step="", setup_error="")
            self._schedule_fetch()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Close and self.state.busy:
            self.log_output("Wait for the current task to finish before closing.")
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    def cleanup(self):
        self.timer.stop()
        self.executor.shutdown(wait=True)
        self.account.clear()
        if self.window is not None:
            self.window.hide()
            self.window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.window = None
