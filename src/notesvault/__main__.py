"""Launch the desktop, interactive command line, or noninteractive commands."""
import argparse
from collections.abc import Sequence
import logging
import subprocess
import sys
from typing import Literal

from .application import Application
from .fetch_control import FetchControl
from .icloud_secret_store import SecretStoreController
from .models import AppError


def run_gui(application: Application | None = None) -> None:
    """Import Qt only when launching the desktop."""
    from PySide6.QtWidgets import QApplication
    import edifice as ed
    from .gui.dashboard import Dashboard

    qt = QApplication.instance() or QApplication([])
    ed.App(Dashboard(application or Application()), qapplication=qt).start()


def run_tui(application: Application | None = None) -> None:
    """Launch the prompt-based command line with interactive input and output."""
    from .terminal import TerminalCLI

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise AppError("--tui requires an interactive terminal. Use --once for noninteractive backups.")
    TerminalCLI(application or Application()).run()

def run_once(application: Application | None = None) -> None:
    """Fetch with saved credentials and release the session on every exit path."""
    application = application or Application()
    try:
        application.authentication.login_saved()
        _, result = application.fetch(print, FetchControl())
        print(result.summary())
        for warning in result.warnings:
            print(warning)
        if result.skipped:
            raise SystemExit(1)
    finally:
        application.authentication.clear()


def check_runtime() -> None:
    """Check local dependencies without loading settings or accessing an account."""
    component = "PyEdifice/Qt and PyiCloud imports"
    try:
        from .gui.dashboard import Dashboard
        from pyicloud import PyiCloudService
        from pyicloud.services.notes.service import NotesService

        if not all(callable(value) for value in (Dashboard, PyiCloudService, NotesService.iter_all)):
            raise AppError("Runtime dependencies expose an incompatible API.")
        component = "Git availability on PATH"
        subprocess.run(
            ["git", "--version"], check=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        component = "OS credential-store availability"
        SecretStoreController().backend()
    except Exception as exc:
        raise AppError(f"Runtime check failed. Verify {component}.") from exc
    print("Runtime imports OK: PyEdifice/Qt, PyiCloud Notes, and OS credential backend. No account accessed.")


def main(mode: Literal["check", "once", "tui", "gui"] = "gui") -> None:
    """Start the selected interface or command using default per-user settings."""
    # Third-party log messages may include note titles or authentication details.
    logging.disable(logging.CRITICAL)
    try:
        match mode:
            case "check":
                check_runtime()
            case "once":
                run_once()
            case "tui":
                run_tui()
            case "gui":
                run_gui()
            case _:
                raise ValueError(f"Unknown startup mode: {mode!r}")

    except (KeyboardInterrupt, EOFError):
        print("Operation cancelled.")
        raise SystemExit(130) from None

    except AppError as exc:
        print(str(exc))
        raise SystemExit(1) from None

    except OSError:
        print("Could not access local files. Check folder permissions and available disk space, then retry.")
        raise SystemExit(1) from None


def cli(argv: Sequence[str] | None = None, *, default_mode: Literal["gui", "tui"] = "gui") -> None:
    """Translate command-line arguments into a startup mode."""
    parser = argparse.ArgumentParser(
        description="Back up iCloud Notes to local Git using the desktop or command line."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", dest="mode", action="store_const", const="once",
                      help="Fetch once using saved settings and OS credentials")
    mode.add_argument("--check", dest="mode", action="store_const", const="check",
                      help="Check runtime dependencies without accessing an account")
    mode.add_argument("--tui", dest="mode", action="store_const", const="tui",
                      help="Open the interactive command line")
    parser.set_defaults(mode=default_mode)
    main(parser.parse_args(argv).mode)


if __name__ == "__main__":
    cli()
