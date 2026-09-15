from contextlib import contextmanager

import pytest

from notesvault.fetch_control import FetchControl
from test_interfaces import terminal


def test_startup_prepares_folder_before_login_and_status(tmp_path, monkeypatch):
    cli = terminal(tmp_path)
    cli.app.authentication.clear()
    calls = []
    def login():
        assert cli.app.store.load().backup_folder == str(tmp_path / 'vault')
        calls.append('login')
        cli.app.authentication.connected = True
        return True
    def settings():
        assert not cli.app.connected
        calls.append('folder')
        cli.app.save_settings(str(tmp_path / 'vault'), '1')
    def prompt():
        output = cli.console.file.getvalue()
        assert str(tmp_path / 'vault') in output
        assert 'Notes on disk: 0' in output
        assert cli.next_fetch is not None
        return 'quit'
    monkeypatch.setattr(cli, 'login', login)
    monkeypatch.setattr(cli, 'settings', settings)
    monkeypatch.setattr(cli, 'prompt', prompt)
    cli.run()
    assert calls == ['folder', 'login']
    assert cli.tasks.closed
    assert not cli.app.connected


def test_disk_count_ignores_unmanaged_files_and_missing_notes(tmp_path):
    cli = terminal(tmp_path)
    folder = tmp_path / 'vault'
    cli.app.save_settings(str(folder), '0')
    assert cli.app.local_note_count() == 0
    cli.app.fetch(lambda _: None, FetchControl())
    assert cli.app.local_note_count() == 3
    (folder / 'notes' / 'unrelated.md').write_text('Synthetic user file', encoding='utf-8')
    (folder / 'README.md').write_text('Synthetic readme', encoding='utf-8')
    managed = next((folder / 'notes').glob('*/*.md'))
    managed.unlink()
    assert cli.app.local_note_count() == 2
    cli.show_status()
    assert 'Notes on disk: 2' in cli.console.file.getvalue()
    cli.tasks.close()


def test_bad_manifest_reports_unavailable_count(tmp_path):
    cli = terminal(tmp_path)
    folder = tmp_path / 'vault'
    cli.app.save_settings(str(folder), '0')
    (folder / '.apple-notes-manifest.json').write_text('invalid', encoding='utf-8')
    cli.show_status()
    assert 'Notes on disk: unavailable' in cli.console.file.getvalue()
    cli.tasks.close()


@pytest.mark.parametrize('keys,expected', [(['y', 'e', 's', '\n'], 'yes'),
                                         (['y', '\b', 'n', '\r'], 'n'),
                                         (['\n'], '')])
def test_prompt_accepts_lines_and_restores_terminal(tmp_path, monkeypatch, keys, expected):
    cli = terminal(tmp_path)
    events = []
    keys = iter(keys)
    @contextmanager
    def keyboard():
        events.append('open')
        try:
            yield lambda: next(keys)
        finally:
            events.append('closed')
    monkeypatch.setattr('notesvault.terminal.keyboard', keyboard)
    monkeypatch.setattr('notesvault.terminal.time.sleep', lambda _: None)
    assert cli.prompt() == expected
    assert events == ['open', 'closed']
    assert 'Fetch now?' in cli.console.file.getvalue()
    cli.tasks.close()


def test_countdown_updates_and_starts_fetch_without_input(tmp_path, monkeypatch):
    cli = terminal(tmp_path)
    cli.next_fetch = 102
    ticks = iter([100, 101, 102])
    restored = []
    @contextmanager
    def keyboard():
        try:
            yield lambda: ''
        finally:
            restored.append(True)
    monkeypatch.setattr('notesvault.terminal.keyboard', keyboard)
    monkeypatch.setattr('notesvault.terminal.time.monotonic', lambda: next(ticks))
    monkeypatch.setattr('notesvault.terminal.time.sleep', lambda _: None)
    assert cli.prompt() == 'automatic'
    output = cli.console.file.getvalue()
    assert '00:00:02' in output and '00:00:01' in output
    assert restored == [True]
    cli.tasks.close()


def test_declining_fetch_keeps_deadline_then_scheduled_fetch_runs(tmp_path, monkeypatch):
    cli = terminal(tmp_path)
    cli.app.save_settings(str(tmp_path / 'vault'), '1')
    deadlines = []
    answers = iter(['no', 'automatic', 'quit'])
    def prompt():
        deadlines.append(cli.next_fetch)
        return next(answers)
    monkeypatch.setattr(cli, 'prompt', prompt)
    cli.run()
    assert deadlines[0] == deadlines[1]
    assert deadlines[2] > deadlines[1]
    output = cli.console.file.getvalue()
    assert 'Scheduled fetch starting.' in output
    assert '3 added' in output and 'Notes on disk: 3' in output
    assert cli.tasks.closed
