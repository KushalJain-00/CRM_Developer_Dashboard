"""API-level tests: batch dedup, phone classification, call-date Z handling,
history export merging, auth enforcement."""
import pytest
from datetime import datetime

from main import app
from core.auth import verify_token
from api.contacts import classify_phone
from db.models import SessionData, Record, Contact, CallLog


def _batch(contacts, file_name="t.xlsx"):
    return {"file_name": file_name, "sheet_name": "Sheet1",
            "mapping": {"Name": "contact"}, "contacts": contacts}


class TestBatchDedup:
    def test_same_contact_twice_imports_once(self, client):
        c = {"contact_name": "Dup Doe", "email_primary": "intra-dup@example.com",
             "phone_primary": "9876511101", "company_name": "IntraDupCo"}
        r = client.post("/api/contacts/batch", json=_batch([c, dict(c)]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 1
        assert body["skipped"] >= 1

    def test_two_distinct_contacts_both_imported(self, client):
        a = {"contact_name": "Alpha", "email_primary": "alpha-dist@example.com",
             "phone_primary": "9876511102", "company_name": "DistCoA"}
        b = {"contact_name": "Bravo", "email_primary": "bravo-dist@example.com",
             "phone_primary": "9876511103", "company_name": "DistCoB"}
        r = client.post("/api/contacts/batch", json=_batch([a, b]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 2
        assert body["skipped"] == 0

    def test_duplicate_against_existing_db_contact(self, client):
        c = {"contact_name": "Repeat Rhee", "email_primary": "repeat-rhee@example.com",
             "phone_primary": "9876511104", "company_name": "RepeatCo"}
        first = client.post("/api/contacts/batch", json=_batch([c]))
        assert first.status_code == 200 and first.json()["imported"] == 1, first.text
        second = client.post("/api/contacts/batch", json=_batch([c], file_name="again.xlsx"))
        assert second.status_code == 200, second.text
        body = second.json()
        assert body["imported"] == 0
        assert body["skipped"] >= 1


class TestClassifyPhone:
    def test_classify_phone_edge_cases(self):
        # verified against api.contacts.classify_phone — see report for the +44 quirk
        assert classify_phone("+919876543210") == "IN"
        assert classify_phone("+91-98765-43210") == "IN"
        assert classify_phone("9876543210") == "IN"
        assert classify_phone("(98765) 43210") == "IN"
        assert classify_phone("1-415-555-0123") == "INVALID"
        assert classify_phone("5123456789") == "INVALID"
        uk = classify_phone("+44 20 7946 0958")
        assert uk.startswith("+44") and uk != "INVALID"


class TestCallLogZDates:
    @pytest.mark.asyncio
    async def test_call_date_and_next_action_date_with_z_suffix(self, client, db_session):
        contact = Contact(name="Zed Caller", email_primary="zed-caller@example.com",
                          phone_primary="9876511105")
        db_session.add(contact)
        await db_session.commit()

        r = client.post("/api/calls", json={
            "contact_id": contact.id,
            "call_date": "2026-01-15T10:30:00Z",
            "call_type": "Outgoing",
            "outcome": "Connected",
            "notes": "z-suffix date guard",
        })
        assert r.status_code == 200, r.text
        log_id = r.json()["call_log"]["id"]

        r2 = client.put(f"/api/calls/{log_id}", json={
            "next_action": "Follow up",
            "next_action_date": "2026-01-20T09:00:00Z",
        })
        assert r2.status_code == 200, r2.text


class TestHistoryExport:
    @pytest.mark.asyncio
    async def test_export_merges_call_logs(self, client, db_session):
        session = SessionData(file_name="hist.xlsx", sheet_name="Sheet1",
                              mapping={"Name": "contact"}, total_records=1)
        db_session.add(session)
        await db_session.flush()
        # record links to the DB contact by mixed-case email ONLY (no phone) —
        # guards the case-insensitive fix in crud/history.find_contacts_by_emails
        db_session.add(Record(session_id=session.id, data={
            "Name": "Jane Doe", "Email 1": "Jane@Example.COM"}))
        contact = Contact(name="Jane Doe", email_primary="jane@example.com",
                          phone_primary="9876511106")
        db_session.add(contact)
        await db_session.flush()
        db_session.add(CallLog(contact_id=contact.id, call_date=datetime(2026, 1, 1, 12, 0),
                               call_type="Outgoing", outcome="Connected",
                               notes="integration call"))
        await db_session.commit()

        r = client.get(f"/api/history/{session.id}/export")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        rec = body["records"][0]
        assert rec["_total_calls"] == 1
        assert rec["_last_call_type"] == "Outgoing"
        assert "integration call" in rec["_last_notes"]


class TestAuthEnforcement:
    def test_protected_route_requires_token(self, client):
        # router-level Depends(verify_token) in main.py covers GET too;
        # pop the override and both must reject
        saved = app.dependency_overrides.pop(verify_token, None)
        try:
            assert client.get("/api/contacts").status_code in (401, 403)
            r = client.put("/api/contacts/1", json={"contact_name": "nope"})
            assert r.status_code in (401, 403), r.text
        finally:
            if saved is not None:
                app.dependency_overrides[verify_token] = saved
