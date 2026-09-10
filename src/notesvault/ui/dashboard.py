import asyncio

import edifice as ed
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit

from ..state import DashboardState
from .controller import NotesVaultController
from .folderinput import FolderInput


card_body = {"padding": 16, "border": "1px solid #41576a", "border-radius": 8, "margin": 6}
card_title = {"font-size": 20, "font-weight": "bold"}
danger_border = {"border": "1px solid #ef4444"}


def label(text):
    ed.Label(text, text_format=Qt.TextFormat.PlainText, selectable=True, word_wrap=True)


@ed.component
def PasswordInput(self, text, on_change, enabled=True):
    ref = ed.use_ref()

    def configure():
        ref().underlying.setEchoMode(QLineEdit.EchoMode.Password)

    ed.use_effect(configure, ())
    ed.TextInput(text, placeholder_text="Password (blank uses saved password)",
                 on_change=on_change, enabled=enabled).register_ref(ref)


@ed.component
def ICloudComponent(self, controller: NotesVaultController, state: DashboardState):
    account, set_account = ed.use_state(state.settings.apple_id)
    password, set_password = ed.use_state("")
    code, set_code = ed.use_state("")
    step = state.setup_step
    enabled = not state.busy and not controller.is_demo
    disconnected = not state.connected
    ed.use_effect(lambda: set_account(state.settings.apple_id), (state.settings.apple_id,))

    def clear_secrets():
        set_password("")
        set_code("")

    ed.use_effect(clear_secrets, (step, state.connected))

    def submit_login(_):
        controller.login_to_icloud(account, password)
        set_password("")

    def submit_verify(_):
        controller.verify_code(code)
        set_code("")

    def cancel(_):
        clear_secrets()
        controller.cancel_setup()

    with ed.VBoxView(css_class="Danger" if disconnected else "",
                     style={**card_body, **(danger_border if disconnected else {})}):
        ed.Label("iCloud", style=card_title)
        label(state.settings.apple_id or "No Apple Account connected")
        if step == "verify":
            label("Enter the verification code from your trusted device or phone.")
            ed.TextInput(code, on_change=set_code, placeholder_text="Verification code", enabled=enabled)
            ed.Button("Verify", enabled=enabled, on_click=submit_verify)
        elif disconnected and (step == "login" or not state.settings.apple_id):
            ed.TextInput(account, on_change=set_account, placeholder_text="Apple Account email", enabled=enabled)
            PasswordInput(password, on_change=set_password, enabled=enabled)
            ed.Button("Login", enabled=enabled, on_click=submit_login)
        elif disconnected:
            ed.Button("Login", enabled=enabled, on_click=lambda _: controller.login_button())
        else:
            label("Connected")
            ed.Button("Disconnect iCloud", enabled=enabled, on_click=lambda _: controller.disconnect_icloud())
        if step in ("login", "verify"):
            ed.Button("Cancel setup", enabled=not state.busy, on_click=cancel)


@ed.component
def DiskComponent(self, controller: NotesVaultController, state: DashboardState):
    settings = state.settings
    folder_missing = not settings.backup_folder.strip()
    folder, set_folder = ed.use_state(settings.backup_folder)
    interval, set_interval = ed.use_state(str(settings.interval_minutes))
    attempted, set_attempted = ed.use_state(None)
    ed.use_effect(lambda: set_folder(settings.backup_folder), (settings.backup_folder,))
    ed.use_effect(lambda: set_interval(str(settings.interval_minutes)), (settings.interval_minutes,))
    dirty = (folder, interval) != (settings.backup_folder, str(settings.interval_minutes))

    async def autosave():
        if state.busy or not dirty or attempted == (folder, interval):
            return
        await asyncio.sleep(0.5)
        if controller.save_settings(folder, interval):
            set_attempted((folder, interval))

    ed.use_async(autosave, (folder, interval, state.busy, dirty, attempted))

    def fetch(_):
        if dirty:
            controller.save_settings(folder, interval, fetch_after=True)
        else:
            controller.fetch_notes()

    with ed.VBoxView(css_class="Danger" if folder_missing else "",
                     style={**card_body, **(danger_border if folder_missing else {})}):
        ed.Label("Disk", style=card_title)
        FolderInput(folder=folder, on_change=set_folder, enabled=not state.busy)
        label("Changes save automatically after you stop typing.")
        label(f"Last backup: {settings.last_backup}")
        label(f"Next fetch: {state.next_fetch:%H:%M:%S}" if state.next_fetch else
              "Manual fetching" if not settings.interval_minutes else "Automatic fetch: paused")
        label("Automatic fetch interval in minutes (0 = manual only)")
        ed.TextInput(interval, on_change=set_interval, enabled=not state.busy)
        if state.setup_step == "folder":
            label("Choose a backup folder to continue the fetch.")
            ed.Button("Cancel setup", enabled=not state.busy, on_click=lambda _: controller.cancel_setup())
        ed.Button("Fetch iCloud now", enabled=not state.busy and not state.setup_step, on_click=fetch)


@ed.component
def TasksViewerComponent(self, state: DashboardState):
    with ed.VBoxView(style=card_body):
        ed.Label("Tasks", style=card_title)
        label(state.active_task or "No active tasks")


@ed.component
def Dashboard(self, controller: NotesVaultController):
    state, set_state = ed.use_state(controller.state)
    window_ref = ed.use_ref()

    def subscribe():
        controller.changed.connect(set_state)
        controller.window = window_ref().underlying
        controller.window.installEventFilter(controller)
        return lambda: controller.changed.disconnect(set_state)

    ed.use_effect(subscribe, ())

    with ed.Window(title="Notes Vault", _size_open=(1100, 760)).register_ref(window_ref):
        with ed.VBoxView():
            ed.Label("Notes Vault", style={"font-size": 28, "font-weight": "bold"})
            with ed.HBoxView():
                ICloudComponent(controller=controller, state=state)
                DiskComponent(controller=controller, state=state)
            TasksViewerComponent(state=state)
            with ed.VBoxView(style=card_body):
                ed.Label("Logs", style=card_title)
                if state.setup_error:
                    label(state.setup_error)
                label(state.settings.last_result)
                with ed.VScrollView(style={"padding": 16}):
                    label("\n".join(reversed(state.logs)) or "No activity yet.")
