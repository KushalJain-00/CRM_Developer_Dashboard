"""
Contact deduplication and merge for EML pipeline.
Multi-signal matching: exact email > exact phone > fuzzy name + company.
"""
import re
from difflib import SequenceMatcher


def _normalize_email(email):
    if not email:
        return ""
    return email.strip().lower()


def _normalize_phone(phone):
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    # ponytail: simple IN country code strip; add intl handling when needed
    if len(digits) >= 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def _name_similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _domain_from_email(email):
    if not email or "@" not in email:
        return ""
    return email.split("@")[-1].strip().lower()


def _exact_key(contact):
    email = _normalize_email(contact.get("email_primary", ""))
    phone = _normalize_phone(contact.get("phone_primary", ""))
    name = (contact.get("name") or "").strip().lower()
    return f"{email}|{phone}|{name}"


def _merge_group(group):
    """Merge duplicates: keep newest, fill blanks from older entries."""
    # Sort by created_at descending so newest is first
    sorted_group = sorted(
        group,
        key=lambda c: c.get("created_at") or "",
        reverse=True,
    )
    base = dict(sorted_group[0])
    for other in sorted_group[1:]:
        for key in ("name", "email_primary", "phone_primary", "company",
                     "position", "city", "address", "website"):
            if not base.get(key) and other.get(key):
                base[key] = other[key]
    return base


def deduplicate_contacts(contacts):
    """Returns (unique_contacts, duplicate_groups).

    duplicate_groups is a list of lists — each inner list is the group
    of original contacts that were merged into one unique contact.
    """
    if not contacts:
        return [], []

    # Phase 1: group by exact key (email + phone + name)
    exact_groups = {}
    for c in contacts:
        key = _exact_key(c)
        exact_groups.setdefault(key, []).append(c)

    # Merge exact groups first, keep track of which originals were merged
    exact_dup_groups = [g for g in exact_groups.values() if len(g) > 1]
    representatives = [_merge_group(g) for g in exact_groups.values()]

    # Phase 2: fuzzy match on merged representatives
    merged = []
    used = set()
    fuzzy_dup_groups = []

    for i, rep_a in enumerate(representatives):
        if i in used:
            continue
        cluster = [rep_a]
        email_a = _normalize_email(rep_a.get("email_primary", ""))
        domain_a = _domain_from_email(email_a)
        name_a = (rep_a.get("name") or "").strip()

        for j, rep_b in enumerate(representatives):
            if j <= i or j in used:
                continue
            name_b = (rep_b.get("name") or "").strip()
            email_b = _normalize_email(rep_b.get("email_primary", ""))
            domain_b = _domain_from_email(email_b)

            sim = _name_similarity(name_a, name_b)
            same_domain = domain_a and domain_b and domain_a == domain_b

            if (sim >= 0.90) or (sim >= 0.85 and same_domain):
                cluster.append(rep_b)
                used.add(j)

        used.add(i)
        if len(cluster) > 1:
            fuzzy_dup_groups.append(cluster)
        merged.append(_merge_group(cluster))

    all_dup_groups = exact_dup_groups + fuzzy_dup_groups
    return merged, all_dup_groups
