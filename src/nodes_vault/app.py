import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from .backup import BackupRepository
from .config import ConfigStore, SecretStore
from .github import push_repository, validate_repository
from .models import AppError
from .providers import DemoProvider, ICloudProvider
from .service import run_backup


class SetupScreen(ModalScreen[dict | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, settings, demo=False):
        super().__init__()
        self.settings = settings
        self.demo = demo

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="setup-dialog"):
            yield Label("BACKUP SETTINGS", classes="eyebrow")
            yield Label("1 · Connect iCloud")
            yield Input(value=self.settings.apple_id, placeholder="Apple Account email", id="apple-id", disabled=self.demo)
            yield Input(placeholder="Password · leave blank to use saved credential", password=True, id="password", disabled=self.demo)
            yield Label("2 · Choose a local backup folder")
            yield Input(value=self.settings.backup_folder, placeholder="C:\\Users\\you\\Documents\\NotesBackup", id="folder")
            yield Label("3 · GitHub · optional, leave empty to skip")
            yield Input(value=self.settings.github_repo, placeholder="owner/private-repository", id="repo", disabled=self.demo)
            yield Input(placeholder="Token · saved in OS credential store", password=True, id="token", disabled=self.demo)
            yield Label("Automatic fetch interval · minutes (0 = manual only)")
            yield Input(value=str(self.settings.interval_minutes), type="integer", id="interval")
            yield Static("Scheduling runs while this app is open. Closing it stops the schedule.", classes="muted")
            yield Static("", id="form-error", markup=False)
            with Horizontal(classes="actions"):
                yield Button("Save & connect", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    @on(Button.Pressed, "#cancel")
    def action_cancel(self):
        self.dismiss(None)

    @on(Button.Pressed, "#save")
    def save(self):
        values = {key: self.query_one(f"#{key}", Input).value.strip()
                  for key in ("apple-id", "folder", "repo", "interval", "token")}
        values["password"] = self.query_one("#password", Input).value
        try:
            if not values["folder"]:
                raise ValueError("Choose a local backup folder.")
            minutes = int(values["interval"])
            if not 0 <= minutes <= 10080:
                raise ValueError("Choose an interval between 0 and 10080 minutes.")
        except ValueError as exc:
            self.query_one("#form-error", Static).update(str(exc))
            return
        self.query_one("#password", Input).value = ""
        self.query_one("#token", Input).value = ""
        self.dismiss(values)


class CodeScreen(ModalScreen[str | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self):
        with Vertical(id="code-dialog"):
            yield Label("Verify your Apple Account")
            yield Static("Enter the code sent to your trusted device or phone.")
            yield Input(placeholder="Verification code", password=True, id="code")
            with Horizontal(classes="actions"):
                yield Button("Verify", variant="primary", id="verify")
                yield Button("Cancel", id="cancel-code")

    @on(Button.Pressed, "#verify")
    def verify(self):
        self.dismiss(self.query_one("#code", Input).value)

    @on(Button.Pressed, "#cancel-code")
    def action_cancel(self):
        self.dismiss(None)


class NotesVaultApp(App):
    TITLE = "Notes Vault"
    SUB_TITLE = "Your notes. Your history."
    BINDINGS = [("f", "fetch", "Fetch now"), ("s", "settings", "Settings"), ("q", "quit", "Quit")]
    CSS = """
    Screen { background: #101820; color: #e5edf4; }
    Header { background: #172631; }
    Footer { background: #172631; }
    #body { max-width: 120; width: 100%; margin: 1 2; height: 1fr; }
    #intro { height: auto; margin-bottom: 1; }
    .eyebrow { color: #6ed7c5; text-style: bold; margin-bottom: 1; }
    .muted { color: #a0b3c0; height: auto; }
    #accounts { height: auto; }
    .card { width: 1fr; height: auto; min-height: 8; border: round #34515e; padding: 1 2; margin-right: 1; }
    .card Static { height: auto; margin-bottom: 1; }
    #backup { height: auto; border: round #34515e; padding: 1 2; margin-top: 1; }
    #backup Static { height: auto; margin-bottom: 1; }
    .actions { height: auto; margin-top: 1; }
    Button { margin-right: 1; }
    #result { height: auto; padding: 1 0; }
    #activity { height: auto; min-height: 3; color: #6ed7c5; }
    #setup-dialog { width: 76; max-height: 95%; height: auto; background: #172631; border: round #6ed7c5; padding: 1 2; }
    #setup-dialog Label { margin-top: 1; }
    #setup-dialog Input { margin-bottom: 1; }
    #form-error { color: #ffad9f; height: auto; }
    SetupScreen, CodeScreen { align: center middle; background: #000000 65%; }
    #code-dialog { width: 64; height: auto; background: #172631; border: round #6ed7c5; padding: 2; }
    #code-dialog Input { margin-top: 1; }
    """

    def __init__(self, store: ConfigStore | None = None, demo=False, secrets=None):
        super().__init__()
        self.store = store or ConfigStore()
        self.settings = self.store.load()
        self.secrets = secrets or SecretStore()
        self.demo = demo
        self.provider = DemoProvider() if demo else ICloudProvider(self.store.directory / "sessions")
        if demo:
            self.settings.apple_id = "demo"
            self.settings.github_repo = ""
            self.settings.backup_folder = str(self.store.directory / "backups")
        self.busy = False
        self.next_fetch = None

    def compose(self):
        yield Header()
        with VerticalScroll(id="body"):
            yield Static("APPLE NOTES  /  LOCAL BACKUP" + ("  /  DEMO" if self.demo else ""), classes="eyebrow")
            yield Static("A local copy. A complete history of every saved version.", id="intro")
            with Horizontal(classes="actions"):
                yield Button("Fetch now", variant="primary", id="fetch")
                yield Button("Retry push", id="push")
                yield Button("Settings", id="settings")
            with Horizontal(id="accounts"):
                with Vertical(classes="card"):
                    yield Static("iCloud", classes="eyebrow")
                    yield Static("Not connected", id="icloud-state", markup=False)
                    yield Button("Disconnect iCloud", id="logout-icloud", disabled=self.demo)
                with Vertical(classes="card"):
                    yield Static("GitHub · optional", classes="eyebrow")
                    yield Static("Local backups only", id="github-state", markup=False)
                    yield Button("Disconnect GitHub", id="logout-github", disabled=self.demo)
            with Container(id="backup"):
                yield Static("BACKUP", classes="eyebrow")
                yield Static("", id="folder-state", markup=False)
                yield Static("", id="schedule-state", markup=False)
                yield Static("", id="result", markup=False)
                yield Static("Ready when you are.", id="activity", markup=False)
            yield Static("Automatic fetching runs while this terminal is open. Local Git history preserves deleted notes.", classes="muted")
        yield Footer()

    def on_mount(self):
        self.refresh_dashboard()
        self.set_interval(1, self.tick)
        if not self.demo and self.settings.apple_id:
            self.reconnect()
        elif not self.demo and (not self.settings.apple_id or not self.settings.backup_folder):
            self.call_after_refresh(self.action_settings)
        else:
            self.schedule_next()

    def schedule_next(self):
        self.next_fetch = (datetime.now() + timedelta(minutes=self.settings.interval_minutes)
            if self.settings.interval_minutes and self.provider.connected and self.settings.backup_folder else None)

    def refresh_dashboard(self):
        state = "Connected" if self.provider.connected else "Not connected · open Settings"
        self.query_one("#icloud-state", Static).update(f"{self.settings.apple_id or 'No account'}\n{state}")
        self.query_one("#github-state", Static).update(self.settings.github_repo or "Not connected · local backups only")
        self.query_one("#folder-state", Static).update(self.settings.backup_folder or "Choose a backup folder in Settings")
        self.query_one("#result", Static).update(f"Last backup: {self.settings.last_backup}\n{self.settings.last_result}")
        for button in self.query(Button):
            button.disabled = self.busy
        self.query_one("#fetch", Button).disabled = self.busy or not self.provider.connected or not self.settings.backup_folder
        self.query_one("#push", Button).disabled = self.busy or not self.settings.github_repo or not self.settings.backup_folder
        self.query_one("#logout-icloud", Button).disabled = self.busy or self.demo or not self.settings.apple_id
        self.query_one("#logout-github", Button).disabled = self.busy or self.demo or not self.settings.github_repo
        self.tick_schedule()

    def tick_schedule(self):
        text = f"Next fetch: {self.next_fetch:%H:%M:%S}" if self.next_fetch else "Automatic fetch: paused" if self.settings.interval_minutes else "Manual fetching"
        self.query_one("#schedule-state", Static).update(text)

    def tick(self):
        if self.screen is not self.screen_stack[0]:
            return
        self.tick_schedule()
        if self.next_fetch and datetime.now() >= self.next_fetch and not self.busy:
            self.action_fetch()

    def activity(self, message):
        self.query_one("#activity", Static).update(message)

    def start_operation(self):
        if self.busy:
            return False
        self.busy = True
        self.refresh_dashboard()
        return True

    def finish_operation(self):
        self.busy = False
        self.schedule_next()
        self.refresh_dashboard()

    @work
    async def reconnect(self):
        if not self.start_operation():
            return
        try:
            password = await asyncio.to_thread(self.secrets.get, f"icloud:{self.settings.apple_id}")
            if password:
                self.activity("Reconnecting iCloud…")
                await self.connect(self.settings.apple_id, password)
            else:
                self.activity("Open Settings to connect iCloud.")
        except AppError as exc:
            self.activity(str(exc))
        except Exception:
            self.activity("Could not restore the saved session. Open Settings to reconnect.")
        finally:
            self.finish_operation()

    async def connect(self, account, password):
        ready = await asyncio.to_thread(self.provider.login, account, password)
        while not ready:
            code = await self.push_screen_wait(CodeScreen())
            if not code:
                await asyncio.to_thread(self.provider.logout)
                raise AppError("Sign-in cancelled. Reconnect in Settings when ready.")
            try:
                await asyncio.to_thread(self.provider.verify, code)
                ready = True
            except AppError as exc:
                self.notify(str(exc), severity="error")
        await asyncio.to_thread(self.secrets.set, f"icloud:{account}", password)
        self.activity("iCloud connected. Fetch now to create your local backup.")

    def action_settings(self):
        if not self.busy:
            self.push_screen(SetupScreen(self.settings, self.demo), self.setup_finished)

    def setup_finished(self, values):
        if values:
            self.save_settings(values)

    @work
    async def save_settings(self, values):
        if not self.start_operation():
            return
        try:
            folder = str(Path(values["folder"]).expanduser().resolve())
            await asyncio.to_thread(BackupRepository(Path(folder)).initialize)
            repo = values["repo"] if not self.demo else ""
            if repo:
                token = values["token"] or await asyncio.to_thread(self.secrets.get, "github")
                await asyncio.to_thread(validate_repository, repo, token or "")
                await asyncio.to_thread(self.secrets.set, "github", token)
            elif self.settings.github_repo:
                await asyncio.to_thread(self.secrets.delete, "github")
            account = values["apple-id"].lower()
            old_account = self.settings.apple_id
            self.settings.backup_folder = folder
            self.settings.github_repo = repo
            self.settings.interval_minutes = int(values["interval"])
            if not self.demo:
                if old_account and old_account != account:
                    await asyncio.to_thread(self.provider.logout)
                    await asyncio.to_thread(self.secrets.delete, f"icloud:{old_account}")
                self.settings.apple_id = account
            self.store.save(self.settings)
            self.activity("Settings saved.")
            if account and not self.demo:
                password = values["password"] or await asyncio.to_thread(self.secrets.get, f"icloud:{account}")
                if password:
                    self.activity("Connecting iCloud…")
                    await self.connect(account, password)
                else:
                    self.activity("Settings saved. Enter your iCloud password to connect.")
        except AppError as exc:
            self.activity(str(exc))
        except Exception:
            self.activity("Settings could not be saved. Check the folder and account configuration.")
        finally:
            values["password"] = values["token"] = ""
            self.finish_operation()

    def action_fetch(self):
        if not self.busy:
            self.fetch_notes()

    @work
    async def fetch_notes(self):
        if not self.start_operation():
            return
        try:
            result = await asyncio.to_thread(run_backup, self.provider, self.settings, self.secrets,
                self.store.directory / "staging", lambda message: self.call_from_thread(self.activity, message))
            self.settings.last_backup = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.settings.last_result = (f"{result.added} added · {result.updated} updated · {result.deleted} deleted · {result.skipped} skipped"
                f"\nLocal Git: {result.commit}\nGitHub: {result.push}")
            self.store.save(self.settings)
            self.activity("\n".join(result.warnings) or "Backup complete. Your local history is up to date.")
        except AppError as exc:
            self.activity(str(exc))
        except Exception:
            self.activity("Backup could not finish. Check disk space and folder permissions before retrying.")
        finally:
            self.finish_operation()

    @work
    async def retry_push(self):
        if not self.start_operation():
            return
        try:
            if not self.settings.github_repo:
                raise AppError("Connect a GitHub repository in Settings first.")
            token = await asyncio.to_thread(self.secrets.get, "github")
            if not token:
                raise AppError("Reconnect GitHub in Settings.")
            def publish():
                repository = BackupRepository(Path(self.settings.backup_folder))
                with repository.locked():
                    return push_repository(repository.root, self.settings.github_repo, token)
            self.activity("Publishing existing Git history…")
            self.activity(await asyncio.to_thread(publish))
        except AppError as exc:
            self.activity(str(exc))
        except Exception:
            self.activity("Publishing failed. Your local backup is unchanged.")
        finally:
            self.finish_operation()

    @work
    async def disconnect(self, github=False):
        if not self.start_operation():
            return
        try:
            if github:
                await asyncio.to_thread(self.secrets.delete, "github")
                self.settings.github_repo = ""
            else:
                await asyncio.to_thread(self.secrets.delete, f"icloud:{self.settings.apple_id}")
                await asyncio.to_thread(self.provider.logout)
                self.settings.apple_id = ""
            self.store.save(self.settings)
            self.activity("Disconnected. Local backups and Git history are preserved.")
        except Exception:
            self.activity("Could not fully disconnect. Retry to clear the account's saved credentials and session.")
        finally:
            self.finish_operation()

    @on(Button.Pressed)
    def handle_button(self, event):
        actions = {"fetch": self.action_fetch, "settings": self.action_settings,
                   "push": self.retry_push, "logout-icloud": self.disconnect,
                   "logout-github": lambda: self.disconnect(github=True)}
        if event.button.id in actions and not self.busy:
            actions[event.button.id]()

    def action_quit(self):
        if self.busy:
            self.notify("Wait for the current operation to finish before quitting.")
        else:
            self.exit()
