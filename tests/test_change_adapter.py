from types import SimpleNamespace

import pytest
from pyicloud.common.cloudkit import CKRecord, CKTombstoneRecord, CKErrorItem, CKZoneID
from pyicloud.services.notes.client import NotesApiError

from notesvault import icloud_note_changes as adapter
from notesvault.fetch_control import FetchControl
from notesvault.models import AppError


def raw_service(monkeypatch, records, zone="Notes"):
    class Service:
        def __init__(self):
            self.raw = self
            self.requests = []
        def changes(self, *, zone_req):
            self.requests.append(zone_req)
            yield SimpleNamespace(records=records, zoneID=CKZoneID(zoneName=zone))
    monkeypatch.setattr(adapter, "NotesService", Service)
    return Service()


def test_raw_feed_includes_locked_folders_and_explicit_deletions(monkeypatch):
    service = raw_service(monkeypatch, [
        CKRecord(recordName="locked", recordType="PasswordProtectedNote"),
        CKRecord(recordName="folder", recordType="Folder"),
        CKRecord(recordName="soft", recordType="Note", fields={"Deleted": {"type": "INT64", "value": 1}}),
        CKTombstoneRecord(recordName="gone", deleted=True),
    ])
    changes = list(adapter.read_changes(service, "cursor", FetchControl()))
    assert changes[0].is_locked and changes[1].is_folder
    assert changes[2].is_deleted and changes[3].is_deleted
    request = service.requests[0]
    assert request.syncToken == "cursor"
    assert "PasswordProtectedNote" in request.desiredRecordTypes


@pytest.mark.parametrize("record,error", [
    (CKErrorItem(serverErrorCode="ACCESS_DENIED"), NotesApiError),
    (CKRecord(recordName="unknown", recordType="Unknown"), AppError),
])
def test_raw_errors_and_unknown_content_abort_enumeration(monkeypatch, record, error):
    service = raw_service(monkeypatch, [record])
    with pytest.raises(error):
        list(adapter.read_changes(service, None, FetchControl()))


def test_unrequested_zone_is_rejected_before_ids_can_collide(monkeypatch):
    service = raw_service(monkeypatch, [CKTombstoneRecord(recordName="one", deleted=True)], zone="Shared")
    with pytest.raises(AppError, match="unsupported Notes zone"):
        list(adapter.read_changes(service, None, FetchControl()))
