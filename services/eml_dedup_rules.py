# services/eml_dedup_rules.py
"""Pure dedup helpers — ported from n8n workflow rules."""
import re

def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()

def normalize_phone(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")

def is_duplicate(email, phone, existing_emails: set[str], existing_phones: set[str]) -> str | None:
    e = normalize_email(email)
    if e and e in existing_emails:
        return "email"
    p = normalize_phone(phone)
    if len(p) >= 10:
        # match if any existing phone contains or equals (handles +91 prefix variance)
        for ep in existing_phones:
            if ep == p or (len(ep) >= 10 and (ep in p or p in ep)):
                return "phone"
    return None
