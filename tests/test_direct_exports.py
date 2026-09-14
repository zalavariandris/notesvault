from pathlib import Path
from types import SimpleNamespace
import json
import subprocess
import sys

import pytest

from notesvault.backup_controller import BackupController
from notesvault.disk_vault_controller import DiskVaultController, git
from notesvault.icloud_notes_provider import ICloudNotesProvider
from notesvault.models import AppError, SnapshotModel
from notesvault.provider_utils import render_export, note_date, stable_id


def test_frontmatter_preserves_unicode_and_escapes_yaml_delimiters(tmp_path):
    title = 'Éttermek "quoted": \\ path\n---\n日本語 😀'
    note = render_export('unicode', title, 'Body', 'Árvíztűrő', 'folder', None, [])
    name, content = next(iter(note.files.items()))
    text = content.decode('utf-8')
    assert 'Éttermek' in text and '日本語 😀' in text and 'Árvíztűrő' in text
    assert '\\u00c9' not in text
    metadata = dict(line.split(': ', 1) for line in text.split('\n---\n')[0].splitlines()[1:])
    assert json.loads(metadata['title']) == title
    repo = DiskVaultController(tmp_path / 'backup')
    with repo.locked():
        assert repo.apply(SnapshotModel('test', [note])).added == 1
        assert (repo.root / name).read_bytes() == content
        assert repo.apply(SnapshotModel('test', [note])).commit == 'No changes'


@pytest.mark.parametrize("timestamp,expected", [
    (None, "0000-00-00"), ("invalid", "0000-00-00"),
    ("2026-01-02T00:30:00+02:00", "2026-01-01"),
    ("2026-09-10T12:00:00", "2026-09-10"),
])
def test_filename_dates_are_deterministic_utc(timestamp, expected):
    assert note_date(timestamp) == expected


def test_rendering_does_not_write_files_and_names_keep_identity(tmp_path):
    first = render_export("one", "CON / Unicode ☁", "body", "Notes", "folder", None, [])
    second = render_export("one", "Renamed", "body", "Notes", "folder", "2026-01-01", [])
    name, content = next(iter(first.files.items()))
    assert Path(name).name == f"0000-00-00-CON _ Unicode ☁-[{stable_id('one')}].md"
    assert Path(next(iter(second.files))).name == f"2026-01-01-Renamed-[{stable_id('one')}].md"
    assert isinstance(content, bytes)
    assert not list(tmp_path.iterdir())
    repo = DiskVaultController(tmp_path / "backup")
    with repo.locked():
        assert repo.apply(SnapshotModel("test", [first])).added == 1
        head = git(repo.root, "rev-parse", "HEAD").stdout.decode().strip()
        assert repo.apply(SnapshotModel("test", [second])).updated == 1
        assert not (repo.root / name).exists()
        assert git(repo.root, "show", f"{head}:{name}").stdout == content
        assert repo.apply(SnapshotModel("test", [second])).commit == "No changes"


def test_memory_limit_aborts_before_vault_or_cache_changes(tmp_path, monkeypatch):
    from notesvault import provider_utils
    from test_incremental import Cloud, event
    cloud = Cloud()
    controller = BackupController(tmp_path / "backup")
    provider = ICloudNotesProvider(SimpleNamespace(notes=cloud), "test")
    controller.run_backup(provider, lambda _: None)
    root = controller.vault.root
    original = {path: path.read_bytes() for path in root.rglob("*") if path.is_file() and ".git" not in path.parts}
    cache = (root / ".git/notesvault-fetch.json").read_bytes()
    cloud.cursor, cloud.events = "second", [event("one")]
    monkeypatch.setattr(provider_utils, "MAX_EXPORT_BYTES", 1)
    with pytest.raises(AppError, match="fetch limit"):
        controller.run_backup(provider, lambda _: None)
    assert all(path.read_bytes() == content for path, content in original.items())
    assert (root / ".git/notesvault-fetch.json").read_bytes() == cache
    assert not list(root.rglob("notes-downloads-*"))


def test_markdown_is_only_written_after_save_boundary(tmp_path, monkeypatch):
    from notesvault.demo_provider import DemoProvider
    from notesvault.fetch_control import FetchControl
    control = FetchControl()
    root = tmp_path / "backup"
    writes = []
    original = Path.write_bytes

    def write(path, content):
        if path.suffix == ".md":
            assert control.state == "saving"
            assert path.is_relative_to(root / "notes")
            writes.append(path)
        return original(path, content)

    monkeypatch.setattr(Path, "write_bytes", write)
    result = BackupController(root).run_backup(DemoProvider(), lambda _: None, control=control)
    assert result.added == len(writes) == 3


def test_attachment_downloads_are_single_copy_and_cleaned_after_cancel(tmp_path, monkeypatch):
    from notesvault.fetch_control import FetchControl, FetchCancelled
    from test_provider import Notes
    control = FetchControl()

    class Cloud(Notes):
        def get(self, *args, **kwargs):
            note = super().get(*args, **kwargs)
            note.attachments = [SimpleNamespace(id="asset", filename="asset.bin", size=3,
                download_url="https://example.invalid/file", stream=lambda **kw: iter([b"abc"]))]
            return note

    provider = ICloudNotesProvider(SimpleNamespace(notes=Cloud()), "test")
    original = provider.fetch
    def fetch(directory, *args, **kwargs):
        snapshot = original(directory, *args, **kwargs)
        assert len(list(directory.rglob("*.*"))) == 0  # Download names are stable hashes.
        files = [path for path in directory.rglob("*") if path.is_file()]
        assert len(files) == 1 and files[0].read_bytes() == b"abc"
        control.cancel()
        return snapshot
    monkeypatch.setattr(provider, "fetch", fetch)
    root = tmp_path / "backup"
    with pytest.raises(FetchCancelled):
        BackupController(root).run_backup(provider, lambda _: None, control=control, download_attachments=True)
    assert not list(root.rglob("*.md"))
    assert not list((root / ".git").glob("notes-downloads-*"))


def test_process_interruption_keeps_recovery_copies_and_blocks_new_fetch(tmp_path):
    root = tmp_path / "backup"
    repo = DiskVaultController(root)
    note = render_export("one", "Original", "old content", "Notes", "folder", None, [])
    with repo.locked():
        repo.apply(SnapshotModel("test", [note]))
    head = git(root, "rev-parse", "HEAD").stdout.decode().strip()
    code = '''
import os, sys
from notesvault import disk_vault_controller as disk
from notesvault.models import SnapshotModel
from notesvault.provider_utils import render_export
real_git = disk.git
def interrupted(root, *args, **kwargs):
    if "commit" in args:
        os._exit(77)
    return real_git(root, *args, **kwargs)
disk.git = interrupted
repo = disk.DiskVaultController(sys.argv[1])
with repo.locked():
    repo.apply(SnapshotModel("test", [render_export("one", "Changed", "new", "Notes", "folder", None, [])]))
'''
    result = subprocess.run([sys.executable, "-c", code, str(root)], capture_output=True)
    assert result.returncode == 77, result.stderr.decode()
    journal = json.loads((root / ".git/notesvault-save.json").read_text())
    assert journal["head"] == head
    name, content = next(iter(note.files.items()))
    assert (root / ".git" / journal["rollback"] / journal["before"][name]).read_bytes() == content
    with pytest.raises(AppError, match="interrupted local save"):
        with repo.locked():
            pytest.fail("A new fetch must not start")
    assert git(root, "show", f"{head}:{name}").stdout == content
