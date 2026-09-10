import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from .models import AppError, ExportedNoteModel

# Invalidates cached exports even when the iCloud cursor is unchanged.
# Increment whenever export content or supported content changes.
EXPORT_VERSION = 3
MAX_EXPORT_BYTES = 64 * 1024 * 1024


class ExportBuffer:
    """Bound retained rendered bytes without writing temporary Markdown files."""

    def __init__(self):
        self.size = 0

    def retain(self, note: ExportedNoteModel) -> ExportedNoteModel:
        self.size += sum(len(content) for content in note.files.values() if isinstance(content, bytes))
        if self.size > MAX_EXPORT_BYTES:
            raise AppError("Rendered notes exceed the 64 MiB fetch limit. Existing backups were retained.")
        return note


def note_date(modified: str | None) -> str:
    """Use UTC modification dates; never invent a changing date for missing data."""
    try:
        value = datetime.fromisoformat(modified)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return "0000-00-00"

def safe_name(value: str, limit: int = 65) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")[:limit].rstrip(" .")
    if not value:
        return "Untitled"
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}:
        value = "_" + value
    return value


def stable_id(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def render_export(note_id: str, title: str, text: str,
                 folder: str, folder_id: str, modified: str | None,
                 attachments: list[tuple[str, str, bytes | Path]], *,
                 format_description: str = "plain text in Markdown; rich formatting is not preserved") -> ExportedNoteModel:
    note_key = stable_id(note_id)
    folder_key = f"{safe_name(folder, 35)}_[{stable_id(folder_id)}]"
    base = f"notes/{folder_key}/{note_date(modified)}-{safe_name(title)}-[{note_key}]"
    files: dict[str, bytes | Path] = {}

    links = []
    for att_id, filename, content in attachments:
        relative = f"attachments/{note_key}/{stable_id(att_id)}_{safe_name(filename)}"
        if relative in files:
            raise AppError("Duplicate attachment identifier; backup was not changed.")
        files[relative] = content
        links.append(f"- [Attachment](../../{quote(relative)})")
    body = text.replace("\r\n", "\n")
    if links:
        body += "\n\n## Attachments\n\n" + "\n".join(links)
    metadata = {"id": note_id, "title": title, "folder": folder,
                "folder_id": folder_id, "modified_at": modified,
                "format": format_description}
    # JSON-quoted scalars are valid YAML and safely escape metadata characters.
    frontmatter = "\n".join(f"{key}: {json.dumps(value)}" for key, value in sorted(metadata.items()))
    files[base + ".md"] = (f"---\n{frontmatter}\n---\n\n" + body.rstrip() + "\n").encode("utf-8")
    return ExportedNoteModel(note_id, files)
