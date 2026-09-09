import argparse
import logging
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from dotenv import load_dotenv

from .app import NotesVaultApp
from .config import ConfigStore, SecretStore
from .models import AppError
from .providers import DemoProvider, ICloudProvider
from .service import run_backup


def main():
    parser = argparse.ArgumentParser(description="Back up iCloud Notes to local Git with an interactive terminal dashboard.")
    parser.add_argument("--demo", action="store_true", help="Use synthetic notes in an isolated temporary directory")
    parser.add_argument("--once", action="store_true", help="Fetch once using saved settings and OS credentials")
    parser.add_argument("--check", action="store_true", help="Check runtime dependencies without accessing an account")
    parser.add_argument("--data-dir", type=Path, help="Override per-user configuration/session storage")
    args = parser.parse_args()
    # Third-party log messages may include note titles or authentication details.
    logging.disable(logging.CRITICAL)
    if args.check:
        import subprocess
        from pyicloud import PyiCloudService
        from pyicloud.services.notes.service import NotesService
        try:
            subprocess.run(["git", "--version"], check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            SecretStore().backend()
            assert callable(PyiCloudService) and callable(NotesService.iter_all)
        except Exception:
            print("Runtime check failed. Verify Git and OS credential-store availability.")
            raise SystemExit(1) from None
        print("Runtime imports OK: Textual, PyiCloud Notes, and OS credential backend. No account accessed.")
        return
    load_dotenv(Path.cwd() / ".env", override=False)
    demo_directory = TemporaryDirectory(prefix="apple-notes-demo-") if args.demo else None
    try:
        store = ConfigStore(Path(demo_directory.name) if demo_directory else args.data_dir)
        if not args.once:
            NotesVaultApp(store, demo=args.demo).run()
            return
        settings = store.load()
        secrets = SecretStore()
        if args.demo:
            provider = DemoProvider()
            settings.backup_folder = str(store.directory / "backups")
            settings.github_repo = ""
        else:
            provider = ICloudProvider(store.directory / "sessions")
            if not settings.apple_id:
                raise AppError("Run the dashboard first to connect iCloud and choose a backup folder.")
            if settings.auth_method == "browser":
                ready = provider.restore_session(settings.apple_id)
            else:
                password = secrets.get(f"icloud:{settings.apple_id}")
                ready = bool(password) and provider.login(settings.apple_id, password)
            if not ready:
                raise AppError("Reconnect iCloud in the dashboard before running --once.")
        result = run_backup(provider, settings, secrets, store.directory / "staging", print)
        settings.last_backup = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        settings.last_result = (f"{result.added} added · {result.updated} updated · {result.deleted} deleted · {result.skipped} skipped"
            f"\nLocal Git: {result.commit}\nGitHub: {result.push}")
        store.save(settings)
        print(f"{result.added} added, {result.updated} updated, {result.deleted} deleted, {result.skipped} skipped.")
        print(f"Local Git: {result.commit}. GitHub: {result.push}.")
        for warning in result.warnings:
            print(warning)
        if result.skipped or (settings.github_repo and not result.push.startswith("Published to ")):
            raise SystemExit(1)
    except AppError as exc:
        print(str(exc))
        raise SystemExit(1) from None
    finally:
        if demo_directory:
            demo_directory.cleanup()


if __name__ == "__main__":
    main()
