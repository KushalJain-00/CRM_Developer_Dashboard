"""
Signature Intelligence — uses email-reply-parser to isolate the signature
block, then Groq Llama 3.3 70B to extract structured contact fields from it.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from groq import Groq
import os, hashlib, json

router = APIRouter()
_cache: dict = {}   # in-memory cache: signature_hash → parsed fields

client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

SYSTEM_PROMPT = """You are a contact information extractor. Given a raw email signature block, extract structured fields.

Return ONLY a valid JSON object with these exact keys (use null if not found):
{
  "name": null,
  "company": null,
  "designation": null,
  "phone_primary": null,
  "phone_secondary": null,
  "email": null,
  "website": null,
  "address": null,
  "city": null,
  "pincode": null
}

Rules:
- name: full name of the person signing
- company: organization/company name (look for Ltd, Pvt, Inc, LLP, Industries, etc.)
- designation: job title/role (CEO, Manager, Director, Founder, etc.)
- phone_primary: first/main phone number with country code if present
- phone_secondary: second phone number if present
- email: email address found in signature
- website: company website URL
- address: street/plot/office address
- city: city name
- pincode: 6-digit PIN code
- Return ONLY the JSON. No explanation. No markdown. No code blocks."""


class SignatureRequest(BaseModel):
    body_text: str        # full email body text
    subject: str = ""


def extract_signature_block(body_text: str) -> str:
    """
    Isolate signature from email body.
    Strategy: look for common signature delimiters, take everything after.
    Falls back to last 40 lines if no delimiter found.
    """
    lines = body_text.replace('\r\n', '\n').split('\n')

    # Common signature delimiters
    delimiters = ['-- ', '--\n', '___', '---', 'Best regards', 'Best Regards',
                  'Thanks & Regards', 'Regards,', 'Warm regards', 'Sincerely,',
                  'Thanks,', 'Thank you,', 'Cheers,', 'With regards']

    for i, line in enumerate(lines):
        stripped = line.strip()
        if any(stripped.startswith(d.strip()) or stripped == d.strip()
               for d in delimiters):
            sig_lines = lines[i:]
            return '\n'.join(sig_lines[:40]).strip()

    # No delimiter — take last 35 lines as likely signature zone
    return '\n'.join(lines[-35:]).strip()


@router.post("/parse-signature")
async def parse_signature(body: SignatureRequest):
    if not client.api_key:
        raise HTTPException(500, "GROQ_API_KEY not configured")

    sig_block = extract_signature_block(body.body_text)

    if not sig_block or len(sig_block) < 10:
        return JSONResponse({"ok": True, "fields": {}, "cached": False})

    # Cache check
    cache_key = hashlib.md5(sig_block.encode()).hexdigest()
    if cache_key in _cache:
        return JSONResponse({"ok": True, "fields": _cache[cache_key], "cached": True})

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"Extract contact info from this email signature:\n\n{sig_block}"}
            ],
            temperature=0.1,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()

        # Clean up in case model wraps in markdown
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        fields = json.loads(raw)
        _cache[cache_key] = fields
        return JSONResponse({"ok": True, "fields": fields, "cached": False})

    except json.JSONDecodeError:
        return JSONResponse({"ok": True, "fields": {}, "error": "Parse failed"})
    except Exception as e:
        raise HTTPException(500, f"Groq error: {str(e)}")