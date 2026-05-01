"""
Contacts CRUD API — Handles batch import from parser, listing, editing, and deletion.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import sys, os, re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.auth import verify_api_key
from db.database import get_db
from db.models import Company, Contact, SessionData, Record, User

router = APIRouter()


# ── Pydantic Schemas ──────────────────────────────────────────────────

class ContactIn(BaseModel):
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    email_primary: Optional[str] = None
    email_secondary: Optional[str] = None
    phone_primary: Optional[str] = None
    phone_secondary: Optional[str] = None
    phone_country: Optional[str] = "IN"   # ISO country code
    whatsapp: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    product: Optional[str] = None
    position: Optional[str] = None
    raw_data: Optional[dict] = None       # original unmapped JSON for reference


class BatchImportRequest(BaseModel):
    file_name: str
    sheet_name: str
    mapping: dict
    contacts: List[ContactIn]
    user_email: Optional[str] = None


class ContactUpdate(BaseModel):
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    email_primary: Optional[str] = None
    email_secondary: Optional[str] = None
    phone_primary: Optional[str] = None
    phone_secondary: Optional[str] = None
    phone_country: Optional[str] = None
    whatsapp: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    product: Optional[str] = None
    position: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────

INDIAN_MOBILE_RE = re.compile(r"^(\+91[\s\-]?)?[6-9]\d{9}$")
INTL_PHONE_RE = re.compile(r"^\+(?!91)\d{1,3}[\s\-]?\d{5,14}$")
EMAIL_RE = re.compile(r"^[\w.+%-]+@[\w.-]+\.[a-z]{2,}$", re.I)


def classify_phone(num: str) -> str:
    """Return 'IN', a country prefix, or 'INVALID'."""
    cleaned = re.sub(r"[\s\-\(\)]", "", num.strip())
    if INDIAN_MOBILE_RE.match(cleaned):
        return "IN"
    if INTL_PHONE_RE.match(cleaned):
        # Extract country code from +XX or +XXX prefix
        m = re.match(r"^\+(\d{1,3})", cleaned)
        return f"+{m.group(1)}" if m else "INTL"
    # Check if it looks like a bare Indian mobile (no prefix)
    if re.match(r"^[6-9]\d{9}$", cleaned):
        return "IN"
    # Landline / invalid
    return "INVALID"


def validate_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email.strip())) if email else False


def _find_or_create_company(db: Session, name: str, data: ContactIn) -> Company:
    """Find existing company by name or create a new one."""
    if not name:
        return None
    normalized = name.strip().lower()
    existing = db.query(Company).filter(
        Company.name.ilike(normalized)
    ).first()
    if existing:
        return existing
    company = Company(
        name=name.strip(),
        address=data.address,
        city=data.city,
        pincode=data.pincode,
        website=data.website,
        industry=data.industry,
        product=data.product,
    )
    db.add(company)
    db.flush()
    return company


def _contact_to_dict(contact: Contact, company: Company = None) -> dict:
    return {
        "id": contact.id,
        "company_id": contact.company_id,
        "company_name": company.name if company else None,
        "name": contact.name,
        "email_primary": contact.email_primary,
        "email_secondary": contact.email_secondary,
        "phone_primary": contact.phone_primary,
        "phone_secondary": contact.phone_secondary,
        "phone_country": contact.phone_country if hasattr(contact, 'phone_country') else "IN",
        "whatsapp": contact.whatsapp,
        "position": contact.position,
        "address": company.address if company else None,
        "city": company.city if company else None,
        "pincode": company.pincode if company else None,
        "website": company.website if company else None,
        "industry": company.industry if company else None,
        "product": company.product if company else None,
        "created_at": contact.created_at.isoformat() if contact.created_at else None,
        "updated_at": contact.updated_at.isoformat() if contact.updated_at else None,
    }


# ── Routes ────────────────────────────────────────────────────────────

@router.post("/contacts/batch", dependencies=[Depends(verify_api_key)])
async def batch_import(body: BatchImportRequest, db: Session = Depends(get_db)):
    """
    Receives the cleaned, mapped contacts from the frontend after the user
    confirms the field mapping.  Validates, filters, and persists to the DB.
    """
    imported = 0
    skipped = 0
    flagged_foreign = 0

    user_id = None
    if hasattr(body, "user_email") and body.user_email:
        u = db.query(User).filter(User.email == body.user_email).first()
        if u: user_id = u.id


    # Save session metadata
    session = SessionData(
    user_id=user_id,
    file_name=body.file_name,
    sheet_name=body.sheet_name,
    mapping=body.mapping,
    total_records=len(body.contacts),
    )

    db.add(session)
    db.flush()

    # Fetch existing contacts that share the same email or phone to check for full duplicates later
    batch_emails = [item.email_primary for item in body.contacts if item.email_primary]
    batch_phones = [item.phone_primary for item in body.contacts if item.phone_primary]
    
    existing_contacts_data = []
    if batch_emails or batch_phones:
        q = db.query(Contact, Company).outerjoin(Company, Contact.company_id == Company.id)
        from sqlalchemy import or_
        filters = []
        if batch_emails: filters.append(Contact.email_primary.in_(batch_emails))
        if batch_phones: filters.append(Contact.phone_primary.in_(batch_phones))
        if filters:
            q = q.filter(or_(*filters))
            existing_contacts_data = q.all()

    for item in body.contacts:
        # ── Archive raw record FIRST (before any skip/continue) ───
        # This ensures all uploaded rows are persisted for audit,
        # even if they are later skipped as duplicates or invalid.
        if item.raw_data:
            db.add(Record(session_id=session.id, data=item.raw_data))

        # ── Validate email ────────────────────────────────────────
        email_ok = validate_email(item.email_primary) if item.email_primary else False
        if not email_ok:
            item.email_primary = None
        if item.email_secondary and not validate_email(item.email_secondary):
            item.email_secondary = None

        # ── Validate & classify phone ─────────────────────────────
        phone_class = "INVALID"
        if item.phone_primary:
            phone_class = classify_phone(item.phone_primary)
            if phone_class == "INVALID":
                item.phone_primary = None
            else:
                item.phone_country = phone_class

        if item.phone_secondary:
            sec_class = classify_phone(item.phone_secondary)
            if sec_class == "INVALID":
                item.phone_secondary = None

        # ── Rule: must have at least email OR valid mobile ────────
        has_email = item.email_primary is not None
        has_phone = item.phone_primary is not None
        if not has_email and not has_phone:
            skipped += 1
            continue

        # ── Exact Duplicate check ───────────────────────────────────────
        is_exact_dup = False
        for existing_contact, existing_company in existing_contacts_data:
            # Check if this contact matches ALL provided fields
            match = True
            if item.email_primary and existing_contact.email_primary != item.email_primary: match = False
            if match and item.phone_primary and existing_contact.phone_primary != item.phone_primary: match = False
            if match and item.contact_name and existing_contact.name != item.contact_name: match = False
            if match and item.whatsapp and existing_contact.whatsapp != item.whatsapp: match = False
            if match and item.position and existing_contact.position != item.position: match = False
            
            if match and item.company_name:
                if not existing_company or existing_company.name != item.company_name: match = False
            if match and item.city:
                if not existing_company or existing_company.city != item.city: match = False
            if match and item.industry:
                if not existing_company or existing_company.industry != item.industry: match = False
                
            if match:
                is_exact_dup = True
                break
                
        if is_exact_dup:
            skipped += 1
            continue

        # ── Flag foreign numbers ──────────────────────────────────
        if item.phone_country and item.phone_country not in ("IN", "INVALID"):
            flagged_foreign += 1

        # ── Find or create company ────────────────────────────────
        company = _find_or_create_company(db, item.company_name, item)

        # ── Create contact ────────────────────────────────────────
        contact = Contact(
            company_id=company.id if company else None,
            name=item.contact_name,
            email_primary=item.email_primary,
            email_secondary=item.email_secondary,
            phone_primary=item.phone_primary,
            phone_secondary=item.phone_secondary,
            phone_country=item.phone_country,
            whatsapp=item.whatsapp,
            position=item.position,
        )
        db.add(contact)

        imported += 1
        existing_contacts_data.append((contact, company))

    session.imported = imported
    session.skipped  = skipped

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Database error during save: {str(e)}")

    return JSONResponse(content={
        "ok": True,
        "imported": imported,
        "skipped": skipped,
        "flagged_foreign": flagged_foreign,
        "session_id": session.id,
    })


@router.get("/contacts", dependencies=[Depends(verify_api_key)])
async def list_contacts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    search: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Paginated contact listing with optional search and filters.
    Joins Company table for full record view.
    """
    q = db.query(Contact, Company).outerjoin(Company, Contact.company_id == Company.id)

    if search:
        like = f"%{search}%"
        q = q.filter(
            (Contact.name.ilike(like)) |
            (Contact.email_primary.ilike(like)) |
            (Contact.phone_primary.ilike(like)) |
            (Company.name.ilike(like))
        )
    if city:
        q = q.filter(Company.city.ilike(f"%{city}%"))
    if industry:
        q = q.filter(Company.industry.ilike(f"%{industry}%"))

    total = q.count()
    rows = q.order_by(Contact.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return JSONResponse(content={
        "ok": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "contacts": [_contact_to_dict(c, co) for c, co in rows],
    })


@router.get("/contacts/{contact_id}", dependencies=[Depends(verify_api_key)])
async def get_contact(contact_id: int, db: Session = Depends(get_db)):
    row = db.query(Contact, Company).outerjoin(
        Company, Contact.company_id == Company.id
    ).filter(Contact.id == contact_id).first()
    if not row:
        raise HTTPException(404, "Contact not found")
    return JSONResponse(content={"ok": True, "contact": _contact_to_dict(row[0], row[1])})


@router.put("/contacts/{contact_id}", dependencies=[Depends(verify_api_key)])
async def update_contact(contact_id: int, body: ContactUpdate, db: Session = Depends(get_db)):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(404, "Contact not found")

    # Validate email if provided
    if body.email_primary is not None:
        if body.email_primary and not validate_email(body.email_primary):
            raise HTTPException(422, "Invalid email format")
        contact.email_primary = body.email_primary or None

    if body.email_secondary is not None:
        if body.email_secondary and not validate_email(body.email_secondary):
            raise HTTPException(422, "Invalid secondary email format")
        contact.email_secondary = body.email_secondary or None

    # Validate phone if provided
    if body.phone_primary is not None:
        if body.phone_primary:
            pc = classify_phone(body.phone_primary)
            if pc == "INVALID":
                raise HTTPException(422, "Invalid phone number")
        contact.phone_primary = body.phone_primary or None

    if body.phone_secondary is not None:
        contact.phone_secondary = body.phone_secondary or None

    if body.contact_name is not None:
        contact.name = body.contact_name
    if body.whatsapp is not None:
        contact.whatsapp = body.whatsapp
    if body.position is not None:
        contact.position = body.position

    # Update company fields
    if contact.company_id:
        company = db.query(Company).filter(Company.id == contact.company_id).first()
        if company:
            if body.company_name is not None:
                company.name = body.company_name
            if body.address is not None:
                company.address = body.address
            if body.city is not None:
                company.city = body.city
            if body.pincode is not None:
                company.pincode = body.pincode
            if body.website is not None:
                company.website = body.website
            if body.industry is not None:
                company.industry = body.industry
            if body.product is not None:
                company.product = body.product
    else:
        # Contact has no company — create one if company_name is provided
        if body.company_name:
            new_company = Company(
                name=body.company_name,
                address=body.address,
                city=body.city,
                pincode=body.pincode,
                website=body.website,
                industry=body.industry,
                product=body.product,
            )
            db.add(new_company)
            db.flush()
            contact.company_id = new_company.id

    db.commit()
    db.refresh(contact)
    return JSONResponse(content={"ok": True, "message": "Contact updated"})


@router.delete("/contacts/{contact_id}", dependencies=[Depends(verify_api_key)])
async def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(404, "Contact not found")
    db.delete(contact)
    db.commit()
    return JSONResponse(content={"ok": True, "message": "Contact deleted"})


@router.delete("/contacts", dependencies=[Depends(verify_api_key)])
async def delete_multiple(ids: List[int] = Query(...), db: Session = Depends(get_db)):
    """Delete multiple contacts at once. Handles empty lists and chunks
    large batches to avoid exceeding SQL bind-parameter limits."""
    if not ids:
        return JSONResponse(content={"ok": True, "deleted": 0})

    CHUNK_SIZE = 5000
    total_deleted = 0
    for i in range(0, len(ids), CHUNK_SIZE):
        chunk = ids[i : i + CHUNK_SIZE]
        total_deleted += db.query(Contact).filter(
            Contact.id.in_(chunk)
        ).delete(synchronize_session=False)
    db.commit()
    return JSONResponse(content={"ok": True, "deleted": total_deleted})


@router.get("/contacts/stats/summary", dependencies=[Depends(verify_api_key)])
async def contact_stats(db: Session = Depends(get_db)):
    """Quick summary stats for the dashboard."""
    total = db.query(Contact).count()
    with_email = db.query(Contact).filter(Contact.email_primary.isnot(None)).count()
    with_phone = db.query(Contact).filter(Contact.phone_primary.isnot(None)).count()
    companies = db.query(Company).count()

    # City breakdown (top 10)
    from sqlalchemy import func
    city_rows = db.query(Company.city, func.count(Contact.id)).outerjoin(
        Contact, Contact.company_id == Company.id
    ).filter(Company.city.isnot(None)).group_by(Company.city).order_by(
        func.count(Contact.id).desc()
    ).limit(10).all()

    # Industry breakdown (top 10)
    ind_rows = db.query(Company.industry, func.count(Contact.id)).outerjoin(
        Contact, Contact.company_id == Company.id
    ).filter(Company.industry.isnot(None)).group_by(Company.industry).order_by(
        func.count(Contact.id).desc()
    ).limit(10).all()

    return JSONResponse(content={
        "ok": True,
        "total_contacts": total,
        "with_email": with_email,
        "with_phone": with_phone,
        "total_companies": companies,
        "top_cities": [{"city": c, "count": n} for c, n in city_rows],
        "top_industries": [{"industry": i, "count": n} for i, n in ind_rows],
    })
