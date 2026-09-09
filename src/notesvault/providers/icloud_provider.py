import hashlib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote

from ..models import AppError, ExportedNote, Snapshot



from . import utils


class ICloudProvider:
    def __init__(self, session_directory: Path):
        self.session_directory = session_directory
        self.api = None
        self.account = ""

    @property
    def connected(self) -> bool:
        return self.api is not None and not self.api.requires_2fa and not self.api.requires_2sa

    def login(self, account: str, password: str) -> bool:
        from pyicloud import PyiCloudService
        self.api = None
        self.account = account.strip().lower()
        try:
            self.api = PyiCloudService(self.account, password,
                cookie_directory=str(self.session_directory / utils.stable_id(self.account)),
                with_family=False, accept_terms=False)
            if self.api.requires_2fa:
                if self.api.security_key_names:
                    raise AppError("This account requires a hardware security key; this version supports code-based 2FA only.")
                self.api.request_2fa_code()
                return False
            if self.api.requires_2sa:
                raise AppError("Legacy two-step authentication is not supported in this version.")
            self.api.notes
            return True
        except AppError:
            self.api = None
            raise
        except Exception as exc:
            self.api = None
            raise AppError("iCloud sign-in failed. Check credentials, iCloud web access, and any pending Apple terms.") from exc

    def verify(self, code: str) -> None:
        try:
            if self.api is None or not self.api.validate_2fa_code(code.strip()):
                raise AppError("The verification code was not accepted. Try again.")
            self.api.trust_session()
            self.api.notes
        except AppError:
            raise
        except Exception as exc:
            raise AppError("Could not verify iCloud. Reconnect and request a new code.") from exc

    def logout(self):
        if self.api is None and self.account:
            from pyicloud import PyiCloudService
            self.api = PyiCloudService(self.account,
                cookie_directory=str(self.session_directory / utils.stable_id(self.account)),
                with_family=False, accept_terms=False, authenticate=False)
        try:
            if self.api:
                # Clear this app's local session even if the remote logout fails.
                try:
                    self.api.logout()
                finally:
                    self.api.session.clear_persistence(remove_files=True)
        finally:
            self.api = None

    def fetch(self, directory: Path, progress, *, previous=None, previous_cursor=None) -> Snapshot:
        if not self.connected:
            raise AppError("Reconnect iCloud before fetching.")
        from pyicloud.services.notes.service import NoteLockedError, NoteNotFound
        try:
            service = self.api.notes
            progress("Reading the iCloud Notes list…")
            cursor = service.sync_cursor()
            if previous is not None and previous_cursor and cursor == previous_cursor:
                progress("iCloud is unchanged; checking existing local backups without downloading.")
                return Snapshot(account=self.account, notes=previous, cursor=cursor)
            summaries = {note.id: note for note in service.iter_all()}
            active = [note for note in summaries.values() if not note.is_deleted]
            result = Snapshot(account=self.account, notes=[])
            for index, summary in enumerate(active, 1):
                progress(f"Downloading note {index} of {len(active)}…")
                try:
                    note = service.get(summary.id, with_attachments=True)
                    if note.is_deleted or note.text is None:
                        result.skipped += 1
                        continue
                    attachments = []
                    unavailable = False
                    for attachment in note.attachments or []:
                        if not attachment.download_url:
                            unavailable = True
                            break  # A preview is not an original attachment backup.
                        download = directory / "downloads" / utils.stable_id(note.id) / utils.stable_id(attachment.id)
                        download.parent.mkdir(parents=True, exist_ok=True)
                        with download.open("wb") as output:
                            for chunk in attachment.stream(service=service):
                                output.write(chunk)
                        if attachment.size is not None and download.stat().st_size != attachment.size:
                            raise AppError("An attachment download was incomplete. Existing backups were retained.")
                        attachments.append((attachment.id, attachment.filename or "attachment", download))
                    if unavailable:
                        result.skipped += 1
                        continue
                    result.notes.append(utils.write_export(directory, note.id, note.title or "Untitled",
                        note.text, note.folder_name or "Notes", note.folder_id or "default",
                        note.modified_at.isoformat() if note.modified_at else None, attachments))
                except (NoteLockedError, NoteNotFound):
                    result.skipped += 1
            if service.sync_cursor() != cursor:
                raise AppError("Notes changed during the fetch. Existing backups were retained; fetch again.")
            result.complete = result.skipped == 0
            result.cursor = cursor if result.complete else None
            if result.skipped:
                result.warnings.append("Locked, unavailable, or unsupported notes were skipped; all deletions were deferred.")
            result.warnings.append("Text and downloadable attachments exported. Rich formatting and shared-zone discovery are not supported yet.")
            return result
        except AppError:
            raise
        except Exception as exc:
            raise AppError("iCloud fetch failed. Existing backups were retained. Check your connection or reconnect iCloud.") from exc


