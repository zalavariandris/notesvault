from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from notesvault.models import AppError
from notesvault.icloud_notes_provider import ICloudNotesProvider


def test_frontmatter_preserves_metadata_and_body(tmp_path):
    import json
    from notesvault.provider_utils import render_export

    title = 'A "title": # tag\n---\nUnicode \u2601'
    exported = render_export("001", title, "# Body\r\n\r\nText", "Notes", "folder", None, [])
    assert len(exported.files) == 1
    name, content = next(iter(exported.files.items()))
    assert name.endswith(".md")
    header, body = content.decode("utf-8")[4:].split("\n---\n\n", 1)
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
    return ICloudNotesProvider(SimpleNamespace(notes=notes), "test")


def test_full_scan_exports(tmp_path):
    snapshot = provider(tmp_path, Notes()).fetch(tmp_path / "stage", lambda _: None)
    assert snapshot.complete
    assert len(snapshot.notes) == 1


@pytest.mark.parametrize("html,rich", [
    ("<h2>Heading</h2><p><b>Synthetic</b> <custom>content</custom></p>", True),
    ("<style>unused</style>", False),
])
def test_renderer_integration_and_readable_fallback(tmp_path, html, rich):
    class Rendered(Notes):
        def render_note(self, note_id, **options):
            assert options == {"export_mode": "lightweight", "full_page": False, "debug": False}
            return html
    snapshot = provider(tmp_path, Rendered()).fetch(None, lambda _: None)
    content = next(iter(snapshot.notes[0].files.values())).decode()
    assert ("## Heading" in content) is rich
    assert "**Synthetic**" in content if rich else "Synthetic content" in content
    assert any("plain text was exported" in message for message in snapshot.warnings) is not rich
    assert not list(tmp_path.rglob("*.md"))


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
    snapshot = provider(tmp_path, PreviewOnly()).fetch(tmp_path / "stage", lambda _: None, download_attachments=True)
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
    snapshot = provider(tmp_path, WithAttachment()).fetch(tmp_path / "stage", lambda _: None, download_attachments=True)
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
        provider(tmp_path, Truncated()).fetch(tmp_path / "stage", lambda _: None, download_attachments=True)


@pytest.mark.parametrize("point", ["listing", "note", "attachment", "network_error"])
def test_cancel_during_retrieval_never_returns_partial_snapshot(tmp_path, point):
    from notesvault.fetch_control import FetchCancelled, FetchControl

    control = FetchControl()
    consumed = []
    class CancellableNotes(Notes):
        def iter_all(self):
            if point == "listing":
                control.cancel()
            yield from super().iter_all()
            consumed.append("second page")
        def get(self, *args, **kwargs):
            if point in ("note", "network_error"):
                control.cancel()
            if point == "network_error":
                raise RuntimeError("synthetic timeout")
            note = super().get(*args, **kwargs)
            if point == "attachment":
                def chunks(**kwargs):
                    yield b"first"
                    control.cancel()
                    yield b"second"
                    consumed.append("third chunk")
                note.attachments = [SimpleNamespace(id="attachment", filename="synthetic.bin",
                    download_url="https://example.invalid/original", size=None, stream=chunks)]
            return note
    with pytest.raises(FetchCancelled):
        provider(tmp_path, CancellableNotes()).fetch(tmp_path / "stage", lambda _: None, control=control,
                                                  download_attachments=True)
    if point == "listing":
        assert "second page" not in consumed
    assert "third chunk" not in consumed
