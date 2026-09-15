"""Prompt-based command line with scrolling output and an automatic-fetch timer."""
from contextlib import contextmanager
import math
import os
from queue import SimpleQueue
import sys
import time

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.text import Text

from .application import Application
from .backup_status_store import BackupStatusStore
from .fetch_control import FetchCancelled, FetchControl
from .models import AppError
from .icloud_errors import ReconnectRequired, TermsAcceptanceRequired
from .task_manager import TaskManager


@contextmanager
def keyboard():
    """Read prompt input without blocking the timer; restore normal input for forms."""
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


class TerminalCLI:
    def __init__(self, application: Application, console=None):
        self.app = application
        self.console = console or Console()
        self.tasks = TaskManager()
        self.next_fetch = None
        self.quitting = False

    def log(self, message):
        self.console.print(Text(message))

    def report(self, exc):
        message = str(exc) if isinstance(exc, AppError) else "Operation failed. Check connection, folder permissions, and settings, then retry."
        self.log(message)

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
                    self.log("Signing in with saved credentials...")
                    ready = auth.login(account)
                    needs_password = False
                except TermsAcceptanceRequired:
                    raise
                except AppError as exc:
                    self.report(exc)

            while not ready:
                if needs_password:
                    self.console.print("Connect iCloud (Ctrl+C cancels)")
                    account = Prompt.ask("Apple Account email", default=account, console=self.console)
                    password = Prompt.ask("Password", password=True, console=self.console)
                    try:
                        self.log("Signing in...")
                        ready = auth.login(account, password)
                        needs_password = False
                    except TermsAcceptanceRequired:
                        raise
                    except AppError as exc:
                        self.report(exc)
                    finally:
                        password = ""
                    continue
                code = Prompt.ask("Verification code (Ctrl+C cancels)", console=self.console)
                try:
                    self.log("Verifying...")
                    auth.verify(code)
                    ready = True
                except TermsAcceptanceRequired:
                    raise
                except AppError as exc:
                    self.report(exc)
                    needs_password = (isinstance(exc, ReconnectRequired)
                                      or not getattr(auth, "awaiting_verification", True))
                    prompt = "Sign in again?" if needs_password else "Retry verification?"
                    if not Confirm.ask(prompt, default=True, console=self.console):
                        return False
                finally:
                    code = ""

            self.log("iCloud connected.")
            return True
        except TermsAcceptanceRequired as exc:
            self.report(exc)
            self.log("Sign-in paused. After finishing at iCloud.com, answer yes to retry sign-in.")
            return False

        finally:
            if not ready:
                try:
                    auth.cancel()
                finally:
                    auth.clear()

    def setup(self):
        """Prepare a saved folder or ask for a missing one, then sign in."""
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

    def show_status(self):
        config = self.app.store.load()
        status = BackupStatusStore(self.app.store.directory).load()
        self.log(f"Backup folder: {config.backup_folder or 'Not configured'}")
        try:
            self.log(f"Notes on disk: {self.app.local_note_count()}")
        except (AppError, OSError):
            self.log("Notes on disk: unavailable; check the backup folder and manifest.")
        self.log(f"Last backup: {status.last_backup}")
        self.log(status.last_result)
        self.log(f"Automatic fetch interval: {config.interval_minutes} minutes (0 = off).")
        self.log("Enter yes to fetch, no to wait, settings to change preferences, or quit to exit.")

    def prompt(self):
        """Accept a line of input while displaying the next fetch countdown."""
        answer = ""
        previous = ""
        width = 0
        with keyboard() as read_key:
            try:
                while True:
                    remaining = (max(0, math.ceil(self.next_fetch - time.monotonic()))
                                 if self.next_fetch is not None else None)
                    if remaining == 0:
                        return "automatic"
                    question = "Fetch now?" if self.app.connected else "Retry sign-in?"
                    timer = (f"Next fetch in {remaining // 3600:02}:{remaining // 60 % 60:02}:{remaining % 60:02}"
                             if remaining is not None else "Automatic fetch paused" if not self.app.connected
                             else "Automatic fetch off")
                    line = f"{timer} | {question} [y/N/q]: {answer}"
                    if line != previous:
                        width = max(width, len(line))
                        # Update only this prompt line, keeping all earlier output in scrollback.
                        self.console.file.write("\r" + line.ljust(width) + "\r" + line)
                        self.console.file.flush()
                        previous = line
                    key = read_key()
                    if key in ("\r", "\n"):
                        return answer.strip().casefold()
                    if key == "\x03":
                        raise KeyboardInterrupt()
                    if key == "\x04":
                        raise EOFError()
                    if key in ("\b", "\x7f"):
                        answer = answer[:-1]
                    elif key.isascii() and key.isprintable() and key and len(answer) < 16:
                        answer += key
                    time.sleep(0.05)
            finally:
                self.console.file.write("\n")
                self.console.file.flush()

    def fetch(self):
        messages = SimpleQueue()
        control = FetchControl()
        self.log("Fetching notes... Ctrl+C cancels and exits after safe cleanup.")
        task = self.tasks.start("Fetching", lambda progress: self.app.fetch(progress, control), messages.put, control=control)
        if task is None:
            return
        try:
            while not task.future.done():
                try:
                    while not messages.empty():
                        self.log(messages.get_nowait())
                    time.sleep(0.05)
                except KeyboardInterrupt:
                    self.quitting = True
                    control.cancel()
                    self.log("Stopping after the current request or local save finishes...")
            while not messages.empty():
                self.log(messages.get_nowait())
            _, result = task.future.result()
            self.log(result.summary())
            for warning in result.warnings:
                self.log(warning)
        except FetchCancelled as exc:
            self.log(str(exc))
        finally:
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
                return
            except EOFError:
                return
            except Exception as exc:
                self.report(exc)
            self.show_status()
            self.schedule()
            while not self.quitting:
                try:
                    answer = self.prompt()
                    if answer in ("q", "quit", "exit"):
                        break
                    if answer in ("", "n", "no"):
                        continue
                    if answer == "settings":
                        self.next_fetch = None
                        self.settings()
                    elif answer in ("y", "yes", "automatic"):
                        self.next_fetch = None
                        if answer == "automatic":
                            self.log("Scheduled fetch starting.")
                        was_connected = self.app.connected
                        if self.setup() and was_connected:
                            self.fetch()
                    else:
                        self.log("Answer yes, no, settings, or quit, then press Enter.")
                        continue
                    if not self.quitting:
                        self.show_status()
                    self.schedule()
                except (KeyboardInterrupt, EOFError):
                    break
                except ReconnectRequired as exc:
                    self.report(exc)
                    self.next_fetch = None
                    if not self.quitting:
                        try:
                            if self.login():
                                self.log("Reconnected. Answer yes to retry the fetch.")
                        except (KeyboardInterrupt, EOFError):
                            break
                        except Exception as login_exc:
                            self.report(login_exc)
                    self.schedule()
                except Exception as exc:
                    self.report(exc)
                    self.schedule()
        finally:
            self.tasks.close()
            self.app.authentication.clear()
