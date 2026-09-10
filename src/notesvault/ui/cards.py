"""Dashboard sections with display props and callbacks, independent of controllers."""
import edifice as ed
from PySide6.QtWidgets import QApplication

from ..activity_log import log_text
from .components import Card, Text, Action, INPUT
from .folderinput import FolderInput


@ed.component
def AccountCard(self, account, connected, is_demo, enabled, on_connect, on_logout):
    with Card("iCloud", "Demo account" if is_demo else "Connected" if connected else "Sign in to start backing up"):
        if account:
            Text(account)
        if not is_demo:
            Action("Disconnect iCloud" if connected else "Login",
                   lambda _: on_logout() if connected else on_connect(), enabled=enabled)


@ed.component
def BackupCard(self, folder, interval, attachments, on_folder, on_interval, on_attachments,
               enabled, save_state, folder_requested, on_continue, on_cancel,
               on_fetch, can_fetch, next_fetch, last_backup):
    with Card("Backup", "Your notes stay on this computer."):
        Text("Backup folder")
        FolderInput(folder=folder, on_change=on_folder, enabled=enabled)
        with ed.HBoxView(style={"margin-top": 8}):
            Text("Fetch every (minutes)")
            ed.TextInput(interval, on_change=on_interval, enabled=enabled,
                         style={**INPUT, "width": 70}, tool_tip="0 means manual backups only")
        ed.CheckBox(checked=attachments, text="Download attachments", on_change=on_attachments,
                    enabled=enabled, style={"margin-top": 5, "margin-bottom": 5})
        Text(save_state, style={"font-size": 11})
        if folder_requested:
            Text("Choose a folder above. Your fetch will continue after setup.")
            with ed.HBoxView():
                Action("Continue", lambda _: on_continue(), enabled=enabled)
                Action("Cancel setup", lambda _: on_cancel(), enabled=enabled)
        Text(f"Last backup: {last_backup}")
        Text(next_fetch)
        Action("Fetch now", on_fetch, enabled=can_fetch, primary=True)


@ed.component
def TaskCard(self, active_task, progress, controls, last_result, error, retry, on_retry):
    state_text = {"running": "Fetching", "pausing": "Pausing after the current request…",
                  "paused": "Paused — resume whenever you are ready",
                  "cancelling": "Cancelling after the current request…",
                  "saving": "Saving your backup. Please wait."}
    with Card("Tasks", state_text.get(controls.state, active_task or "No active tasks")):
        if active_task:
            Text(active_task, style={"font-weight": "bold"})
            Text(progress or "Working…")
            if controls.state != "paused":
                ed.ProgressBar(0, min_value=0, max_value=0, style={"height": 5, "margin-bottom": 8})
        if controls.state:
            if controls.state == "saving":
                Text("Pause and Cancel are unavailable while local history is being saved.")
            with ed.HBoxView():
                if controls.state in ("pausing", "paused"):
                    Action("Resume fetch", lambda _: controls.resume())
                else:
                    Action("Pause fetch", lambda _: controls.pause(), enabled=controls.state == "running")
                Action("Cancel fetch", lambda _: controls.cancel(),
                       enabled=controls.state in ("running", "pausing", "paused"))
        if error:
            Text(error, style={"font-weight": "bold"})
        if retry and not active_task:
            Action("Retry fetch", on_retry, primary=True)
        Text("Last result", style={"font-size": 11, "margin-top": 8})
        Text(last_result)


@ed.component
def LogCard(self, entries, on_clear):
    editor = ed.use_ref()
    text = log_text(tuple(reversed(entries)))

    def configure():
        editor().underlying.setReadOnly(True)

    ed.use_effect(configure, ())

    with Card("Logs"):
        ed.TextInputMultiline(text, placeholder_text="Your activity will appear here.",
                              style={**INPUT, "height": 170, "margin-top": 8}).register_ref(editor)
        with ed.HBoxView():
            Action("Copy logs", lambda _: QApplication.clipboard().setText(text), enabled=bool(entries))
            Action("Clear logs", lambda _: on_clear(), enabled=bool(entries))
