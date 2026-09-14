import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from notesvault import __main__ as cli
from notesvault.models import AppError


def test_demo_once_runs_without_gui_or_account(tmp_path):
    # A subprocess also verifies the installed entry point and dependency imports.
    result = subprocess.run([sys.executable, "-m", "notesvault", "--demo", "--once"],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "3 added | 0 updated | 0 deleted | 0 skipped" in result.stdout
    assert "Local Git:" in result.stdout
    assert "GitHub" not in result.stdout
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('flags,default_tui,expected', [
    ([], False, 'gui'), ([], True, 'tui'),
    (['--tui'], False, 'tui'), (['--once'], False, 'once'),
    (['--once'], True, 'once'), (['--check'], True, 'check'),
])
def test_launch_modes_and_demo_isolation(tmp_path, monkeypatch, flags, default_tui, expected):
    calls, directories = [], []
    monkeypatch.setattr(cli.logging, 'disable', lambda _: None)
    def launch(mode):
        def run(store=None, *, is_demo=False):
            calls.append(mode)
            if store is not None:
                assert is_demo
                assert store.directory != tmp_path
                assert store.load().apple_id == 'demo'
                directories.append(store.directory)
        return run
    monkeypatch.setattr(cli, 'run_gui', launch('gui'))
    monkeypatch.setattr(cli, 'run_once', launch('once'))
    monkeypatch.setattr(cli, 'check_runtime', launch('check'))
    monkeypatch.setattr(cli, 'run_tui', launch('tui'))
    cli.main(['--demo', '--data-dir', str(tmp_path), *flags], default_tui=default_tui)
    assert calls == [expected]
    assert not any(path.exists() for path in directories)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('flags', [ ['--tui', '--once'], ['--check', '--once'], ['--check', '--tui'] ])
def test_conflicting_modes_are_rejected(flags):
    with pytest.raises(SystemExit) as error:
        cli.parse_args(flags)
    assert error.value.code == 2


@pytest.mark.parametrize('failure,code,message', [
    (AppError('Synthetic safe error'), 1, 'Synthetic safe error'),
    (KeyboardInterrupt(), 130, 'Operation cancelled'),
    (EOFError(), 130, 'Operation cancelled'),
    (PermissionError('private diagnostic'), 1, 'folder permissions'),
])
def test_failure_cleans_demo_and_reports_exit_status(monkeypatch, capsys, failure, code, message):
    directories = []
    monkeypatch.setattr(cli.logging, 'disable', lambda _: None)
    def fail(store, **kwargs):
        directories.append(store.directory)
        raise failure
    monkeypatch.setattr(cli, 'run_once', fail)
    with pytest.raises(SystemExit) as error:
        cli.main(['--demo', '--once'])
    assert error.value.code == code
    assert not directories[0].exists()
    output = capsys.readouterr().out
    assert message in output and 'private diagnostic' not in output


@pytest.mark.parametrize('outcome', ['success', 'login_error', 'fetch_error', 'skipped'])
def test_once_clears_credentials_on_every_exit(monkeypatch, capsys, outcome):
    calls = []
    def login():
        calls.append('login')
        if outcome == 'login_error':
            raise AppError('Sign in again')
    def fetch(progress, control):
        calls.append('fetch')
        if outcome == 'fetch_error':
            raise AppError('Fetch failed')
        return None, SimpleNamespace(summary=lambda: 'Synthetic result',
                                     warnings=['Synthetic warning'], skipped=outcome == 'skipped')
    app = SimpleNamespace(authentication=SimpleNamespace(login_saved=login,
                          clear=lambda: calls.append('clear')), fetch=fetch)
    monkeypatch.setattr(cli, 'Application', lambda *a, **kw: app)
    if outcome == 'success':
        cli.run_once(None)
    else:
        with pytest.raises(SystemExit if outcome == 'skipped' else AppError):
            cli.run_once(None)
    assert calls == (['login', 'clear'] if outcome == 'login_error' else ['login', 'fetch', 'clear'])
    if outcome in {'success', 'skipped'}:
        assert capsys.readouterr().out == 'Synthetic result\nSynthetic warning\n'


def test_check_skips_settings_and_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.logging, 'disable', lambda _: None)
    def unexpected(*a, **kw):
        pytest.fail('Runtime check must not load settings or environment defaults')
    monkeypatch.setattr(cli, 'load_dotenv', unexpected)
    monkeypatch.setattr(cli, 'ConfigStoreController', unexpected)
    monkeypatch.setattr(cli, 'check_runtime', lambda: None)
    cli.main(['--check', '--data-dir', str(tmp_path / 'unused')])
    assert not list(tmp_path.iterdir())


def test_once_imports_no_desktop_modules():
    result = subprocess.run(
        [sys.executable, '-c', 'from notesvault.__main__ import main; import sys; '
         'main(["--demo", "--once"]); '
         'assert not any(k.startswith(("edifice", "PySide6", "notesvault.gui")) for k in sys.modules)'],
        capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
