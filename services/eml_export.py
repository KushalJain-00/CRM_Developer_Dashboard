"""
Export engine for EML pipeline results.
Generates Excel, CSV, and VCF from processed EML contacts.
"""
import csv
import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


def export_csv(contacts: list[dict]) -> str:
    """Export contacts as CSV string."""
    if not contacts:
        return ""

    fieldnames = [
        "name", "email", "company", "designation",
        "phone_primary", "phone_secondary", "website",
        "address", "city", "pincode", "confidence", "extraction_method"
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for c in contacts:
        writer.writerow(c)

    return output.getvalue()


def export_vcf(contacts: list[dict]) -> str:
    """Export contacts as vCard 3.0."""
    vcards = []
    for c in contacts:
        lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
        ]
        if c.get("name"):
            lines.append(f"FN:{c['name']}")
        if c.get("email"):
            lines.append(f"EMAIL:{c['email']}")
        if c.get("company"):
            lines.append(f"ORG:{c['company']}")
        if c.get("designation"):
            lines.append(f"TITLE:{c['designation']}")
        if c.get("phone_primary"):
            lines.append(f"TEL;TYPE=CELL:{c['phone_primary']}")
        if c.get("phone_secondary"):
            lines.append(f"TEL;TYPE=WORK:{c['phone_secondary']}")
        if c.get("website"):
            lines.append(f"URL:{c['website']}")
        if c.get("address"):
            lines.append(f"ADR:;;{c['address']};;;;")
        lines.append("END:VCARD")
        vcards.append("\r\n".join(lines))

    return "\r\n".join(vcards)


def export_excel_data(contacts: list[dict]) -> dict:
    """Return data structured for XLSX export (3 sheets).

    Returns: {
        "all_contacts": [row, ...],
        "unique_contacts": [row, ...],
        "domain_summary": [{"domain": ..., "count": ...}, ...]
    }
    """
    from collections import Counter

    all_rows = []
    for c in contacts:
        all_rows.append({
            "Name": c.get("name", ""),
            "Email": c.get("email", ""),
            "Company": c.get("company", ""),
            "Designation": c.get("designation", ""),
            "Phone": c.get("phone_primary", ""),
            "Phone2": c.get("phone_secondary", ""),
            "Website": c.get("website", ""),
            "City": c.get("city", ""),
            "Confidence": c.get("confidence", 0),
            "Method": c.get("extraction_method", ""),
        })

    seen_emails = set()
    unique_rows = []
    for c in contacts:
        email = c.get("email", "").lower()
        if email and email not in seen_emails:
            seen_emails.add(email)
            unique_rows.append({
                "Name": c.get("name", ""),
                "Email": email,
                "Company": c.get("company", ""),
                "Designation": c.get("designation", ""),
                "Phone": c.get("phone_primary", ""),
                "City": c.get("city", ""),
            })

    domain_counter = Counter()
    for c in contacts:
        email = c.get("email", "")
        if "@" in email:
            domain = email.split("@")[1].lower()
            domain_counter[domain] += 1

    domain_summary = [
        {"Domain": d, "Count": cnt}
        for d, cnt in domain_counter.most_common(100)
    ]

    return {
        "all_contacts": all_rows,
        "unique_contacts": unique_rows,
        "domain_summary": domain_summary,
    }
