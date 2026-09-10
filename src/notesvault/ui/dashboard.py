from typing import Callable

from PySide6.QtCore import Qt
import edifice as ed

from notesvault.ui.state import DashboardState

from .folderinput import FolderInput
from .controller import NotesVaultController

from PySide6.QtWidgets import QLineEdit

card_body = {"padding": 16, "border": "1px solid #41576a", "border-radius": 8, "margin": 6}
card_title = {"font-size": 20, "font-weight": "bold"}
danger_border = {"border": "1px solid #ef4444"}

@ed.component
def PasswordInput(
        self,
        text: str = "",
        placeholder_text: str | None = None,
        on_change: Callable[[str], None] | None = None,
        on_edit_finish: Callable[[], None] | None = None,
        **kwargs,
    ):
    ref = ed.use_ref()
    def configure():
        ref().underlying.setEchoMode(QLineEdit.EchoMode.Password)

    ed.use_effect(configure, ())

    ed.TextInput(text, 
        placeholder_text=placeholder_text, 
        on_change=on_change, 
        on_edit_finish=on_edit_finish,
        enabled=kwargs.get("enabled", True)
    ).register_ref(ref)


@ed.component
def ICloudComponent(self, controller: NotesVaultController, state: DashboardState):
    settings = state.settings
    
    icloud_loggedin = not state.connected

    account, set_account = ed.use_state(state.settings.apple_id)
    password, set_password = ed.use_state("")
    code, set_code = ed.use_state("")
    step = state.setup_step

    def submit_login(_):
        controller.login_to_icloud(account, password)
        set_password("")

    def submit_verify(_):
        controller.verify_vertification_code(code)
        set_code("")

    with ed.VBoxView(css_class="Danger" if icloud_loggedin else "",
                        style={**card_body, **(danger_border if icloud_loggedin else {})}):
        ed.Label("iCloud", style=card_title)

        if bool(settings.apple_id):
            ed.Label(settings.apple_id)
            
        elif step != "verify":
            ed.Label("No Apple Account connected")
            ed.TextInput(account, 
                on_change=set_account, 
                placeholder_text="Apple ID"
            )
            PasswordInput(password, on_change=set_password, placeholder_text="Password") # todo: add echo mode for password
            ed.Button("Login", enabled=not state.busy and not state.connected and not controller.is_demo,
                on_click=submit_login)
            
        elif step == "verify":
            ed.TextInput(code, 
                on_change=set_code, 
                placeholder_text="Verification Code"
            )
            ed.Button("Verify", enabled=not state.busy and not controller.is_demo,
                on_click=submit_verify)
            

@ed.component
def DiskComponent(self, controller: NotesVaultController, state: DashboardState):
    settings = state.settings
    folder_missing = not settings.backup_folder.strip()
    folder, set_folder = ed.use_state(state.settings.backup_folder)
    interval, set_interval = ed.use_state(str(state.settings.interval_minutes))

    ed.use_effect(lambda: set_folder(state.settings.backup_folder), (state.settings.backup_folder,))

    with ed.VBoxView(css_class="Danger" if folder_missing else "",
                        style={**card_body, **(danger_border if folder_missing else {})}):
        ed.Label("Disk", style=card_title)
        FolderInput(folder=folder, on_change=set_folder, enabled=not state.busy)
        ed.Label(f"Last backup: {settings.last_backup}")
        
        ed.Label(f"Next fetch: {state.next_fetch:%H:%M:%S}" if state.next_fetch else
                "Manual fetching" if not settings.interval_minutes else "Automatic fetch: paused")

        
        ed.Label("Automatic fetch interval in minutes (0 = manual only)")
        ed.TextInput(interval, on_change=set_interval, enabled=not state.busy)

        ed.Button("Fetch iCloud now", enabled=not state.busy,
            on_click=lambda _: controller.fetch_notes())

@ed.component
def Dashboard(self, controller: NotesVaultController):
    state, set_state = ed.use_state(controller.state)
    window_ref = ed.use_ref()
    settings = state.settings

    def subscribe():
        controller.changed.connect(set_state)
        controller.window = window_ref().underlying
        controller.window.installEventFilter(controller)
        return lambda: controller.changed.disconnect(set_state)
    
    ed.use_effect(subscribe, ())    
    def label(text):
        ed.Label(text, text_format=Qt.TextFormat.PlainText, selectable=True, word_wrap=True)

    with ed.Window(title="Notes Vault", _size_open=(1100, 760)).register_ref(window_ref):
        with ed.VBoxView():
            with ed.VBoxView():
                ed.Label("Notes Vault", style={"font-size": 28, "font-weight": "bold"})
            with ed.HBoxView():
                ICloudComponent(controller=controller, state=state)
                DiskComponent(controller=controller, state=state)

            with ed.VBoxView(style=card_body):
                ed.Label("Logs", style=card_title)
                label("Working..." if state.busy else "Ready")
                label(settings.last_result)
                with ed.VScrollView(style={"padding": 16}):
                    label("\n".join(reversed(state.logs)) or "No activity yet.")
