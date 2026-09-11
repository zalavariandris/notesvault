"""Rich terminal adapter. No Qt imports and no backup or credential storage logic."""
from contextlib import contextmanager
from datetime import datetime
import os
from queue import Empty, SimpleQueue
import sys
import time

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.text import Text

from ..activity_log import append_entry, log_text
from ..application import Application
from ..backup_status_store import BackupStatusStore
from ..fetch_control import FetchCancelled, FetchControl
from ..models import AppError
from ..task_manager import TaskManager


@contextmanager
def keyboard():
    """Poll single keys while Live refreshes; always restore the terminal mode."""
    if os.name == "nt":
        import msvcrt

        def read():
            if not msvcrt.kbhit():
                return ""
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                msvcrt.getwch()
                return ""
            return key.lower()

        yield read
    else:
        import select
        import termios
        import tty
        descriptor = sys.stdin.fileno()
        previous = termios.tcgetattr(descriptor)
        try:
            tty.setcbreak(descriptor)
            yield lambda: os.read(descriptor, 1).decode(errors="ignore").lower() if select.select([descriptor], [], [], 0)[0] else ""
        finally:
            termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


class TerminalUI:
    def __init__(self, application, console=None):
        self.app = application
        self.console = console or Console()
        self.console = console or Console(width=80)
        self.tasks = TaskManager()
        self.logs = ()
        self.next_fetch = None
        self.quitting = False

    def log(self, message):
        self.logs = append_entry(self.logs, message, datetime.now())

    def report(self, exc):
        message = str(exc) if isinstance(exc, AppError) else "Operation failed. Check connection, folder permissions, and settings, then retry."
        self.log(message)
        self.console.print(Text(message, style="red"))

    def settings(self):
        config = self.app.store.load()
        self.console.print("Backup settings (Ctrl+C cancels)")
        folder = Prompt.ask("Local backup folder", default=config.backup_folder, console=self.console)
        interval = Prompt.ask("Fetch interval in minutes (0 = manual)", default=str(config.interval_minutes), console=self.console)
        attachments = Confirm.ask("Download attachments?", default=config.download_attachments, console=self.console)
        self.app.save_settings(folder, interval, require_folder=True, download_attachments=attachments)
        self.log("Settings saved.")

    def login(self):
        if self.app.connected:
            return True
        auth = self.app.authentication
        account = self.app.store.load().apple_id
        ready = False
        needs_password = True
        try:
            if account:
                try:
                    with self.console.status("Trying saved credentials..."):
                        ready = auth.login(account)
                    needs_password = False
                except AppError as exc:
                    self.report(exc)

            while needs_password:
                self.console.print("Connect iCloud (Ctrl+C cancels)")
                account = Prompt.ask("Apple Account email", default=account, console=self.console)
                password = Prompt.ask("Password", password=True, console=self.console)
                try:
                    with self.console.status("Signing in..."):
                        ready = auth.login(account, password)
                    needs_password = False
                except AppError as exc:
                    self.report(exc)
                finally:
                    password = ""

            while not ready:
                code = Prompt.ask("Verification code (Ctrl+C cancels)", console=self.console)
                try:
                    with self.console.status("Verifying..."):
                        auth.verify(code)
                    ready = True
                except AppError as exc:
                    self.report(exc)
                    if not Confirm.ask("Retry verification?", default=True, console=self.console):
                        return False
                finally:
                    code = ""

            self.log("iCloud connected.")
            return True
            
        finally:
            if not ready:
                try:
                    auth.cancel()
                finally:
                    auth.clear()

    def setup(self):
        """UX drawing: persist folder, try saved login, then password and 2FA."""
        if self.app.prerequisite() == "folder":
            config = self.app.store.load()
            if config.backup_folder:
                self.app.save_settings(config.backup_folder, str(config.interval_minutes), require_folder=True)
            else:
                self.settings()
        return self.login()

    def schedule(self):
        minutes = self.app.store.load().interval_minutes
        self.next_fetch = time.monotonic() + minutes * 60 if minutes and self.app.prerequisite() == "ready" else None

    def render(self, task="Idle", progress="", *, fetching=False):
        config = self.app.store.load()
        status = BackupStatusStore(self.app.store.directory).load()
        schedule = (f"Next fetch in {max(0, int(self.next_fetch - time.monotonic()))} seconds"
                    if self.next_fetch else "Automatic fetching paused or manual only")
        visible_logs = max(1, min(5, self.console.height - 23))
        recent = "\n".join(f"{entry.time}  {' '.join(entry.message.split())}"
                           for entry in reversed(self.logs[-visible_logs:]))
        controls = ("P pause | R resume | C cancel | Q quit safely; local saves always finish"
                    if fetching else "F fetch/retry | S settings | L login | D disconnect | H search logs | X clear logs | Q quit")
        return Group(
            Text(controls),
            Panel(Text(f"{config.apple_id or 'No account'} | {'Connected' if self.app.connected else 'Disconnected'}\n"
                       f"Folder: {config.backup_folder or 'Not configured'}\n"
                       f"Attachments: {'on' if config.download_attachments else 'off'}\n{schedule}",
                       overflow="ellipsis", no_wrap=True), title="Notes Vault"),
            Panel(Text(f"{task}\n{progress}\nLast backup: {status.last_backup}\n{status.last_result}",
                       overflow="ellipsis", no_wrap=True), title="Tasks"),
            Panel(Text(recent, overflow="ellipsis", no_wrap=True), title="Recent logs"),
        )

    def fetch(self, read_key):
        messages = SimpleQueue()
        control = FetchControl()
        task = self.tasks.start("Fetching", lambda progress: self.app.fetch(progress, control), messages.put, control=control)
        if task is None:
            return
        latest = ""
        try:
            with Live(console=self.console, refresh_per_second=8) as live:
                while not task.future.done():
                    try:
                        while True:
                            latest = messages.get_nowait()
                            self.log(latest)
                    except Empty:
                        pass
                    live.update(self.render(control.state, latest, fetching=True))
                    try:
                        key = read_key()
                        if key == "p":
                            control.pause()
                        elif key == "r":
                            control.resume()
                        elif key == "c":
                            control.cancel()
                        elif key in ("q", "\x03", "\x04"):
                            self.quitting = True
                            control.cancel()
                        time.sleep(0.05)
                    except KeyboardInterrupt:
                        self.quitting = True
                        control.cancel()
                while not messages.empty():
                    self.log(messages.get_nowait())
                _, result = task.future.result()
                self.log(result.summary())
                for warning in result.warnings:
                    self.log(warning)
        except FetchCancelled as exc:
            self.log(str(exc))
        finally:
            # On any adapter failure, stop retrieval and wait before clearing sessions.
            control.cancel()
            while not task.future.done():
                try:
                    time.sleep(0.05)
                except KeyboardInterrupt:
                    self.quitting = True
            self.tasks.finish(task)

    def run(self):
        try:
            try:
                self.setup()
            except KeyboardInterrupt:
                self.log("Setup cancelled. Saved steps are preserved.")
            except EOFError:
                return
            except Exception as exc:
                self.report(exc)
            self.schedule()
            while not self.quitting:
                try:
                    with keyboard() as read_key, Live(self.render(), console=self.console, refresh_per_second=4) as live:
                        key = ""
                        while not key:
                            live.update(self.render())
                            key = read_key()
                            if self.next_fetch and time.monotonic() >= self.next_fetch:
                                key = "f"
                            time.sleep(0.05)
                    if key in ("q", "\x03", "\x04"):
                        break
                    if key == "f":
                        if self.setup():
                            with keyboard() as read_key:
                                self.fetch(read_key)
                    elif key == "s":
                        self.settings()
                    elif key == "l":
                        self.login()
                    elif key == "d" and not self.app.is_demo:
                        self.app.authentication.logout()
                        self.log("Disconnected. Backups are preserved.")
                    elif key == "h":
                        search = Prompt.ask("Search logs", default="", console=self.console).casefold()
                        self.console.print(Text(log_text(tuple(entry for entry in reversed(self.logs) if search in entry.message.casefold()))))
                        Prompt.ask("Press Enter to return", default="", console=self.console)
                    elif key == "x":
                        self.logs = ()
                    else:
                        continue
                    self.schedule()
                except KeyboardInterrupt:
                    self.log("Action cancelled.")
                    self.schedule()
                except EOFError:
                    break
                except Exception as exc:
                    self.report(exc)
                    self.schedule()
        finally:
            self.tasks.close()
            self.app.authentication.clear()


def run_tui(store, *, is_demo=False):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise AppError("--tui requires an interactive terminal. Use --once for noninteractive backups.")
    TerminalUI(Application(store, is_demo=is_demo)).run()
