# tests/test_eml_processor.py
from services.eml_processor import parse_eml_bytes, extract_local_fields, build_llm_prompt, merge_fields

PLAIN = b"""From: John Doe <john@acme.com>\r
To: sales@client.com\r
Subject: Water Audit Report\r
Date: Mon, 24 Sep 2026 10:00:00 +0000\r
Content-Type: text/plain; charset=utf-8\r
\r
Hello,\r
Please find the report.\r
\r
-- \r
John Doe\r
Manager, Acme Pvt Ltd\r
+91 98765 43210\r
john@acme.com\r
www.acme.com\r
Mumbai 400001\r
"""

def test_parse_headers():
    p = parse_eml_bytes(PLAIN, "a.eml")
    assert p.sender_email == "john@acme.com"
    assert p.sender_name == "John Doe"
    assert p.receiver_email == "sales@client.com"
    assert p.subject == "Water Audit Report"
    assert p.has_signature is True
    assert "John Doe" in p.signature_block

def test_local_extract_phones_company():
    p = parse_eml_bytes(PLAIN, "a.eml")
    f = extract_local_fields(p)
    assert "9876543210" in (f["phone_primary"] or "").replace(" ", "") or f["phone_primary"]
    assert f["email"] == "john@acme.com"
    assert f["company"] and "Acme" in f["company"]
    assert f["website"] and "acme.com" in f["website"]

def test_no_signature_uses_body_tail_flag():
    raw = b"From: a@b.com\r\nTo: c@d.com\r\nSubject: hi\r\n\r\nJust a short note.\r\n"
    p = parse_eml_bytes(raw, "b.eml")
    assert p.has_signature is False

def test_base64_body_decodes():
    import base64
    body = base64.b64encode(b"Call me at 9876543210")
    raw = (b"From: x@y.com\r\nTo: z@w.com\r\nSubject: s\r\n"
           b"Content-Transfer-Encoding: base64\r\n\r\n" + body + b"\r\n")
    p = parse_eml_bytes(raw, "c.eml")
    assert "9876543210" in p.body_text

def test_html_body_stripped_to_text():
    raw = (b"From: x@y.com\r\nTo: z@w.com\r\nSubject: s\r\n"
           b"Content-Type: text/html\r\n\r\n<html><body><p>Hi <b>there</b></p></body></html>")
    p = parse_eml_bytes(raw, "d.eml")
    assert "<html>" not in p.body_text
    assert "Hi" in p.body_text and "there" in p.body_text

def test_multiple_to_joined():
    raw = b"From: a@b.com\r\nTo: one@c.com, two@c.com\r\nSubject: s\r\n\r\nbody\r\n"
    p = parse_eml_bytes(raw, "e.eml")
    assert "one@c.com" in p.receiver_email and "two@c.com" in p.receiver_email

def test_merge_fields_ai_null_keeps_local():
    local = {"name": "John", "email": "j@x.com", "company": None, "designation": None,
             "phone_primary": "9876543210", "phone_secondary": None, "address": None,
             "city": None, "pincode": None, "website": None}
    ai = {"name": None, "email": None, "company": "Acme", "designation": "Manager",
          "phone_primary": None, "phone_secondary": None, "address": None,
          "city": "Mumbai", "pincode": None, "website": None}
    m = merge_fields(local, ai)
    assert m["name"] == "John"
    assert m["company"] == "Acme"
    assert m["designation"] == "Manager"
    assert m["phone_primary"] == "9876543210"
    assert m["city"] == "Mumbai"

def test_prompt_includes_signature_and_subject():
    p = parse_eml_bytes(PLAIN, "a.eml")
    prompt = build_llm_prompt(p)
    assert "Water Audit Report" in prompt
    assert "John Doe" in prompt

def test_website_not_matched_from_email_only_body():
    raw = (b"From: John Doe <john@acme.com>\r\nTo: a@b.com\r\nSubject: hi\r\n\r\n"
           b"Reach me at john@acme.com for details.\r\n")
    p = parse_eml_bytes(raw, "w.eml")
    f = extract_local_fields(p)
    assert f["email"] == "john@acme.com"
    assert f["website"] is None
