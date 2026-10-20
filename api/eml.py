# api/eml.py
"""Fresh EML contact intelligence API — process, browse, export, push.
v2: auto-push to CRM DB after dedup+merge."""
import csv, io, json, logging, os, re, time
from fastapi import APIRouter, File, Form, UploadFile, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from core.rate_limit import limiter
from core.auth import verify_token
from db.database import get_db, AsyncSessionLocal
from db.models import Contact, Company
from api.contacts import ContactIn, validate_email, classify_phone, _find_or_create_company
from services import eml_store
from services.llm_router import ChainEntry, extract_json
from services.eml_processor import parse_eml_bytes, extract_local_fields, build_llm_prompt, merge_fields, FIELD_KEYS
from services.eml_dedup_rules import is_duplicate, normalize_email, normalize_phone, normalize_name

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


async def _merge_into_crm(db: AsyncSession, contact: dict) -> dict:
    """Merge-or-create a CRM contact. Returns {crm_id, action} where action is 'created'|'merged'|'skipped'."""
    email = (contact.get("email") or "").strip().lower()
    phone = (contact.get("phone_primary") or "").strip()
    name = (contact.get("name") or "").strip()

    if email and not validate_email(email):
        email = ""
    if phone and classify_phone(phone) == "INVALID":
        phone = ""
    if not email and not phone:
        return {"crm_id": None, "action": "skipped", "reason": "no valid email or phone"}

    # --- Find existing contact by email or phone ---
    existing_contact = None
    existing_company = None

    if email:
        result = await db.execute(
            select(Contact, Company)
            .outerjoin(Company, Contact.company_id == Company.id)
            .filter(Contact.email_primary == email)
            .limit(1)
        )
        row = result.first()
        if row:
            existing_contact, existing_company = row

    if not existing_contact and phone:
        result = await db.execute(
            select(Contact, Company)
            .outerjoin(Company, Contact.company_id == Company.id)
            .filter(Contact.phone_primary == phone)
            .limit(1)
        )
        row = result.first()
        if row:
            existing_contact, existing_company = row

    # Also check by email_secondary (someone's secondary might be this person's primary)
    if not existing_contact and email:
        result = await db.execute(
            select(Contact, Company)
            .outerjoin(Company, Contact.company_id == Company.id)
            .filter(Contact.email_secondary == email)
            .limit(1)
        )
        row = result.first()
        if row:
            existing_contact, existing_company = row

    # Check by name + any phone match (fallback)
    if not existing_contact and name and len(name) >= 3:
        q = select(Contact, Company).outerjoin(Company, Contact.company_id == Company.id)
        q = q.filter(Contact.name.ilike(name))
        if phone:
            q = q.filter(
                (Contact.phone_primary == phone) | (Contact.phone_secondary == phone)
            )
        q = q.limit(1)
        result = await db.execute(q)
        row = result.first()
        if row:
            existing_contact, existing_company = row

    if existing_contact:
        # --- MERGE: enrich existing contact with new data ---
        merged_any = False

        # Merge phone: if new phone is different, store as secondary
        if phone and phone != (existing_contact.phone_primary or ""):
            if not existing_contact.phone_secondary or existing_contact.phone_secondary == "":
                existing_contact.phone_secondary = phone
                merged_any = True
            elif phone != existing_contact.phone_secondary:
                # Both slots full, but keep the newest info — could log this
                pass

        # Merge email: if new email is different, store as secondary
        if email and email != (existing_contact.email_primary or "").lower():
            if not existing_contact.email_secondary or existing_contact.email_secondary == "":
                existing_contact.email_secondary = email
                merged_any = True
            elif email.lower() != (existing_contact.email_secondary or "").lower():
                pass

        # Merge designation/position
        if contact.get("designation") and not existing_contact.position:
            existing_contact.position = contact["designation"]
            merged_any = True

        # Merge name (if existing has no name)
        if name and not existing_contact.name:
            existing_contact.name = name
            merged_any = True

        # Merge company: update or create if the contact had no company
        company_name = (contact.get("company") or "").strip()
        if company_name:
            if not existing_contact.company_id:
                cin = ContactIn(
                    company_name=company_name,
                    address=contact.get("address"),
                    city=contact.get("city"),
                    pincode=contact.get("pincode"),
                    website=contact.get("website"),
                )
                company = await _find_or_create_company(db, company_name, cin)
                existing_contact.company_id = company.id
                merged_any = True
            elif existing_company and existing_company.name:
                # Already has a company — update company fields if they're empty
                for field_map in [("address", "address"), ("city", "city"),
                                  ("pincode", "pincode"), ("website", "website")]:
                    eml_key, co_attr = field_map
                    val = contact.get(eml_key)
                    if val and not getattr(existing_company, co_attr):
                        setattr(existing_company, co_attr, val)
                        merged_any = True

        return {"crm_id": existing_contact.id, "action": "merged" if merged_any else "skipped",
                "reason": "existing contact enriched" if merged_any else "no new data to merge"}
    else:
        # --- CREATE new contact ---
        cin = ContactIn(
            company_name=contact.get("company"),
            contact_name=name or None,
            email_primary=email or None,
            phone_primary=phone or None,
            phone_secondary=contact.get("phone_secondary"),
            address=contact.get("address"),
            city=contact.get("city"),
            pincode=contact.get("pincode"),
            website=contact.get("website"),
            position=contact.get("designation"),
            files=contact.get("source_file"),
        )
        company = await _find_or_create_company(db, cin.company_name, cin) if cin.company_name else None
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
        return {"crm_id": c.id, "action": "created"}


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
    existing_emails = {normalize_email(e_val) for e_val in existing_emails if normalize_email(e_val)}
    existing_phones = {normalize_phone(p) for p in existing_phones if normalize_phone(p)}

    results = []
    counts = {"new": 0, "duplicate": 0, "merged": 0, "error": 0, "failed": 0}
    # ponytail: total LLM budget — keeps the request under the Cloudflare ~100s proxy timeout
    deadline = time.monotonic() + float(os.getenv("EML_PROCESS_BUDGET", "45"))

    # Open a CRM DB session for auto-push
    async with AsyncSessionLocal() as db:
        for uf in files:
            name = uf.filename or "unnamed.eml"
            try:
                raw = await uf.read()
                if not raw:
                    raise ValueError("file is empty")
                if len(raw) > 10 * 1024 * 1024:
                    raise ValueError("file too large (max 10MB)")
                parsed = parse_eml_bytes(raw, name)
                local = extract_local_fields(parsed)
                ai = await extract_json(chain_list, build_llm_prompt(parsed), deadline) if chain_list else None
                extraction = "llm" if ai else "fallback"
                contact = _pick_contact(merge_fields(local, ai), parsed)
                contact["to_emails"] = parsed.to_emails
                contact["cc_emails"] = parsed.cc_emails
                contact["bcc_emails"] = parsed.bcc_emails

                email_id = await eml_store.insert_email({
                    "file_name": name,
                    "subject": parsed.subject,
                    "date": parsed.date,
                    "sender_name": parsed.sender_name,
                    "sender_email": parsed.sender_email,
                    "receiver_name": parsed.receiver_name,
                    "receiver_email": parsed.receiver_email,
                    "to_emails": parsed.to_emails,
                    "cc_emails": parsed.cc_emails,
                    "bcc_emails": parsed.bcc_emails,
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
                    "to_emails": parsed.to_emails,
                    "cc_emails": parsed.cc_emails,
                    "bcc_emails": parsed.bcc_emails,
                    "dedup_status": status,
                    "pushed_to_crm": False,
                })

                # --- AUTO-PUSH: merge into CRM DB ---
                crm_result = {"crm_id": None, "action": "skipped"}
                try:
                    contact["source_file"] = name
                    crm_result = await _merge_into_crm(db, contact)
                    if crm_result["action"] in ("created", "merged"):
                        await eml_store.mark_pushed(cid)
                except Exception as push_err:
                    logger.warning("auto-push failed for %s: %s", name, push_err)
                    crm_result = {"crm_id": None, "action": "push_failed", "reason": str(push_err)}

                if status == "DUPLICATE" and crm_result["action"] in ("merged",):
                    counts["merged"] += 1
                elif crm_result["action"] == "push_failed":
                    # NEW but auto-push blew up — don't report it as saved to CRM
                    counts["failed"] += 1
                elif status == "NEW":
                    counts["new"] += 1
                else:
                    counts["duplicate"] += 1

                results.append({
                    "file": name, "status": status, "extraction": extraction,
                    "contact_id": cid, "email_id": email_id, "contact": contact,
                    "crm": crm_result,
                })
            except Exception as exc:
                logger.exception("process failed for %s", name)
                counts["error"] += 1
                results.append({"file": name, "status": "ERROR", "extraction": "none",
                                "error": str(exc), "contact": None, "crm": None})

        # Commit all CRM changes at once
        try:
            await db.commit()
        except Exception as commit_err:
            logger.exception("CRM auto-push commit failed")
            await db.rollback()
            # Don't fail the whole request — Supabase data is already saved
            for r in results:
                if r.get("crm") and r["crm"].get("action") in ("created", "merged"):
                    r["crm"]["action"] = "commit_failed"

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
    items: list = []
    page = 1
    while True:
        data = await eml_store.list_contacts(_sanitize_search(search), status, pushed,
                                              page=page, page_size=500)
        items.extend(data["items"])
        if len(items) >= data["total"] or not data["items"]:
            break
        page += 1
    cols = ["name", "company", "email", "phone_primary", "phone_secondary", "website", "to_emails", "cc_emails", "bcc_emails", "designation",
            "address", "city", "pincode", "source_file", "dedup_status", "pushed_to_crm"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for row in items:
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
    if contact.get("pushed_to_crm"):
        raise HTTPException(409, "Already pushed")
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
    pushed, failed, ok_ids = 0, [], []
    for cid in body.ids:
        contact = await eml_store.get_contact(cid)
        if not contact:
            failed.append({"id": cid, "error": "not found"})
            continue
        if contact.get("pushed_to_crm"):
            failed.append({"id": cid, "error": "already pushed"})
            continue
        try:
            await _push_one(db, contact)
            ok_ids.append(cid)
        except Exception as e:
            logger.exception("push failed for %s", cid)
            failed.append({"id": cid, "error": getattr(e, "detail", str(e))})
    if ok_ids:
        try:
            await db.commit()
        except Exception:
            logger.exception("bulk push commit failed")
            await db.rollback()
            raise HTTPException(500, "CRM commit failed")
        # only after commit: mark rows as pushed
        for cid in ok_ids:
            await eml_store.mark_pushed(cid)
            pushed += 1
    return {"ok": True, "pushed": pushed, "failed": failed}
