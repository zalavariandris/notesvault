"""Compose account, disk, and backup actions with dashboard-owned hook state."""
import asyncio
from datetime import datetime, timedelta

import edifice as ed

from ..application import Application
from ..backup_status_store import BackupStatusStore
from ..activity_log import append_entry
from .cards import AccountCard, BackupCard, TaskCard, LogCard
from .components import Text
from .sign_in import SignInWindow
from .tasks import use_tasks


@ed.component
def Dashboard(self, application: Application):
    config_store = application.store
    authentication = application.authentication
    window_ref = ed.use_ref()

    # Saved preferences have their own hook; drafts and runtime values never enter it.
    config, set_config = ed.use_state(config_store.load)
    logs, set_logs = ed.use_state(())
    error, set_error = ed.use_state("")

    def log_output(message):
        set_logs(lambda previous: append_entry(previous, message, datetime.now()))

    active_task, task_progress, start_task, task_is_running, fetch_actions = use_tasks(
        window_ref, log_output, authentication.clear)
    busy = bool(active_task)

    # Authentication state. Credentials live only in the form and controller.
    connected, set_connected = ed.use_state(authentication.connected)
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
    fetch_failed, set_fetch_failed = ed.use_state(False)
    setup_open = auth_step in ("login", "verify") or folder_requested

    def task_started():
        set_error("")
        set_fetch_failed(False)
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

        if not start_task("Signing in to iCloud", operation, completed,
                                     lambda message: authentication_failed(message, "login")):
            return False
        task_started()
        return True

    def connect():
        if task_is_running():
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

        if not start_task("Disconnecting iCloud", operation, completed,
                                     lambda message: authentication_failed(message, "idle")):
            return False
        task_started()
        return True

    def cancel_setup():
        def completed(_):
            set_connected(authentication.connected)
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
            return application.save_settings(
                folder, interval, require_folder=pending_fetch or fetch_after,
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
        if busy or auth_step in ("login", "verify") or not dirty or attempted == draft:
            return
        await asyncio.sleep(0.5)
        if save_settings():
            set_attempted(draft)

    ed.use_async(autosave, (draft, busy, dirty, attempted, auth_step))
    ed.use_effect(lambda: set_folder(config.backup_folder), (config.backup_folder,))
    ed.use_effect(lambda: set_interval(str(config.interval_minutes)), (config.interval_minutes,))
    ed.use_effect(lambda: set_attachments(config.download_attachments), (config.download_attachments,))

    # Backup actions choose prerequisites/providers; the workflow owns fetch and disk I/O.
    def fetch_notes():
        if task_is_running() or setup_open:
            return False
        if application.prerequisite() == "folder":
            set_pending_fetch(True)
            set_folder_requested(True)
            # Also prepares a saved folder whose repository has not been initialized.
            return save_settings(fetch_after=True) if config.backup_folder else True
        if not authentication.connected:
            set_connected(False)
            set_pending_fetch(True)
            return connect()

        def operation(progress, control):
            return application.fetch(progress, control)

        def completed(result):
            status, backup = result
            set_backup_status(status)
            set_connected(authentication.connected)
            for message in backup.warnings or ["Backup complete. Your local history is up to date."]:
                log_output(message)

        def failed(message):
            set_fetch_failed(True)
            set_error(message)
            set_connected(authentication.connected)

        def cancelled():
            set_pending_fetch(False)
            set_resume_fetch(False)
            set_connected(authentication.connected)

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

    save_state = ("Saving preferences…" if active_task == "Saving settings" else
                  "Preferences need attention. Check the message below." if dirty and attempted == draft and error else
                  "Changes will save automatically…" if dirty else "Preferences saved · 0 minutes = manual only")
    schedule_text = (f"Next fetch: {next_fetch:%H:%M:%S}" if next_fetch else
                     "Manual fetching" if not config.interval_minutes else "Automatic fetching paused until ready")

    with ed.Window(title="Notes Vault", _size_open=(520, 860)).register_ref(window_ref):
        with ed.VScrollView(style={"padding": 16, "align": "top"}):
            # Text("Notes Vault", style={"padding": 16, "font-size": 26, "font-weight": "bold"})
            # Text("Apple Notes, with a local history.", style={"padding": 16, "margin-bottom": 14})
            AccountCard(
                account=config.apple_id, 
                connected=connected, 
                enabled=not busy and not setup_open, 
                on_connect=connect, 
                on_logout=logout)
            
            BackupCard(
                folder=folder, 
                interval=interval, 
                attachments=attachments,
                on_folder=set_folder, 
                on_interval=set_interval, 
                on_attachments=set_attachments,
                enabled=not busy and auth_step == "idle", 
                save_state=save_state,
                folder_requested=folder_requested, 
                on_continue=lambda: save_settings(fetch_after=True),
                on_cancel=cancel_setup, 
                on_fetch=fetch_clicked, 
                can_fetch=not busy and not setup_open,
                next_fetch=schedule_text, 
                last_backup=backup_status.last_backup)
            TaskCard(
                active_task=active_task, 
                progress=task_progress, 
                controls=fetch_actions,
                last_result=backup_status.last_result, 
                error=error if auth_step == "idle" else "",
                retry=fetch_failed and not setup_open, 
                on_retry=fetch_clicked)
            LogCard(
                entries=logs, 
                on_clear=lambda: set_logs(()))
            
        # A component must have one root; popups occupy a slot inside that root.
        if auth_step in ("login", "verify"):
            SignInWindow(account=authentication.account or config.apple_id, phase=auth_step,
                        busy=busy, operation=active_task, error=error,
                        on_login=login, on_verify=verify, on_cancel=cancel_setup)
