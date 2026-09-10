import os
import subprocess
import sys


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
