"""Compose account, disk, and backup actions with dashboard-owned hook state."""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import edifice as ed

from ..backup_controller import fetch_backup
from ..backup_status_store import BackupStatusStore
from ..config_store import ConfigStoreController
from ..demo_provider import DemoProvider
from ..disk_vault_controller import DiskVaultController
from ..icloud_authentication_controller import ICloudAuthenticationController
from ..icloud_notes_provider import ICloudNotesProvider
from ..icloud_secret_store import SecretStoreController
from .authentication import AuthenticationComponent
from .folderinput import FolderInput
from .tasks import use_tasks


card_body = {"padding": 16, "border": "1px solid #41576a", "border-radius": 8, "margin": 6}
card_title = {"font-size": 20, "font-weight": "bold"}
danger_border = {"border": "1px solid #ef4444"}


@ed.component
def Dashboard(self, config_store: ConfigStoreController, is_demo=False):
    authentication = ed.use_memo(
        lambda: ICloudAuthenticationController(config_store, SecretStoreController()), ())
    window_ref = ed.use_ref()

    # Saved preferences have their own hook; drafts and runtime values never enter it.
    config, set_config = ed.use_state(config_store.load)
    logs, set_logs = ed.use_state(())
    error, set_error = ed.use_state("")

    def log_output(message):
        set_logs(lambda previous: (*previous, message)[-200:])

    active_task, task_progress, start_task, task_is_running, fetch_actions = use_tasks(
        window_ref, log_output, authentication.clear)
    busy = bool(active_task)

    # Authentication state. Credentials live only in the form and controller.
    connected, set_connected = ed.use_state(is_demo or authentication.connected)
    auth_step, set_auth_step = ed.use_state("idle")

    # Disk drafts are distinct from the last successful save.
    folder, set_folder = ed.use_state(config.backup_folder)
    interval, set_interval = ed.use_state(str(config.interval_minutes))
    attachments, set_attachments = ed.use_state(config.download_attachments)
    folder_requested, set_folder_requested = ed.use_state(False)
    attempted, set_attempted = ed.use_state(None)
    draft = (folder, interval, attachments)
    dirty = draft != (config.backup_folder, str(config.interval_minutes), config.download_attachments)

    # Fetch state: prerequisite continuation, results, and scheduling.
    backup_status, set_backup_status = ed.use_state(lambda: BackupStatusStore(config_store.directory).load())
    pending_fetch, set_pending_fetch = ed.use_state(False)
    resume_fetch, set_resume_fetch = ed.use_state(False)
    next_fetch, set_next_fetch = ed.use_state(None)
    setup_open = auth_step in ("login", "verify") or folder_requested

    def task_started():
        set_error("")
        set_next_fetch(None)
        set_resume_fetch(False)

    # Account actions delegate all authentication and credential persistence.
    def authentication_failed(message, step):
        set_error(message)
        set_connected(authentication.connected)
        set_auth_step(step)

    def login(account, password):
        def operation(progress):
            ready = authentication.login(account, password)
            return config_store.load(), ready

        def completed(result):
            saved, ready = result
            set_config(saved)
            set_connected(ready)
            set_auth_step("idle" if ready else "verify")
            log_output("iCloud connected." if ready else "iCloud verification required.")
            set_resume_fetch(True)

        if is_demo or not start_task("Signing in to iCloud", operation, completed,
                                     lambda message: authentication_failed(message, "login")):
            return False
        task_started()
        return True

    def connect():
        if task_is_running() or is_demo:
            return False
        if config.apple_id:
            return login(config.apple_id, "")
        set_auth_step("login")
        set_error("")
        set_next_fetch(None)
        return True

    def verify(code):
        def operation(progress):
            authentication.verify(code)
            return config_store.load()

        def completed(saved):
            set_config(saved)
            set_connected(authentication.connected)
            set_auth_step("idle")
            log_output("iCloud connected.")
            set_resume_fetch(True)

        if not start_task("Verifying iCloud code", operation, completed,
                          lambda message: authentication_failed(message, "verify")):
            return False
        task_started()
        return True

    def logout():
        def operation(progress):
            authentication.logout()
            return config_store.load()

        def completed(saved):
            set_config(saved)
            set_connected(False)
            set_auth_step("idle")
            set_pending_fetch(False)
            log_output("Disconnected. Local backups and Git history are preserved.")

        if is_demo or not start_task("Disconnecting iCloud", operation, completed,
                                     lambda message: authentication_failed(message, "idle")):
            return False
        task_started()
        return True

    def cancel_setup():
        def completed(_):
            set_connected(is_demo or authentication.connected)
            set_auth_step("idle")
            set_folder_requested(False)
            set_pending_fetch(False)
            log_output("Setup closed. Saved steps are preserved.")

        if not start_task("Closing setup", lambda progress: authentication.cancel(), completed, set_error):
            return False
        task_started()
        set_pending_fetch(False)
        return True

    # Disk actions delegate validation, repository preparation, and saving.
    def save_settings(*, fetch_after=False):
        def operation(progress):
            return DiskVaultController.save_configuration(
                config_store, folder, interval, require_folder=pending_fetch or fetch_after,
                download_attachments=attachments)

        def completed(saved):
            set_config(saved)
            set_folder_requested(False)
            log_output("Settings saved.")
            set_resume_fetch(True)

        if not start_task("Saving settings", operation, completed, set_error):
            return False
        task_started()
        if fetch_after:
            set_pending_fetch(True)
        return True

    async def autosave():
        if busy or not dirty or attempted == draft:
            return
        await asyncio.sleep(0.5)
        if save_settings():
            set_attempted(draft)

    ed.use_async(autosave, (draft, busy, dirty, attempted))
    ed.use_effect(lambda: set_folder(config.backup_folder), (config.backup_folder,))
    ed.use_effect(lambda: set_interval(str(config.interval_minutes)), (config.interval_minutes,))
    ed.use_effect(lambda: set_attachments(config.download_attachments), (config.download_attachments,))

    # Backup actions choose prerequisites/providers; the workflow owns fetch and disk I/O.
    def fetch_notes():
        if task_is_running() or setup_open:
            return False
        if not config.backup_folder or not (Path(config.backup_folder).expanduser() / ".git").is_dir():
            set_pending_fetch(True)
            set_folder_requested(True)
            # Also prepares a saved folder whose repository has not been initialized.
            return save_settings(fetch_after=True) if config.backup_folder else True
        if not connected:
            set_pending_fetch(True)
            return connect()

        def operation(progress, control):
            control.checkpoint()
            provider = DemoProvider() if is_demo else ICloudNotesProvider(authentication.session, authentication.account)
            return fetch_backup(config_store, provider, progress, control=control)

        def completed(result):
            status, backup = result
            set_backup_status(status)
            set_connected(is_demo or authentication.connected)
            for message in backup.warnings or ["Backup complete. Your local history is up to date."]:
                log_output(message)

        def failed(message):
            set_error(message)
            set_connected(is_demo or authentication.connected)

        def cancelled():
            set_pending_fetch(False)
            set_resume_fetch(False)
            set_connected(is_demo or authentication.connected)

        if not start_task("Fetching iCloud notes", operation, completed, failed,
                          cancellable=True, on_cancel=cancelled):
            return False
        task_started()
        return True

    def fetch_clicked(_):
        if dirty:
            save_settings(fetch_after=True)
        else:
            fetch_notes()

    def resume_pending_fetch():
        if resume_fetch and not busy:
            set_resume_fetch(False)
            if pending_fetch and not setup_open:
                set_pending_fetch(False)
                fetch_notes()

    ed.use_effect(resume_pending_fetch, (resume_fetch, pending_fetch, setup_open, busy))

    def schedule_fetch():
        ready = config.interval_minutes and connected and config.backup_folder and not setup_open and not busy
        set_next_fetch(datetime.now() + timedelta(minutes=config.interval_minutes) if ready else None)

    ed.use_effect(schedule_fetch, (config.interval_minutes, config.backup_folder, connected, setup_open, busy))

    async def scheduled_fetch():
        if next_fetch:
            await asyncio.sleep(max(0, (next_fetch - datetime.now()).total_seconds()))
            fetch_notes()

    ed.use_async(scheduled_fetch, (next_fetch,))

    with ed.Window(title="Notes Vault", _size_open=(1100, 760)).register_ref(window_ref):
        with ed.VBoxView():
            with ed.VBoxView(css_class="Danger" if not connected else "",
                             style={**card_body, **(danger_border if not connected else {})}):
                ed.Label("iCloud", style=card_title)
                AuthenticationComponent(
                    account=config.apple_id, phase="connected" if connected else auth_step,
                    on_login=login, on_verify=verify, on_connect=connect,
                    on_logout=logout, on_cancel=cancel_setup, enabled=not busy and not is_demo,
                    account_placeholder="Apple Account email", disconnected_text="No Apple Account connected",
                    logout_text="Disconnect iCloud",
                )

            with ed.VBoxView(css_class="Danger" if not config.backup_folder else "",
                             style={**card_body, **(danger_border if not config.backup_folder else {})}):
                ed.Label("Disk", style=card_title)
                FolderInput(folder=folder, on_change=set_folder, enabled=not busy)
                ed.Label("Changes save automatically after you stop typing.")
                ed.Label(f"Last backup: {backup_status.last_backup}")
                ed.Label(f"Next fetch: {next_fetch:%H:%M:%S}" if next_fetch else
                         "Manual fetching" if not config.interval_minutes else "Automatic fetch: paused")
                ed.Label("Automatic fetch interval in minutes (0 = manual only)")
                ed.TextInput(interval, on_change=set_interval, enabled=not busy)
                ed.CheckBox(checked=attachments, text="Download attachments", on_change=set_attachments, enabled=not busy)
                ed.Label("Off by default. Previously downloaded attachments remain in Git history.")
                if folder_requested:
                    ed.Label("Choose a backup folder to continue the fetch.")
                    ed.Button("Retry folder setup", enabled=not busy, on_click=lambda _: save_settings(fetch_after=True))
                    ed.Button("Cancel setup", enabled=not busy, on_click=lambda _: cancel_setup())
                ed.Button("Fetch iCloud now", enabled=not busy and not setup_open, on_click=fetch_clicked)

            with ed.VBoxView(style=card_body):
                ed.Label("Tasks", style=card_title)
                ed.Label(active_task or "No active tasks")
                if active_task:
                    ed.Label(task_progress or "Working…")
                if fetch_actions.state:
                    if fetch_actions.state == "pausing":
                        ed.Label("Pausing after the current request…")
                    elif fetch_actions.state == "paused":
                        ed.Label("Fetch paused")
                    elif fetch_actions.state == "cancelling":
                        ed.Label("Cancelling after the current request…")
                    elif fetch_actions.state == "saving":
                        ed.Label("Finishing local backup safely…")
                    with ed.HBoxView():
                        if fetch_actions.state in ("pausing", "paused"):
                            ed.Button("Resume fetch", on_click=lambda _: fetch_actions.resume())
                        else:
                            ed.Button("Pause fetch", enabled=fetch_actions.state == "running",
                                      on_click=lambda _: fetch_actions.pause())
                        ed.Button("Cancel fetch", enabled=fetch_actions.state in ("running", "pausing", "paused"),
                                  on_click=lambda _: fetch_actions.cancel())

            with ed.VBoxView(style=card_body):
                ed.Label("Logs", style=card_title)
                if error:
                    ed.Label(error)
                ed.Label(backup_status.last_result)
                with ed.VScrollView(style={"padding": 16}):
                    ed.Label("\n".join(reversed(logs)) or "No activity yet.")
