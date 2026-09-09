from pathlib import Path
from urllib.parse import quote

from ..models import AppError, ExportedNote, Snapshot

class DemoProvider:
    connected = True
    account = "demo"

    def fetch(self, directory: Path, progress) -> Snapshot:
        progress("Preparing three example notes…")
        return Snapshot("demo", [write_export(directory, str(i), title, body,
            "Examples", "demo-folder", "2026-01-01T12:00:00+00:00", [])
            for i, (title, body) in enumerate([
                ("Welcome", "# Welcome\n\nYour notes, backed up locally.\n\nThis is synthetic demo data."),
                ("Weekend plans", "# Weekend plans\n\n- Take a walk\n- Read a book"),
                ("Ideas ☁", "# Ideas ☁\n\nA small app that keeps a history of your notes."),
            ])])
