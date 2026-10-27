# services/eml_store.py
"""Thin async wrappers over the EML Supabase project (eml_emails / eml_contacts)."""
import os, logging, re
from supabase import create_client, Client

logger = logging.getLogger(__name__)
_client: Client | None = None

def get_eml_client() -> Client:
    global _client
    if _client is not None:
        return _client
    # ruling: EML store is a SEPARATE Supabase project — never silently fall
    # back to the CRM project, which has no eml_* tables (404s that look like
    # "no contacts" instead of "misconfigured").
    url = os.getenv("EML_SUPABASE_URL", "")
    key = os.getenv("EML_SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise RuntimeError("EML_SUPABASE_URL / EML_SUPABASE_ANON_KEY not set on server")
    _client = create_client(url, key)
    return _client

async def fetch_dedup_keys() -> tuple[set[str], set[str]]:
    sb = get_eml_client()
    rows = sb.table("eml_contacts").select("email, phone_primary").execute().data or []
    emails = {(r.get("email") or "").lower() for r in rows if r.get("email")}
    phones = {r.get("phone_primary") or "" for r in rows if r.get("phone_primary")}
    emails.discard("")
    phones.discard("")
    return emails, phones

async def insert_email(row: dict) -> str:
    sb = get_eml_client()
    data = sb.table("eml_emails").insert(row).execute().data
    return data[0]["id"]

async def insert_contact(row: dict) -> str:
    sb = get_eml_client()
    data = sb.table("eml_contacts").insert(row).execute().data
    return data[0]["id"]

async def get_contact(contact_id: str) -> dict | None:
    sb = get_eml_client()
    data = sb.table("eml_contacts").select("*").eq("id", contact_id).limit(1).execute().data
    return data[0] if data else None

async def get_email(email_id: str) -> dict | None:
    sb = get_eml_client()
    data = sb.table("eml_emails").select("*").eq("id", email_id).limit(1).execute().data
    if not data:
        return None
    email_row = data[0]
    contacts = sb.table("eml_contacts").select("*").eq("source_email_id", email_id).execute().data or []
    email_row["contacts"] = contacts
    return email_row

async def list_contacts(search="", status="", pushed=None, page=1, page_size=50) -> dict:
    sb = get_eml_client()
    q = sb.table("eml_contacts").select("*", count="exact")
    if search:
        # PostgREST's `or()` filter grammar treats () , : * \ " as syntax, so a
        # raw user string could break out of the filter expression. Strip
        # everything but plain text characters and cap the length instead of
        # trusting naive quote removal.
        s = re.sub(r"[^\w@.\- ]", "", search)[:100]
        if s:
            q = q.or_(
                f"name.ilike.%{s}%,email.ilike.%{s}%,phone_primary.ilike.%{s}%,"
                f"phone_secondary.ilike.%{s}%,company.ilike.%{s}%,city.ilike.%{s}%,address.ilike.%{s}%"
            )
    if status in ("NEW", "DUPLICATE"):
        q = q.eq("dedup_status", status)
    if pushed is not None:
        q = q.eq("pushed_to_crm", pushed)
    q = q.order("created_at", desc=True).range((page - 1) * page_size, page * page_size - 1)
    res = q.execute()
    return {"items": res.data or [], "total": res.count or 0}

async def list_emails(page=1, page_size=50) -> dict:
    sb = get_eml_client()
    res = (
        sb.table("eml_emails")
        .select("*", count="exact")
        .order("created_at", desc=True)
        .range((page - 1) * page_size, page * page_size - 1)
        .execute()
    )
    return {"items": res.data or [], "total": res.count or 0}

async def mark_pushed(contact_id: str) -> None:
    sb = get_eml_client()
    sb.table("eml_contacts").update({"pushed_to_crm": True}).eq("id", contact_id).execute()
