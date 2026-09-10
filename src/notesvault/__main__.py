import argparse
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from dotenv import load_dotenv

from .backup_controller import fetch_backup
from .config_store import ConfigStoreController
from .demo_provider import DemoProvider
from .icloud_authentication_controller import ICloudAuthenticationController
from .icloud_notes_provider import ICloudNotesProvider
from .icloud_secret_store import SecretStoreController
from .models import AppError, ConfigModel


def run_gui(config_store: ConfigStoreController, is_demo: bool = False):
    from PySide6.QtWidgets import QApplication
    import edifice as ed
    from .ui.dashboard import Dashboard

    application = QApplication.instance() or QApplication([])
    ed.App(Dashboard(config_store, is_demo=is_demo), qapplication=application).start()


def main():
    parser = argparse.ArgumentParser(description="Back up iCloud Notes to local Git with a PyEdifice desktop dashboard.")
    parser.add_argument("--demo", action="store_true", help="Use synthetic notes in an isolated temporary directory")
    parser.add_argument("--once", action="store_true", help="Fetch once using saved settings and OS credentials")
    parser.add_argument("--check", action="store_true", help="Check runtime dependencies without accessing an account")
    parser.add_argument("--data-dir", type=Path, help="Override per-user configuration/session storage")
    args = parser.parse_args()
    # Third-party log messages may include note titles or authentication details.
    logging.disable(logging.CRITICAL)
    if args.check:
        import subprocess
        try:
            from .ui.dashboard import Dashboard
            from pyicloud import PyiCloudService
            from pyicloud.services.notes.service import NotesService
            subprocess.run(["git", "--version"], check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            SecretStoreController().backend()
            assert callable(Dashboard) and callable(PyiCloudService) and callable(NotesService.iter_all)
        except Exception:
            print("Runtime check failed. Verify Git and OS credential-store availability.")
            raise SystemExit(1) from None
        print("Runtime imports OK: PyEdifice/Qt, PyiCloud Notes, and OS credential backend. No account accessed.")
        return

    load_dotenv(Path.cwd() / ".env", override=False)
    demo_directory = TemporaryDirectory(prefix="apple-notes-demo-") if args.demo else None
    authentication = None
    try:
        store = ConfigStoreController(Path(demo_directory.name) if demo_directory else args.data_dir)
        if args.demo:
            store.save(ConfigModel(apple_id="demo", backup_folder=str(store.directory / "backups")))
        if not args.once:
            run_gui(store, is_demo=args.demo)
            return
        if args.demo:
            provider = DemoProvider()
        else:
            authentication = ICloudAuthenticationController(store, SecretStoreController())
            authentication.login_saved()
            provider = ICloudNotesProvider(authentication.session, authentication.account)
        _, result = fetch_backup(store, provider, print)
        print(result.summary())
        for warning in result.warnings:
            print(warning)
        if result.skipped:
            raise SystemExit(1)
    except (KeyboardInterrupt, EOFError):
        print("Operation cancelled.")
        raise SystemExit(130) from None
    except AppError as exc:
        print(str(exc))
        raise SystemExit(1) from None
    finally:
        if authentication:
            authentication.clear()
        if demo_directory:
            demo_directory.cleanup()


if __name__ == "__main__":
    main()
