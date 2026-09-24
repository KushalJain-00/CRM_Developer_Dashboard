# tests/test_eml_api.py
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from main import app
from api.eml import eml_push_contact, eml_push_bulk, PushBulkBody

client = TestClient(app)

def test_process_requires_files():
    r = client.post("/api/eml/process", data={"chain": "[]"}, files=[])
    assert r.status_code == 422  # no files field

@patch("api.eml.eml_store")
@patch("api.eml.extract_json", new_callable=AsyncMock)
def test_process_single_new_contact(mock_llm, mock_store):
    mock_llm.return_value = {
        "name": "John Doe", "email": "john@acme.com", "phone_primary": "9876543210",
        "phone_secondary": None, "company": "Acme Pvt Ltd", "designation": "Manager",
        "address": None, "city": "Mumbai", "pincode": "400001", "website": "acme.com",
    }
    mock_store.fetch_dedup_keys = AsyncMock(return_value=(set(), set()))
    mock_store.insert_email = AsyncMock(return_value="eml-1")
    mock_store.insert_contact = AsyncMock(return_value="ct-1")

    raw = (b"From: John Doe <john@acme.com>\r\nTo: sales@x.com\r\nSubject: Hi\r\n\r\n"
           b"-- \r\nJohn Doe\r\nManager\r\n+91 98765 43210\r\n")
    r = client.post(
        "/api/eml/process",
        data={"chain": '[{"provider":"groq","model":"m","api_key":"k"}]'},
        files=[("files", ("hi.eml", raw, "message/rfc822"))],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["counts"]["new"] == 1
    assert body["results"][0]["status"] == "NEW"
    assert body["results"][0]["extraction"] == "llm"
    assert body["results"][0]["contact"]["company"] == "Acme Pvt Ltd"

@patch("api.eml.eml_store")
@patch("api.eml.extract_json", new_callable=AsyncMock)
def test_process_duplicate_email(mock_llm, mock_store):
    mock_llm.return_value = {"name": "J", "email": "dup@x.com", "phone_primary": None,
                             "phone_secondary": None, "company": None, "designation": None,
                             "address": None, "city": None, "pincode": None, "website": None}
    mock_store.fetch_dedup_keys = AsyncMock(return_value=({"dup@x.com"}, set()))
    mock_store.insert_email = AsyncMock(return_value="eml-2")
    mock_store.insert_contact = AsyncMock(return_value="ct-2")
    raw = b"From: J <dup@x.com>\r\nTo: a@b.com\r\nSubject: s\r\n\r\nbody\r\n"
    r = client.post("/api/eml/process", data={"chain": "[]"},
                    files=[("files", ("d.eml", raw, "message/rfc822"))])
    assert r.json()["results"][0]["status"] == "DUPLICATE"

@patch("api.eml.eml_store")
@patch("api.eml.extract_json", new_callable=AsyncMock)
def test_process_empty_chain_uses_fallback(mock_llm, mock_store):
    mock_llm.return_value = None
    mock_store.fetch_dedup_keys = AsyncMock(return_value=(set(), set()))
    mock_store.insert_email = AsyncMock(return_value="eml-3")
    mock_store.insert_contact = AsyncMock(return_value="ct-3")
    raw = (b"From: Alice <alice@z.com>\r\nTo: b@c.com\r\nSubject: s\r\n\r\n-- \r\n"
           b"Alice Shah\r\n+919876543210\r\nalice@z.com\r\n")
    r = client.post("/api/eml/process", data={"chain": "[]"},
                    files=[("files", ("f.eml", raw, "message/rfc822"))])
    res = r.json()["results"][0]
    assert res["status"] == "NEW"
    assert res["extraction"] == "fallback"
    assert res["contact"]["email"] == "alice@z.com"

def test_contacts_list_shape():
    with patch("api.eml.eml_store") as ms:
        ms.list_contacts = AsyncMock(return_value={"items": [], "total": 0})
        r = client.get("/api/eml/contacts?page=1")
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0}

def test_emails_list_shape():
    with patch("api.eml.eml_store") as ms:
        ms.list_emails = AsyncMock(return_value={"items": [], "total": 0})
        r = client.get("/api/eml/emails")
        assert r.status_code == 200

@pytest.mark.asyncio
async def test_push_already_pushed_409():
    with patch("api.eml.eml_store") as ms:
        ms.get_contact = AsyncMock(return_value={"id": "c1", "email": "a@b.com",
                                                 "phone_primary": "9876543210",
                                                 "pushed_to_crm": True})
        with pytest.raises(HTTPException) as ei:
            await eml_push_contact("c1", db=AsyncMock(), _user=None)
    assert ei.value.status_code == 409
    assert ei.value.detail == "Already pushed"

@pytest.mark.asyncio
async def test_bulk_push_already_pushed_fails_without_mark():
    with patch("api.eml.eml_store") as ms:
        ms.get_contact = AsyncMock(return_value={"id": "c1", "email": "a@b.com",
                                                 "phone_primary": "9876543210",
                                                 "pushed_to_crm": True})
        ms.mark_pushed = AsyncMock()
        db = AsyncMock()
        out = await eml_push_bulk(PushBulkBody(ids=["c1"]), db=db, _user=None)
    assert out["pushed"] == 0
    assert out["failed"] == [{"id": "c1", "error": "already pushed"}]
    ms.mark_pushed.assert_not_called()
    db.add.assert_not_called()
