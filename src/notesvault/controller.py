"""Application workflows; event delivery is supplied by the desktop adapter."""
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from .backup import BackupRepository
from .config import ConfigStore, SecretStore
from .models import AppError
from .providers import DemoProvider, ICloudProvider
from .service import run_backup
from .setup import AccountSetup
from .state import DashboardState


@dataclass(frozen=True)
class TaskCompletion:
    future: Future
    after: Callable[[], None] | None
    error_step: str | None
    resume_fetch: bool


class BackupController:
    def __init__(self, config_store=None, is_demo=False, secrets=None, provider=None, *,
                 on_change, on_progress, on_completed):
        # Callbacks must queue worker notifications for delivery on the owner thread.
        self.on_change, self.on_progress, self.on_completed = on_change, on_progress, on_completed
        self.config_store = config_store or ConfigStore()
        self.secrets_store = secrets or SecretStore()
        self.is_demo = is_demo
        self.provider = provider or (DemoProvider() if is_demo else ICloudProvider(self.config_store.directory / "sessions"))
        settings = self.config_store.load()
        if is_demo:
            settings = replace(settings, apple_id="demo", backup_folder=str(self.config_store.directory / "backups"))
        self.state = DashboardState(settings, self.provider.connected)
        self.account = AccountSetup(self.config_store, self.secrets_store, self.provider)
        self._pending_fetch = False
        self._closed = False
        self._future = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notesvault")
        self._schedule_fetch()

    def _set(self, **changes):
        self.state = replace(self.state, **changes)
        self.on_change(self.state)

    def _schedule_fetch(self):
        settings = self.state.settings
        ready = (settings.interval_minutes and self.state.connected and settings.backup_folder
                 and not self.state.setup_step and not self.state.busy and not self._closed)
        self._set(next_fetch=datetime.now() + timedelta(minutes=settings.interval_minutes) if ready else None)

    def log_output(self, message):
        self._set(logs=(*self.state.logs, message)[-200:])

    def _start_task(self, name, operation, after=None, error_step=None, *, resume_fetch=False):
        if self.state.busy or self._closed:
            return False
        self._set(active_task=name, next_fetch=None, setup_error="")
        try:
            self._future = self.executor.submit(operation)
        except Exception:
            self._set(active_task="")
            self._schedule_fetch()
            raise
        self._future.add_done_callback(
            lambda future: self.on_completed(TaskCompletion(future, after, error_step, resume_fetch)))
        return True

    def finish_task(self, completion: TaskCompletion):
        # Only the owner thread consumes completion and changes application state.
        if self._closed or completion.future is not self._future:
            return
        succeeded = False
        try:
            settings, messages = completion.future.result()
            self._set(settings=settings)
            if completion.after:
                completion.after()
            for message in messages:
                self.log_output(message)
            succeeded = True
        except Exception as exc:
            message = str(exc) if isinstance(exc, AppError) else "Operation failed. Check the connection, folder permissions, and settings, then retry."
            self._set(setup_error=message, setup_step=completion.error_step or self.state.setup_step)
            self.log_output(message)
        finally:
            self._future = None
            self._set(active_task="", connected=self.provider.connected)
            self._schedule_fetch()
        if succeeded and completion.resume_fetch and self._pending_fetch and not self.state.setup_step:
            self._pending_fetch = False
            self.fetch_notes()

    def tick(self):
        if self.state.next_fetch and datetime.now() >= self.state.next_fetch:
            self.fetch_notes()

    def fetch_notes(self):
        if self.state.busy or self.state.setup_step or self._closed:
            return False
        folder = self.state.settings.backup_folder
        if not folder or (not self.is_demo and not (Path(folder).expanduser() / ".git").is_dir()):
            self._pending_fetch = True
            self._set(setup_step="folder", setup_error="", next_fetch=None)
            return True
        if not self.state.connected:
            self._pending_fetch = True
            return self.login_button()
        settings = self.state.settings

        def task():
            result = run_backup(self.provider, settings, self.config_store.directory / "staging", self.on_progress)
            updated = replace(settings, last_backup=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                              last_result=result.summary())
            self.config_store.save(updated)
            return updated, result.warnings or ["Backup complete. Your local history is up to date."]

        return self._start_task("Fetching iCloud notes", task)

    def save_settings(self, folder, interval, *, fetch_after=False):
        if self.state.busy or self._closed:
            return False
        if fetch_after:
            self._pending_fetch = True
        settings = self.state.settings

        def task():
            try:
                minutes = int(interval)
                if not 0 <= minutes <= 10080:
                    raise ValueError()
            except ValueError:
                raise AppError("Enter an interval from 0 to 10080 minutes.") from None
            path = Path(folder.strip()).expanduser().absolute() if folder.strip() else None
            if not path and settings.backup_folder:
                raise AppError("Choose a backup folder before replacing the current location.")
            if not path and self._pending_fetch:
                raise AppError("Choose a backup folder to continue the fetch.")
            if path:
                BackupRepository(path).initialize()
            updated = replace(settings, backup_folder=str(path) if path else "", interval_minutes=minutes)
            if updated != settings:
                self.config_store.save(updated)
            return updated, ["Settings saved."]

        after = (lambda: self._set(setup_step="")) if self.state.setup_step == "folder" else None
        return self._start_task("Saving settings", task, after, resume_fetch=True)

    def disconnect_icloud(self):
        settings = self.state.settings

        def task():
            self.secrets_store.delete(f"icloud:{settings.apple_id}")
            self.provider.logout()
            updated = replace(settings, apple_id="")
            self.config_store.save(updated)
            return updated, ["Disconnected. Local backups and Git history are preserved."]

        return False if self.is_demo else self._start_task("Disconnecting iCloud", task)

    def login_button(self):
        if self.state.busy or self.is_demo or self._closed:
            return False
        if not self.state.settings.apple_id:
            self._set(setup_step="login", setup_error="", next_fetch=None)
            return True
        return self.login_to_icloud(self.state.settings.apple_id, "")

    def login_to_icloud(self, account, password):
        def task():
            self.account.login(account, password)
            return self.config_store.load(), ["iCloud sign-in processed."]

        def after():
            self._set(setup_step="" if self.provider.connected else "verify")

        return False if self.is_demo else self._start_task("Signing in to iCloud", task, after, "login", resume_fetch=True)

    def verify_code(self, code):
        def task():
            self.account.verify(code)
            return self.config_store.load(), ["iCloud connected."]

        return self._start_task("Verifying iCloud code", task, lambda: self._set(setup_step=""), "verify", resume_fetch=True)

    def cancel_setup(self):
        if self.state.busy or self._closed:
            return False
        self._pending_fetch = False
        settings = self.state.settings

        def task():
            self.account.cancel()
            return settings, ["Account setup closed. Saved steps are preserved."]

        return self._start_task("Closing account setup", task, lambda: self._set(setup_step=""))

    def cleanup(self):
        self._closed = True
        self.executor.shutdown(wait=True)
        self.account.clear()
