"""Synthetic dependencies and disposable settings for tests and manual checks."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from notesvault.application import Application
from notesvault.config_store import ConfigStoreController
from notesvault.icloud_errors import ReconnectRequired
from notesvault.models import ConfigModel, SnapshotModel
from notesvault.fetch_control import FetchControl
from notesvault.provider_utils import render_export, ExportBuffer


class SyntheticNotesProvider:
    def __init__(self, session=None, account="demo"):
        self.account = account

    def fetch(self, directory: Path | None, progress, *, previous=None, previous_cursor=None,
              control: FetchControl | None = None,
              download_attachments: bool = False) -> SnapshotModel:
        control = control or FetchControl()
        control.checkpoint()
        buffer = ExportBuffer()
        progress("Preparing three example notes…")
        return SnapshotModel(self.account, [buffer.retain(render_export(str(i), title, body,
            "Examples", "demo-folder", "2026-01-01T12:00:00+00:00", []))
            for i, (title, body) in enumerate(control.iterate([
                ("Welcome", "# Welcome\n\nYour notes, backed up locally.\n\nThis is synthetic demo data."),
                ("Weekend plans", "# Weekend plans\n\n- Take a walk\n- Read a book"),
                ("Ideas ☁", "# Ideas ☁\n\nA small app that keeps a history of your notes."),
            ]))])


class SyntheticAuthentication:
    """Exercise normal connection/logout paths without network or OS credentials."""

    def __init__(self, store):
        self.store = store
        self.account = ""
        self.connected = False

    @property
    def session(self):
        if not self.connected:
            raise ReconnectRequired("Connect the synthetic account before fetching.")
        return self

    def login(self, account, password="", *, interactive=True):
        self.account = account
        self.store.save(replace(self.store.load(), apple_id=account))
        self.connected = True
        return True

    def login_saved(self):
        self.login(self.store.load().apple_id or "demo@example.invalid")

    def logout(self):
        self.clear()
        self.account = ""
        self.store.save(replace(self.store.load(), apple_id=""))

    def cancel(self):
        self.clear()

    def clear(self):
        self.connected = False


@contextmanager
def demo_application():
    """Keep synthetic settings and backups alive until the interface has stopped."""
    with TemporaryDirectory(prefix="notesvault-demo-") as directory:
        store = ConfigStoreController(Path(directory))
        store.save(ConfigModel(apple_id="demo@example.invalid",
                               backup_folder=str(store.directory / "backups"), interval_minutes=0))
        authentication = SyntheticAuthentication(store)
        application = Application(store, authentication=authentication,
                                  provider_factory=SyntheticNotesProvider)
        authentication.login_saved()
        try:
            yield application
        finally:
            authentication.clear()
