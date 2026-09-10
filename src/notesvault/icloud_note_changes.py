"""PyiCloud 2.7.0 change-feed adapter, including records its list API omits."""
from dataclasses import dataclass

from pyicloud.common.cloudkit import CKRecord, CKErrorItem, CKTombstoneRecord, CKZoneID, CKZoneChangesZoneReq
from pyicloud.services.notes.client import NotesApiError
from pyicloud.services.notes.service import NotesService

from .models import AppError


@dataclass(frozen=True)
class NoteChange:
    id: str
    is_deleted: bool = False
    is_locked: bool = False
    is_folder: bool = False


def read_changes(service, since, control):
    if isinstance(service, NotesService):
        # The public iter_changes filters out PasswordProtectedNote and Folder.
        request = CKZoneChangesZoneReq(
            zoneID=CKZoneID(zoneName="Notes", zoneType="REGULAR_CUSTOM_ZONE"),
            desiredRecordTypes=["Note", "PasswordProtectedNote", "Folder"],
            desiredKeys=["Deleted"], syncToken=since, reverse=False,
        )
        for page in control.iterate(service.raw.changes(zone_req=request)):
            if page.zoneID.zoneName != "Notes" or page.zoneID.zoneType not in (None, "REGULAR_CUSTOM_ZONE"):
                raise AppError("An unsupported Notes zone was returned. Existing backups were retained.")
            for record in control.iterate(page.records):
                if isinstance(record, CKErrorItem):
                    raise NotesApiError("CloudKit could not enumerate a record.", payload=record.model_dump())
                if isinstance(record, CKTombstoneRecord):
                    yield NoteChange(record.recordName, is_deleted=True)
                elif isinstance(record, CKRecord):
                    if record.recordType not in {"Note", "PasswordProtectedNote", "Folder"}:
                        raise AppError("Unsupported record in the Notes change feed. Existing backups were retained.")
                    yield NoteChange(record.recordName, bool(record.fields.get_value("Deleted")),
                                     record.recordType == "PasswordProtectedNote", record.recordType == "Folder")
                else:
                    raise AppError("Incomplete Notes change feed. Existing backups were retained.")
    elif callable(getattr(service, "iter_changes", None)):
        for event in control.iterate(service.iter_changes(since=since)):
            if event.type not in {"updated", "deleted"}:
                raise AppError("Unsupported Notes change event. Existing backups were retained.")
            yield NoteChange(event.note.id, event.type == "deleted", getattr(event.note, "is_locked", False))
    else:
        # Lightweight providers without a change API must enumerate a full snapshot.
        for note in control.iterate(service.iter_all()):
            yield NoteChange(note.id, note.is_deleted, getattr(note, "is_locked", False))


def supports_incremental(service):
    return isinstance(service, NotesService) or callable(getattr(service, "iter_changes", None))


def expired_cursor(error):
    if not isinstance(error, NotesApiError):
        return False
    def expired(value):
        if isinstance(value, dict):
            if value.get("serverErrorCode") in {
                "BAD_SYNC_TOKEN", "INVALID_SYNC_TOKEN", "SYNC_TOKEN_EXPIRED", "CHANGE_TOKEN_EXPIRED",
            }:
                return True
            return any(expired(item) for item in value.values())
        return isinstance(value, list) and any(expired(item) for item in value)
    return expired(error.payload)


def clear_metadata_cache(service):
    if isinstance(service, NotesService):
        # These caches survive fetches in 2.7.0 and otherwise retain old folder names
        # and attachment metadata. Keep version-specific handling in this adapter.
        service._folder_name_cache.clear()
        service._attachment_meta_cache.clear()
