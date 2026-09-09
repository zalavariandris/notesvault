from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from notesvault.models import AppError
from notesvault.providers import ICloudProvider


def test_frontmatter_preserves_metadata_and_body(tmp_path):
    import json
    from notesvault.providers import write_export

    title = 'A "title": # tag\n---\nUnicode \u2601'
    exported = write_export(tmp_path, "001", title, "# Body\r\n\r\nText", "Notes", "folder", None, [])
    assert len(exported.files) == 1
    path = next(iter(exported.files.values()))
    assert path.suffix == ".md"
    header, body = path.read_text(encoding="utf-8")[4:].split("\n---\n\n", 1)
    metadata = {key: json.loads(value) for key, value in
                (line.split(": ", 1) for line in header.splitlines())}
    assert metadata == {
        "id": "001", "title": title, "folder": "Notes", "folder_id": "folder",
        "modified_at": None,
        "format": "plain text in Markdown; rich formatting is not preserved",
    }
    assert body == "# Body\n\nText\n"
    assert not list(tmp_path.rglob("*.json"))


class Notes:
    def sync_cursor(self):
        return "stable"

    def iter_all(self):
        yield SimpleNamespace(id="one", is_deleted=False)

    def get(self, note_id, with_attachments=False):
        return SimpleNamespace(id=note_id, title="Example", text="Synthetic content",
            is_deleted=False, folder_name="Notes", folder_id="folder",
            modified_at=datetime(2026, 1, 1, tzinfo=timezone.utc), attachments=[])


def provider(tmp_path, notes):
    instance = ICloudProvider(tmp_path)
    instance.account = "test"
    instance.api = SimpleNamespace(notes=notes, requires_2fa=False, requires_2sa=False)
    return instance


def test_full_scan_exports(tmp_path):
    snapshot = provider(tmp_path, Notes()).fetch(tmp_path / "stage", lambda _: None)
    assert snapshot.complete
    assert len(snapshot.notes) == 1


def test_pagination_error_aborts_before_returning_snapshot(tmp_path):
    class BrokenPage(Notes):
        def iter_all(self):
            yield from super().iter_all()
            raise RuntimeError("page two failed")
    with pytest.raises(AppError, match="fetch failed"):
        provider(tmp_path, BrokenPage()).fetch(tmp_path / "stage", lambda _: None)


def test_changed_cursor_aborts(tmp_path):
    class Changing(Notes):
        calls = 0
        def sync_cursor(self):
            self.calls += 1
            return str(self.calls)
    with pytest.raises(AppError, match="changed during"):
        provider(tmp_path, Changing()).fetch(tmp_path / "stage", lambda _: None)


def test_locked_note_defers_deletions(tmp_path):
    from pyicloud.services.notes.service import NoteLockedError
    class Locked(Notes):
        def get(self, *args, **kwargs):
            raise NoteLockedError("private title must not be surfaced")
    snapshot = provider(tmp_path, Locked()).fetch(tmp_path / "stage", lambda _: None)
    assert snapshot.skipped == 1
    assert not snapshot.complete
    assert "private title" not in " ".join(snapshot.warnings)


def test_preview_only_attachment_is_not_backed_up_as_original(tmp_path):
    class PreviewOnly(Notes):
        def get(self, *args, **kwargs):
            note = super().get(*args, **kwargs)
            note.attachments = [SimpleNamespace(download_url=None)]
            return note
    snapshot = provider(tmp_path, PreviewOnly()).fetch(tmp_path / "stage", lambda _: None)
    assert snapshot.skipped == 1
    assert not snapshot.notes


def test_original_attachment_stream_is_preserved(tmp_path):
    class WithAttachment(Notes):
        def get(self, *args, **kwargs):
            note = super().get(*args, **kwargs)
            note.attachments = [SimpleNamespace(id="attachment", filename="example.bin",
                download_url="https://example.invalid/original", size=6,
                stream=lambda **kwargs: iter([b"abc", b"def"]))]
            return note
    snapshot = provider(tmp_path, WithAttachment()).fetch(tmp_path / "stage", lambda _: None)
    attachment_path = next(path for name, path in snapshot.notes[0].files.items() if name.startswith("attachments/"))
    assert attachment_path.read_bytes() == b"abcdef"


def test_truncated_attachment_aborts(tmp_path):
    class Truncated(Notes):
        def get(self, *args, **kwargs):
            note = super().get(*args, **kwargs)
            note.attachments = [SimpleNamespace(id="attachment", filename="example.bin",
                download_url="https://example.invalid/original", size=10,
                stream=lambda **kwargs: iter([b"abc"]))]
            return note
    with pytest.raises(AppError, match="incomplete"):
        provider(tmp_path, Truncated()).fetch(tmp_path / "stage", lambda _: None)
