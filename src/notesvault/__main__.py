"""Launch the desktop, terminal dashboard, or noninteractive commands."""
import argparse
from collections.abc import Sequence
from contextlib import nullcontext
import logging
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from dotenv import load_dotenv

from .application import Application
from .config_store import ConfigStoreController
from .fetch_control import FetchControl
from .icloud_secret_store import SecretStoreController
from .models import AppError, ConfigModel


def run_gui(config_store: ConfigStoreController, is_demo: bool = False) -> None:
    """Import Qt only when launching the desktop."""
    from PySide6.QtWidgets import QApplication
    import edifice as ed
    from .gui.dashboard import Dashboard

    application = QApplication.instance() or QApplication([])
    ed.App(Dashboard(config_store, is_demo=is_demo), qapplication=application).start()

def run_tui(store, *, is_demo=False):
    from .tui.tui import TerminalUI
    import sys
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise AppError("--tui requires an interactive terminal. Use --once for noninteractive backups.")
    TerminalUI(Application(store, is_demo=is_demo)).run()

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Back up iCloud Notes to local Git using the desktop or terminal dashboard."
    )
    parser.add_argument("--demo", action="store_true", help="Use synthetic notes in an isolated temporary directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Fetch once using saved settings and OS credentials")
    mode.add_argument("--check", action="store_true", help="Check runtime dependencies without accessing an account")
    mode.add_argument("--tui", action="store_true", help="Open the interactive Rich terminal dashboard")
    parser.add_argument("--data-dir", type=Path, help="Override per-user configuration/session storage")
    return parser.parse_args(argv)

def run_once(store: ConfigStoreController, *, is_demo: bool = False) -> None:
    """Fetch with saved credentials and release the session on every exit path."""
    application = Application(store, is_demo=is_demo)
    try:
        if not is_demo:
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


def main(argv: Sequence[str] | None = None, *, default_tui: bool = False) -> None:
    """Keep explicit modes ahead of the executable's default interface."""
    args = parse_args(argv)
    # Third-party log messages may include note titles or authentication details.
    logging.disable(logging.CRITICAL)
    try:
        if args.check:
            check_runtime()
            return

        load_dotenv(Path.cwd() / ".env", override=False)
        directory_context = (TemporaryDirectory(prefix="apple-notes-demo-")
                             if args.demo else nullcontext(args.data_dir))
        with directory_context as directory:
            store = ConfigStoreController(Path(directory) if directory is not None else None)
            if args.demo:
                store.save(ConfigModel(apple_id="demo", backup_folder=str(store.directory / "backups")))

            if args.once:
                run_once(store, is_demo=args.demo)
            elif args.tui or default_tui:
                run_tui(store, is_demo=args.demo)
            else:
                run_gui(store, is_demo=args.demo)
    except (KeyboardInterrupt, EOFError):
        print("Operation cancelled.")
        raise SystemExit(130) from None
    except AppError as exc:
        print(str(exc))
        raise SystemExit(1) from None
    except OSError:
        print("Could not access local files. Check folder permissions and available disk space, then retry.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
