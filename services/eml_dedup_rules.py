# services/eml_dedup_rules.py
"""Pure dedup helpers — email match or normalized phone ≥10 digits or name match.
Also provides merge helpers to enrich existing contacts with new data."""
import re

def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()

def normalize_phone(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")

def normalize_name(name: str | None) -> str:
    """Lowercase, strip, collapse whitespace for name comparison."""
    n = (name or "").strip().lower()
    return re.sub(r"\s+", " ", n)

def is_duplicate(email, phone, existing_emails: set[str], existing_phones: set[str],
                 name=None, existing_names: set[str] | None = None) -> str | None:
    """Return the reason string if duplicate, else None.
    Checks email, phone, then name (any match = duplicate)."""
    e = normalize_email(email)
    if e and e in existing_emails:
        return "email"
    p = normalize_phone(phone)
    if len(p) >= 10:
        # match if any existing phone contains or equals (handles +91 prefix variance)
        for ep in existing_phones:
            if ep == p or (len(ep) >= 10 and (ep in p or p in ep)):
                return "phone"
    if name and existing_names:
        n = normalize_name(name)
        if n and len(n) >= 3 and n in existing_names:
            return "name"
    return None
