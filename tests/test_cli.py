import subprocess
import sys
from types import SimpleNamespace

import pytest

from notesvault import __main__ as cli
from notesvault.models import AppError


@pytest.mark.parametrize('flags,default_tui,expected', [
    ([], False, 'gui'), ([], True, 'tui'),
    (['--tui'], False, 'tui'), (['--once'], False, 'once'),
    (['--once'], True, 'once'), (['--check'], True, 'check'),
    (['--check'], False, 'check'),
])
def test_launch_modes(monkeypatch, flags, default_tui, expected):
    calls = []
    monkeypatch.setattr(cli.logging, 'disable', lambda _: None)
    def launch(mode):
        def run():
            calls.append(mode)
        return run
    monkeypatch.setattr(cli, 'run_gui', launch('gui'))
    monkeypatch.setattr(cli, 'run_once', launch('once'))
    monkeypatch.setattr(cli, 'check_runtime', launch('check'))
    monkeypatch.setattr(cli, 'run_tui', launch('tui'))
    cli.cli(flags, default_mode="tui" if default_tui else "gui")
    assert calls == [expected]


@pytest.mark.parametrize('flags', [ ['--tui', '--once'], ['--check', '--once'], ['--check', '--tui'] ])
def test_conflicting_modes_are_rejected(flags):
    with pytest.raises(SystemExit) as error:
        cli.cli(flags)
    assert error.value.code == 2


@pytest.mark.parametrize('flags', [['--demo'], ['--data-dir', 'unused']])
def test_production_rejects_development_and_settings_flags(flags):
    with pytest.raises(SystemExit) as error:
        cli.cli(flags)
    assert error.value.code == 2


def test_direct_main_rejects_unknown_mode(monkeypatch):
    monkeypatch.setattr(cli.logging, 'disable', lambda _: None)
    with pytest.raises(ValueError, match='Unknown startup mode'):
        cli.main('invalid')


@pytest.mark.parametrize('failure,code,message', [
    (AppError('Synthetic safe error'), 1, 'Synthetic safe error'),
    (KeyboardInterrupt(), 130, 'Operation cancelled'),
    (EOFError(), 130, 'Operation cancelled'),
    (PermissionError('private diagnostic'), 1, 'folder permissions'),
])
def test_failure_reports_exit_status(monkeypatch, capsys, failure, code, message):
    monkeypatch.setattr(cli.logging, 'disable', lambda _: None)
    def fail():
        raise failure
    monkeypatch.setattr(cli, 'run_once', fail)
    with pytest.raises(SystemExit) as error:
        cli.main('once')
    assert error.value.code == code
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
    if outcome == 'success':
        cli.run_once(app)
    else:
        with pytest.raises(SystemExit if outcome == 'skipped' else AppError):
            cli.run_once(app)
    assert calls == (['login', 'clear'] if outcome == 'login_error' else ['login', 'fetch', 'clear'])
    if outcome in {'success', 'skipped'}:
        assert capsys.readouterr().out == 'Synthetic result\nSynthetic warning\n'


def test_check_skips_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.logging, 'disable', lambda _: None)
    def unexpected(*a, **kw):
        pytest.fail('Runtime check must not load settings')
    monkeypatch.setattr(cli, 'Application', unexpected)
    monkeypatch.setattr(cli, 'check_runtime', lambda: None)
    cli.main('check')
    assert not list(tmp_path.iterdir())


def test_production_imports_no_desktop_or_development_modules():
    result = subprocess.run(
        [sys.executable, '-c', 'import notesvault.__main__; import sys; '
         'assert not any(k.startswith(("edifice", "PySide6", "notesvault.gui", "devtools")) for k in sys.modules)'],
        capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
