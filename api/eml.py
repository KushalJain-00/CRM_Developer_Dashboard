# api/eml.py
"""Fresh EML contact intelligence API — process, browse, export, push."""
import csv, io, json, logging, re
from fastapi import APIRouter, File, Form, UploadFile, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from core.rate_limit import limiter
from core.auth import verify_token
from db.database import get_db
from db.models import Contact, Company
from api.contacts import ContactIn, validate_email, classify_phone, _find_or_create_company
from services import eml_store
from services.llm_router import ChainEntry, extract_json
from services.eml_processor import parse_eml_bytes, extract_local_fields, build_llm_prompt, merge_fields, FIELD_KEYS
from services.eml_dedup_rules import is_duplicate, normalize_email, normalize_phone

logger = logging.getLogger(__name__)
router = APIRouter(tags=["eml"])

class PushBulkBody(BaseModel):
    ids: List[str]

def _empty_fields() -> dict:
    return {k: None for k in FIELD_KEYS}

def _pick_contact(fields: dict, parsed) -> dict:
    """One contact per email (sender/signature primary). email fallback to sender."""
    out = merge_fields(_empty_fields(), fields)
    if not out.get("email") and parsed.sender_email:
        out["email"] = parsed.sender_email.split(",")[0].strip().lower()
    if not out.get("name") and parsed.sender_name:
        out["name"] = parsed.sender_name
    return out

def _sanitize_search(s: str) -> str:
    """Strip chars that break PostgREST or_ strings; keep alnum/space/@/./-/_."""
    return re.sub(r"[^a-zA-Z0-9 @.\-_]", "", s or "")

@router.post("/eml/process")
@limiter.limit("30/minute")
async def eml_process(
    request: Request,
    files: list[UploadFile] = File(...),
    chain: str = Form("[]"),
):
    try:
        chain_list = [ChainEntry(**c) for c in json.loads(chain or "[]")]
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid chain JSON"})

    try:
        existing_emails, existing_phones = await eml_store.fetch_dedup_keys()
    except Exception as e:
        logger.error("dedup fetch failed: %s", e)
        return JSONResponse(status_code=503, content={"ok": False, "error": f"EML store unavailable: {e}"})
    # ruling: normalize sets before compare — emails lowercase, phones digit-only
    existing_emails = {normalize_email(e) for e in existing_emails if normalize_email(e)}
    existing_phones = {normalize_phone(p) for p in existing_phones if normalize_phone(p)}

    results = []
    counts = {"new": 0, "duplicate": 0, "error": 0}

    for uf in files:
        name = uf.filename or "unnamed.eml"
        try:
            raw = await uf.read()
            if len(raw) > 10 * 1024 * 1024:
                raise ValueError("file too large (max 10MB)")
            parsed = parse_eml_bytes(raw, name)
            local = extract_local_fields(parsed)
            ai = await extract_json(chain_list, build_llm_prompt(parsed)) if chain_list else None
            extraction = "llm" if ai else "fallback"
            contact = _pick_contact(merge_fields(local, ai), parsed)

            email_id = await eml_store.insert_email({
                "file_name": name,
                "subject": parsed.subject,
                "date": parsed.date,
                "sender_name": parsed.sender_name,
                "sender_email": parsed.sender_email,
                "receiver_name": parsed.receiver_name,
                "receiver_email": parsed.receiver_email,
                "body_text": parsed.body_text,
                "has_signature": parsed.has_signature,
            })

            reason = is_duplicate(contact.get("email"), contact.get("phone_primary"),
                                  existing_emails, existing_phones)
            status = "DUPLICATE" if reason else "NEW"
            if not reason:
                if contact.get("email"):
                    existing_emails.add(normalize_email(contact["email"]))
                ph = normalize_phone(contact.get("phone_primary"))
                if len(ph) >= 10:
                    existing_phones.add(ph)

            # still store duplicate rows (with flag) — browseable, not re-pushed silently
            cid = await eml_store.insert_contact({
                **contact,
                "source_email_id": email_id,
                "source_file": name,
                "dedup_status": status,
                "pushed_to_crm": False,
            })
            counts["new" if status == "NEW" else "duplicate"] += 1
            results.append({"file": name, "status": status, "extraction": extraction,
                            "contact_id": cid, "email_id": email_id, "contact": contact})
        except Exception as e:
            logger.exception("process failed for %s", name)
            counts["error"] += 1
            results.append({"file": name, "status": "ERROR", "extraction": "none",
                            "error": str(e), "contact": None})

    return JSONResponse({"ok": True, "results": results, "counts": counts})

@router.get("/eml/contacts")
async def eml_list_contacts(
    search: str = "",
    status: str = "",
    pushed: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    try:
        return await eml_store.list_contacts(_sanitize_search(search), status, pushed, page, page_size)
    except Exception as e:
        raise HTTPException(503, f"EML store unavailable: {e}")

@router.get("/eml/emails")
async def eml_list_emails(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    try:
        return await eml_store.list_emails(page, page_size)
    except Exception as e:
        raise HTTPException(503, f"EML store unavailable: {e}")

@router.get("/eml/emails/{email_id}")
async def eml_get_email(email_id: str):
    row = await eml_store.get_email(email_id)
    if not row:
        raise HTTPException(404, "Email not found")
    return row

@router.get("/eml/contacts/export")
async def eml_export_csv(
    search: str = "",
    status: str = "",
    pushed: Optional[bool] = None,
):
    data = await eml_store.list_contacts(_sanitize_search(search), status, pushed, page=1, page_size=500)
    cols = ["name", "email", "phone_primary", "phone_secondary", "company", "designation",
            "address", "city", "pincode", "website", "source_file", "dedup_status", "pushed_to_crm"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for row in data["items"]:
        w.writerow([row.get(c, "") for c in cols])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=eml_contacts.csv"},
    )

async def _push_one(db: AsyncSession, contact: dict) -> str:
    email = contact.get("email") or ""
    if email and not validate_email(email):
        email = ""
    phone = contact.get("phone_primary") or ""
    if phone and classify_phone(phone) == "INVALID":
        phone = ""
    if not email and not phone:
        raise HTTPException(400, "Contact has no valid email or phone")

    cin = ContactIn(
        company_name=contact.get("company"),
        contact_name=contact.get("name"),
        email_primary=email or None,
        phone_primary=phone or None,
        phone_secondary=contact.get("phone_secondary"),
        address=contact.get("address"),
        city=contact.get("city"),
        pincode=contact.get("pincode"),
        website=contact.get("website"),
        position=contact.get("designation"),
        files=contact.get("source_file"),
        raw_data={k: contact.get(k) for k in FIELD_KEYS},
    )
    company = await _find_or_create_company(db, cin.company_name, cin) if cin.company_name else None
    # ruling: address/city/pincode/website map onto Company (never Contact columns)
    if company:
        for f in ("address", "city", "pincode", "website"):
            v = getattr(cin, f)
            if v and not getattr(company, f):
                setattr(company, f, v)
    c = Contact(
        company_id=company.id if company else None,
        name=cin.contact_name,
        email_primary=cin.email_primary,
        phone_primary=cin.phone_primary,
        phone_secondary=cin.phone_secondary,
        phone_country=classify_phone(phone) if phone else "IN",
        position=cin.position,
        files=cin.files,
    )
    db.add(c)
    await db.flush()
    return str(c.id)

@router.post("/eml/contacts/{contact_id}/push")
async def eml_push_contact(
    contact_id: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(verify_token),
):
    contact = await eml_store.get_contact(contact_id)
    if not contact:
        raise HTTPException(404, "Contact not found")
    crm_id = await _push_one(db, contact)
    await db.commit()
    await eml_store.mark_pushed(contact_id)
    return {"ok": True, "crm_contact_id": crm_id, "pushed": True}

@router.post("/eml/contacts/push-bulk")
async def eml_push_bulk(
    body: PushBulkBody,
    db: AsyncSession = Depends(get_db),
    _user=Depends(verify_token),
):
    pushed, failed = 0, []
    for cid in body.ids:
        contact = await eml_store.get_contact(cid)
        if not contact:
            failed.append({"id": cid, "error": "not found"})
            continue
        try:
            await _push_one(db, contact)
            await eml_store.mark_pushed(cid)
            pushed += 1
        except HTTPException as e:
            failed.append({"id": cid, "error": e.detail})
    await db.commit()
    return {"ok": True, "pushed": pushed, "failed": failed}
