"""Retrieve and export notes using a session authenticated by the caller."""
from pathlib import Path

from .models import AppError, SnapshotModel
from .icloud_errors import ReconnectRequired, authentication_required
from .fetch_control import FetchControl
from . import provider_utils
from .icloud_note_changes import read_changes, supports_incremental, expired_cursor, clear_metadata_cache
from .markdown_export import to_markdown


class ICloudNotesProvider:
    def __init__(self, session, account: str):
        self.session = session
        self.account = account

    def fetch(self, directory: Path | None, progress, *, previous=None, previous_cursor=None,
              control: FetchControl | None = None, download_attachments: bool = False) -> SnapshotModel:
        from pyicloud.services.notes.service import NoteLockedError, NoteNotFound
        control = control or FetchControl()
        buffer = provider_utils.ExportBuffer()
        try:
            control.checkpoint()
            service = self.session.notes
            progress("Reading the iCloud Notes list…")
            cursor = service.sync_cursor()
            control.checkpoint()
            scope_warning = ("Coverage is limited to the Notes zone. Separate shared zones and locked content "
                             "are unsupported; unconfirmed absences are retained.")
            if previous is not None and previous_cursor and cursor == previous_cursor:
                progress("iCloud is unchanged; checking existing local backups without downloading.")
                return SnapshotModel(account=self.account, notes=previous, cursor=cursor,
                                     deleted_ids=set(), warnings=[scope_warning])
            incremental = previous is not None and bool(previous_cursor) and supports_incremental(service)
            progress("Reading changed notes..." if incremental else "Scanning all accessible note records...")
            try:
                changes = {change.id: change for change in read_changes(
                    service, previous_cursor if incremental else None, control)}
            except Exception as exc:
                if not incremental or not expired_cursor(exc):
                    raise
                control.checkpoint()
                progress("The sync cursor expired; scanning all accessible note records again.")
                incremental = False
                changes = {change.id: change for change in read_changes(service, None, control)}
            if incremental and any(change.is_folder for change in changes.values()):
                progress("Folders changed; refreshing note metadata and paths.")
                incremental = False
                changes = {change.id: change for change in read_changes(service, None, control)}
            clear_metadata_cache(service)
            active = [change for change in changes.values() if not change.is_deleted and not change.is_folder]
            deleted = {change.id for change in changes.values() if change.is_deleted and not change.is_folder}
            retained = [note for note in previous or [] if note.note_id not in changes] if incremental else []
            result = SnapshotModel(account=self.account, notes=retained, deleted_ids=deleted, warnings=[scope_warning])
            if not download_attachments:
                result.warnings.append("Attachment downloads are disabled. Enable Download attachments in settings to include them.")
            if retained:
                progress(f"Reusing {len(retained)} unchanged notes.")
            locked = unavailable_count = formatting_fallbacks = 0
            for index, summary in enumerate(control.iterate(active), 1):
                progress(f"Downloading note {index} of {len(active)}…")
                try:
                    control.checkpoint()
                    if summary.is_locked:
                        locked += 1
                        result.skipped += 1
                        continue
                    note = service.get(summary.id, with_attachments=download_attachments)
                    control.checkpoint()
                    if note.is_deleted or note.text is None:
                        result.skipped += 1
                        unavailable_count += 1
                        continue
                    attachments = []
                    unavailable = False
                    for attachment in control.iterate((note.attachments or []) if download_attachments else []):
                        if not attachment.download_url:
                            unavailable = True
                            break  # A preview is not an original attachment backup.
                        if directory is None:
                            raise AppError("An attachment download directory is required.")
                        download = directory / provider_utils.stable_id(note.id) / provider_utils.stable_id(attachment.id)
                        download.parent.mkdir(parents=True, exist_ok=True)
                        with download.open("wb") as output:
                            for chunk in control.iterate(attachment.stream(service=service)):
                                output.write(chunk)
                        if attachment.size is not None and download.stat().st_size != attachment.size:
                            raise AppError("An attachment download was incomplete. Existing backups were retained.")
                        attachments.append((attachment.id, attachment.filename or "attachment", download))
                    if unavailable:
                        unavailable_count += 1
                        result.skipped += 1
                        continue
                    control.checkpoint()
                    html = getattr(note, "html", None)
                    if not html and callable(getattr(service, "render_note", None)):
                        html = service.render_note(summary.id, export_mode="lightweight", full_page=False, debug=False)
                        control.checkpoint()
                    text = to_markdown(html) if html else note.text
                    if not text.strip() and note.text.strip():
                        html = None
                        text = note.text
                    if not html:
                        formatting_fallbacks += 1
                    result.notes.append(buffer.retain(provider_utils.render_export(note.id, note.title or "Untitled",
                        text, note.folder_name or "Notes", note.folder_id or "default",
                        note.modified_at.isoformat() if note.modified_at else None, attachments,
                        format_description="Markdown with rich text" if html else "plain text in Markdown; rich formatting is unavailable")))
                except NoteLockedError:
                    locked += 1
                    result.skipped += 1
                except NoteNotFound:
                    unavailable_count += 1
                    result.skipped += 1
            control.checkpoint()
            final_cursor = service.sync_cursor()
            control.checkpoint()
            if final_cursor != cursor:
                raise AppError("Notes changed during the fetch. Existing backups were retained; fetch again.")
            result.complete = result.skipped == 0
            result.cursor = cursor if result.complete else None
            if result.skipped:
                result.warnings.append("Locked, unavailable, or unsupported notes were skipped; all deletions were deferred.")
            if locked:
                result.warnings.append(f"{locked} locked notes could not be exported. Unlock them in Apple Notes to include them.")
            if unavailable_count:
                result.warnings.append(f"{unavailable_count} notes had inaccessible content or attachments; existing exports were retained.")
            if formatting_fallbacks:
                result.warnings.append(f"Rich formatting was unavailable for {formatting_fallbacks} notes; plain text was exported.")
            return result
        except AppError:
            raise
        except Exception as exc:
            control.checkpoint()
            if authentication_required(exc):
                raise ReconnectRequired("Your iCloud session needs sign-in again. Existing backups were retained. Reconnect iCloud, then retry the fetch.") from exc
            raise AppError("iCloud fetch failed. Existing backups were retained. Check your connection or reconnect iCloud.") from exc


