# services/eml_processor.py
"""Parse .eml bytes → headers/body/signature; local field extraction; LLM merge."""
import re, email, html as html_mod
from email import policy
from dataclasses import dataclass

FIELD_KEYS = ["name", "email", "phone_primary", "phone_secondary", "company",
              "designation", "address", "city", "pincode", "website"]

SIG_DELIM = re.compile(
    r"^(?:--\s*$|regards|best regards|thanks|warm regards|sincerely|cheers|"
    r"thanks\s*&\s*regards|thanks\s+and\s+regards|sent from my|with regards)",
    re.I,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}"    # Indian mobile: 10 digits, optional mid-split
    r"|\+\d{1,3}[\s\-]?\d{7,14}"                  # international: min 7 digits after code
)
WEBSITE_RE = re.compile(r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)")
PINCODE_RE = re.compile(r"\b\d{6}\b")
COMPANY_RE = re.compile(
    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Za-z0-9&.\-]+){0,6}\s+"
    r"(?:Pvt\.?\s+Ltd\.?|Limited|Ltd\.?|Inc\.?|LLP|Corporation|Co\.))",
    re.I,
)
CITY_HINTS = re.compile(
    r"\b(Mumbai|Bombay|Delhi|New Delhi|Bangalore|Bengaluru|Chennai|Madras|Kolkata|Calcutta|"
    r"Pune|Hyderabad|Secunderabad|Ahmedabad|Vadodara|Baroda|Surat|Rajkot|Ankleshwar|Bharuch|"
    r"Dahej|Vapi|Valsad|Navsari|Gandhinagar|Bhavnagar|Jamnagar|Morbi|Kutch|Thane|Navi Mumbai|"
    r"Nashik|Aurangabad|Nagpur|Kolhapur|Solapur|Noida|Greater Noida|Gurgaon|Gurugram|Faridabad|"
    r"Ghaziabad|Jaipur|Udaipur|Jodhpur|Indore|Bhopal|Gwalior|Jabalpur|Lucknow|Kanpur|Agra|"
    r"Varanasi|Chandigarh|Mohali|Panchkula|Ludhiana|Amritsar|Jalandhar|Dehradun|Haridwar|"
    r"Roorkee|Kochi|Cochin|Trivandrum|Thiruvananthapuram|Coimbatore|Madurai|Trichy|Tiruchirappalli|"
    r"Visakhapatnam|Vizag|Vijayawada|Guntur|Bhubaneswar|Cuttack|Patna|Ranchi|Jamshedpur|Raipur|"
    r"Guwahati|Panoli|Halol|Kalol|Sanand|Chhatral|Tarapur|Baddi|Pithampur|Dewas|Daman|Silvassa|"
    r"Singapore|Dubai|Abu Dhabi|Sharjah|Doha|Riyadh|Jeddah|London|New York|Chicago|Houston|"
    r"Dallas|San Francisco|Los Angeles|Toronto|Vancouver|Sydney|Melbourne|Tokyo|Hong Kong)\b",
    re.I,
)
LOCATION_PREFIX_RE = re.compile(
    r"^(?:Location|Address|Plant|Works|Factory|Office|Regd\.?\s*Office|Head\s*Office|Branch|Unit(?:\s*-\s*[I|V|X\d]+)?)\s*[:\-]\s*(.+)$",
    re.I,
)
ADDRESS_LINE_RE = re.compile(
    r"\b(?:Plot\s+No\.?|Survey\s+No\.?|GIDC|Industrial\s+(?:Area|Estate)|Phase\s+[I|V|X\d]+|Sector\s+\d+|Road|Marg|Street|Floor|Towers?|Building|Opp\.?|Near|Dist\.?|District)\b",
    re.I,
)
# Reject lines that look like greetings/salutations/departments — not real person names
NAME_REJECT = re.compile(
    r"^(?:dear\b|hi\b|hello\b|thank|please|regards|sir|madam|to whom"
    r"|purchase\s+dep|ehs\s|new\s+corporate|image\d|\*+$)"
    r"|@|\bsent\s+from\b",
    re.I,
)

@dataclass
class ParsedEml:
    file_name: str = ""
    subject: str = ""
    date: str = ""
    sender_name: str = ""
    sender_email: str = ""
    receiver_name: str = ""
    receiver_email: str = ""
    to_emails: str = ""
    cc_emails: str = ""
    bcc_emails: str = ""
    body_text: str = ""
    has_signature: bool = False
    signature_block: str = ""

def _decode_part(part) -> str:
    try:
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    except Exception:
        return ""

def _html_to_text(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html_mod.unescape(text)

def _addr(msg, header: str) -> tuple[str, str]:
    raw_list = msg.get_all(header, [])
    pairs = email.utils.getaddresses(raw_list)
    if not pairs:
        return "", ""
    names = ", ".join(n for n, a in pairs if n)
    addrs = ", ".join(a for n, a in pairs if a)
    return names, addrs

def _find_signature(body: str) -> tuple[bool, str]:
    lines = [ln.rstrip() for ln in body.splitlines()]
    nonempty = [(i, ln.strip()) for i, ln in enumerate(lines) if ln.strip()]
    for idx, (orig_i, ln) in enumerate(nonempty):
        if SIG_DELIM.search(ln):
            return True, "\n".join(lines[orig_i:])[:2500]
    # heuristic: trailing cluster with phone or email
    tail = nonempty[-12:] if len(nonempty) > 12 else nonempty
    tail_text = "\n".join(ln for _, ln in tail)
    if EMAIL_RE.search(tail_text) and PHONE_RE.search(tail_text):
        return True, tail_text[:2500]
    if len(nonempty) >= 3 and PHONE_RE.search(tail_text):
        return True, tail_text[:2500]
    return False, ""

def parse_eml_bytes(raw: bytes, file_name: str) -> ParsedEml:
    msg = email.message_from_bytes(raw, policy=policy.default)
    sender_name, sender_email = _addr(msg, "From")
    receiver_name, receiver_email = _addr(msg, "To")
    cc_name, cc_email = _addr(msg, "Cc")
    bcc_name, bcc_email = _addr(msg, "Bcc")
    
    to_emails_str = receiver_email
    cc_emails_str = cc_email  # preserve raw CC list
    bcc_emails_str = bcc_email # preserve raw Bcc list
    
    if cc_email:
        receiver_email = (receiver_email + ", " + cc_email).strip(", ")
        if cc_name:
            receiver_name = (receiver_name + ", " + cc_name).strip(", ")
    if bcc_email:
        receiver_email = (receiver_email + ", " + bcc_email).strip(", ")
        if bcc_name:
            receiver_name = (receiver_name + ", " + bcc_name).strip(", ")

    body_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart" or part.get_filename():
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain":
                body_parts.append(_decode_part(part))
            elif ctype == "text/html" and not body_parts:
                body_parts.append(_html_to_text(_decode_part(part)))
    else:
        ctype = msg.get_content_type()
        text = _decode_part(msg)
        body_parts.append(_html_to_text(text) if ctype == "text/html" else text)

    body = "\n".join(p for p in body_parts if p).strip()
    # strip quoted history
    body = re.split(
        r"(?m)^(?:-{3,}\s*Forwarded message\s*-{3,}|-{3,}\s*Original Message\s*-{3,}|From:.*\nSent:|On .+ wrote:)",
        body, maxsplit=1, flags=re.I,
    )[0].strip()
    has_sig, sig = _find_signature(body)
    return ParsedEml(
        file_name=file_name,
        subject=str(msg.get("Subject") or ""),
        date=str(msg.get("Date") or ""),
        sender_name=sender_name,
        sender_email=sender_email,
        receiver_name=receiver_name,
        receiver_email=receiver_email,
        to_emails=to_emails_str,
        cc_emails=cc_emails_str,
        bcc_emails=bcc_emails_str,
        body_text=body[:8000],
        has_signature=has_sig,
        signature_block=sig,
    )

def extract_local_fields(parsed: ParsedEml) -> dict:
    zone = parsed.signature_block or parsed.body_text
    fields = {k: None for k in FIELD_KEYS}
    em = EMAIL_RE.search(zone) or EMAIL_RE.search(parsed.body_text) or EMAIL_RE.search(parsed.sender_email or "")
    if em:
        fields["email"] = em.group(0).lower()
    phones = PHONE_RE.findall(zone) or PHONE_RE.findall(parsed.body_text)
    if phones:
        fields["phone_primary"] = phones[0].strip()
        if len(phones) > 1:
            fields["phone_secondary"] = ", ".join(p.strip() for p in phones[1:])
    cm = COMPANY_RE.search(zone)
    if cm:
        fields["company"] = cm.group(0).strip()
    # ponytail: blank emails first so "john@acme.com" is not accepted as a website
    wm = WEBSITE_RE.search(EMAIL_RE.sub(" ", zone))
    if wm:
        fields["website"] = wm.group(0).strip()
    pm = PINCODE_RE.search(zone)
    if pm:
        fields["pincode"] = pm.group(0)

    # Location / Address / Destination extraction from signature or body
    sig_lines = (parsed.signature_block or parsed.body_text).splitlines()
    for ln in sig_lines:
        s = ln.strip()
        if not s or EMAIL_RE.search(s) or PHONE_RE.search(s) or WEBSITE_RE.search(s):
            continue
        loc_m = LOCATION_PREFIX_RE.match(s)
        if loc_m:
            val = loc_m.group(1).strip()
            if not fields["address"]:
                fields["address"] = val
            ch = CITY_HINTS.search(val)
            if ch and not fields["city"]:
                fields["city"] = ch.group(0).title()
            break
        elif ADDRESS_LINE_RE.search(s) and not fields["address"]:
            fields["address"] = s
            ch = CITY_HINTS.search(s)
            if ch and not fields["city"]:
                fields["city"] = ch.group(0).title()

    if not fields["city"]:
        city = CITY_HINTS.search(zone)
        if city:
            fields["city"] = city.group(0).title()
    # name: first non-empty signature line that isn't delimiter/email/phone
    if parsed.has_signature:
        for ln in parsed.signature_block.splitlines():
            s = ln.strip()
            if not s or SIG_DELIM.search(s) or EMAIL_RE.search(s) or PHONE_RE.search(s):
                continue
            if COMPANY_RE.search(s) or WEBSITE_RE.search(s):
                continue
            if NAME_REJECT.search(s):
                continue
            # Strip markdown bold markers and pipe-delimited suffixes
            cleaned = re.sub(r"^\*+|\*+$", "", s).strip()
            inline_desig = None
            if "|" in cleaned:
                parts = cleaned.split("|", 1)
                cleaned = parts[0].strip()
                inline_desig = parts[1].strip() if len(parts) > 1 else None
            # Extract designation from parenthesized suffix: "Name (Title)"
            paren_m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", cleaned)
            if paren_m:
                cleaned = paren_m.group(1).strip()
                if not inline_desig:
                    inline_desig = paren_m.group(2).strip()
            if len(cleaned.split()) >= 2 and len(cleaned) <= 50:
                fields["name"] = cleaned
                if inline_desig and not fields.get("designation"):
                    fields["designation"] = inline_desig
                # designation often next line "Role, Company" or "Role"
                break
        # designation: line after name containing role keywords
        if fields["name"]:
            lines = [ln.strip() for ln in parsed.signature_block.splitlines() if ln.strip()]
            for i, ln in enumerate(lines):
                if fields["name"] in ln and i + 1 < len(lines):
                    nxt = lines[i + 1]
                    if re.search(r"manager|director|engineer|executive|president|head|associate|founder|sales|ceo|cto|coordinator|officer|analyst|consultant|lead|supervisor|owner|proprietor", nxt, re.I):
                        fields["designation"] = nxt.split(",")[0].strip()
                        break
    elif parsed.sender_name and not NAME_REJECT.search(parsed.sender_name):
        fields["name"] = re.sub(r"^\*+|\*+$", "", parsed.sender_name).strip()
    if not fields["email"] and parsed.sender_email:
        fields["email"] = parsed.sender_email.split(",")[0].strip().lower()
    return fields

def build_llm_prompt(parsed: ParsedEml) -> str:
    zone = parsed.signature_block or parsed.body_text[:2500]
    return (
        f"Subject: {parsed.subject}\n"
        f"From: {parsed.sender_name} <{parsed.sender_email}>\n"
        f"To: {parsed.receiver_name} <{parsed.receiver_email}>\n"
        f"Date: {parsed.date}\n"
        f"Signature detected: {parsed.has_signature}\n"
        f"--- SIGNATURE/BODY ---\n{zone}"
    )

def merge_fields(local: dict, ai: dict | None) -> dict:
    out = {}
    for k in FIELD_KEYS:
        av = (ai or {}).get(k)
        lv = local.get(k)
        if av is not None and str(av).strip() and str(av).strip().lower() != "null":
            out[k] = str(av).strip()
        else:
            out[k] = lv if lv is not None else None
    return out
