import subprocess
import sys
from pathlib import Path

import pytest

from devtools import demo
from devtools.synthetic import demo_application
from notesvault.fetch_control import FetchControl
from notesvault.icloud_errors import ReconnectRequired


def test_synthetic_once_uses_production_workflow_without_qt():
    result = subprocess.run(
        [sys.executable, '-c', 'from devtools.demo import main; import sys; main(["--once"]); '
         'assert not any(k.startswith(("edifice", "PySide6", "notesvault.gui")) for k in sys.modules)'],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert '3 added | 0 updated | 0 deleted | 0 skipped' in result.stdout
    assert 'Local Git:' in result.stdout


@pytest.mark.parametrize('flags,runner', [([], 'run_gui'), (['--tui'], 'run_tui'), (['--once'], 'run_once')])
@pytest.mark.parametrize('fail', [False, True])
def test_development_launch_cleans_up_on_every_exit(monkeypatch, flags, runner, fail):
    applications = []
    monkeypatch.setattr(demo.logging, 'disable', lambda _: None)
    def launch(application):
        applications.append(application)
        assert application.connected
        assert application.store.load().apple_id == 'demo@example.invalid'
        assert application.store.directory.is_dir()
        if fail:
            raise KeyboardInterrupt()
    monkeypatch.setattr(demo, runner, launch)
    if fail:
        with pytest.raises(KeyboardInterrupt):
            demo.main(flags)
    else:
        demo.main(flags)
    assert len(applications) == 1
    assert not applications[0].store.directory.exists()
    assert not applications[0].connected


def test_synthetic_authentication_uses_normal_disconnect_and_reconnect_paths():
    with demo_application() as app:
        app.authentication.logout()
        assert not app.connected
        assert app.store.load().apple_id == ''
        with pytest.raises(ReconnectRequired):
            app.fetch(lambda _: None, FetchControl())
        app.authentication.login_saved()
        _, result = app.fetch(lambda _: None, FetchControl())
        assert result.added == 3
