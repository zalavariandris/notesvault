import hashlib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote

from ..models import AppError, ExportedNote

# Invalidates cached exports even when the iCloud cursor is unchanged.
# Increment whenever export content or supported content changes.
EXPORT_VERSION = 1

def safe_name(value: str, limit: int = 65) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")[:limit].rstrip(" .")
    if not value:
        return "Untitled"
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}:
        value = "_" + value
    return value


def stable_id(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def write_export(directory: Path, note_id: str, title: str, text: str,
                 folder: str, folder_id: str, modified: str | None,
                 attachments: list[tuple[str, str, bytes | Path]]) -> ExportedNote:
    note_key = stable_id(note_id)
    folder_key = f"{safe_name(folder, 35)}_[{stable_id(folder_id)}]"
    base = f"notes/{folder_key}/{safe_name(title)}_[{note_key}]"
    files: dict[str, Path] = {}

    def put(relative: str, content: bytes | Path):
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, Path):
            shutil.copyfile(content, target)
        else:
            target.write_bytes(content)
        files[relative] = target

    links = []
    for att_id, filename, content in attachments:
        relative = f"attachments/{note_key}/{stable_id(att_id)}_{safe_name(filename)}"
        if relative in files:
            raise AppError("Duplicate attachment identifier; backup was not changed.")
        put(relative, content)
        links.append(f"- [Attachment](../../{quote(relative)})")
    body = text.replace("\r\n", "\n")
    if links:
        body += "\n\n## Attachments\n\n" + "\n".join(links)
    metadata = {"id": note_id, "title": title, "folder": folder,
                "folder_id": folder_id, "modified_at": modified,
                "format": "plain text in Markdown; rich formatting is not preserved"}
    # JSON-quoted scalars are valid YAML and safely escape metadata characters.
    frontmatter = "\n".join(f"{key}: {json.dumps(value)}" for key, value in sorted(metadata.items()))
    put(base + ".md", (f"---\n{frontmatter}\n---\n\n" + body.rstrip() + "\n").encode("utf-8"))
    return ExportedNote(note_id, files)
