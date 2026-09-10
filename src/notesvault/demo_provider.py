from pathlib import Path

from .models import SnapshotModel
from .fetch_control import FetchControl
from .provider_utils import write_export

class DemoProvider:
    connected = True
    account = "demo"

    def fetch(self, directory: Path, progress, *, control: FetchControl | None = None,
              download_attachments: bool = False) -> SnapshotModel:
        control = control or FetchControl()
        control.checkpoint()
        progress("Preparing three example notes…")
        return SnapshotModel("demo", [write_export(directory, str(i), title, body,
            "Examples", "demo-folder", "2026-01-01T12:00:00+00:00", [])
            for i, (title, body) in enumerate(control.iterate([
                ("Welcome", "# Welcome\n\nYour notes, backed up locally.\n\nThis is synthetic demo data."),
                ("Weekend plans", "# Weekend plans\n\n- Take a walk\n- Read a book"),
                ("Ideas ☁", "# Ideas ☁\n\nA small app that keeps a history of your notes."),
            ]))])
