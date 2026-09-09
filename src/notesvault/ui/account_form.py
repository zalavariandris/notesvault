import edifice as ed
from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QLineEdit
from PySide6.QtCore import Qt

@ed.component
def FormInput(self, text, on_change, name, secret=False, enabled=True):
    ref = ed.use_ref()
    def configure():
        ref().underlying.setObjectName(name)
        ref().underlying.setEchoMode(QLineEdit.EchoMode.Password if secret else QLineEdit.EchoMode.Normal)
    ed.use_effect(configure, (secret,))
    ed.TextInput(text, on_change=on_change, enabled=enabled).register_ref(ref)


@ed.component
def AccountForm(self, controller: NotesVaultApp, state: DashboardState):
    account, set_account = ed.use_state(state.settings.apple_id)
    password, set_password = ed.use_state("")
    code, set_code = ed.use_state("")
    folder, set_folder = ed.use_state(state.settings.backup_folder or str(Path.home() / "Documents" / "NotesBackup"))
    repo, set_repo = ed.use_state(state.settings.github_repo)
    token, set_token = ed.use_state("")
    step = state.setup_step
    def submit_login(_):
        controller.login(account, password)
        set_password("")

    def submit_verify(_):
        controller.verify(code)
        set_code("")

    def submit_github(_):
        controller.connect_github(repo, token)
        set_token("")

    def browse(_):
        selected = QFileDialog.getExistingDirectory(controller.window, "Choose backup folder", folder)
        if selected:
            set_folder(selected)
            
    with ed.VBoxView(style={"padding": 28, "min-width": 420}):
        ed.Label("Account setup", style={"font-size": 26, "font-weight": "bold"})
        if step == "login":
            ed.Label("Sign in to iCloud")
            ed.Label("Apple Account email")
            FormInput(account, set_account, "apple-id", enabled=not state.busy)
            ed.Label("Password (leave blank to use the saved credential)")
            FormInput(password, set_password, "password", secret=True, enabled=not state.busy)
            ed.Button("Sign in", on_click=submit_login, enabled=not state.busy)
            
        elif step == "verify":
            ed.Label("Verify your Apple Account")
            ed.Label("Enter the code sent to your trusted device or phone.")
            FormInput(code, set_code, "verification-code", enabled=not state.busy)
            ed.Button("Verify code", on_click=submit_verify, enabled=not state.busy)

        elif step == "folder":
            ed.Label("Choose a local backup folder")
            ed.Label("Choose a folder separate from this application's source repository.")
            FormInput(folder, set_folder, "backup-folder", enabled=not state.busy)
            ed.Button("Browse...", on_click=browse, enabled=not state.busy)
            ed.Button("Save folder and continue", on_click=lambda _: controller.save_settings(folder, str(state.settings.interval_minutes)),
                      enabled=not state.busy)
            
        elif step == "github":
            ed.Label("Connect GitHub (optional)")
            ed.Label("Private repository (owner/name)")
            FormInput(repo, set_repo, "github-repo", enabled=not state.busy)
            ed.Label("Token (leave blank to use the saved credential)")
            FormInput(token, set_token, "github-token", secret=True, enabled=not state.busy)
            ed.Button("Connect GitHub", on_click=submit_github, enabled=not state.busy)
            ed.Button("Skip / keep existing", on_click=lambda _: controller.finish_setup(), enabled=not state.busy)

        ed.Label("Working..." if state.busy else state.setup_error,
                 text_format=Qt.TextFormat.PlainText, word_wrap=True)
        
        ed.Button("Cancel setup", on_click=lambda _: controller.cancel_setup(), enabled=not state.busy)