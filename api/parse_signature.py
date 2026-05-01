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

SYSTEM_PROMPT = """You are an expert contact information extractor specialized in parsing email signatures. 

Your task is to identify and extract structured data for EVERY distinct individual found in the signature block.

Return ONLY a valid JSON array of objects. Use null if a field is not found.

Rules for accuracy:
1. **Association**: Strictly associate phone numbers, job titles, and companies with the person they belong to. 
2. **Multiple Contacts**: If you see multiple signatures (e.g., from a thread or a shared signature), return one object per person.
3. **Phones**: Only assign a phone number to a person if it is physically near their name or clearly belongs to their specific signature block.
4. **Name**: Extract the full name. 
5. **JSON Schema**:
[
  {
    "name": "Full Name",
    "company": "Company Name",
    "designation": "Job Title",
    "phone_primary": "Main Phone",
    "phone_secondary": "Alt Phone",
    "email": "Email Address",
    "website": "URL",
    "address": "Full Address",
    "city": "City",
    "pincode": "PIN/Zip"
  }
]

Do not include any intro, outro, or markdown code blocks. Just the raw JSON array."""


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
    delimiters = ['--', '___', '---', 'best regards', 'thanks & regards', 'thanks and regards',
                  'regards,', 'warm regards', 'sincerely,', 'thanks,', 'thank you,', 'cheers,', 'with regards']

    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        # Look for signature delimiters
        if any(stripped.startswith(d) for d in delimiters):
            # Take from the delimiter to the end, but cap at 100 lines for safety
            sig_lines = lines[i:]
            return '\n'.join(sig_lines[:100]).strip()

    # If no delimiter, take the last 50 lines to catch multi-person signatures in long threads
    return '\n'.join(lines[-50:]).strip()


@router.post("/parse-signature")
async def parse_signature(body: SignatureRequest):
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise HTTPException(500, "GROQ_API_KEY not configured")

    sig_block = extract_signature_block(body.body_text)

    if not sig_block or len(sig_block) < 10:
        return JSONResponse({"ok": True, "fields": [], "cached": False})

    # Cache check
    cache_key = hashlib.md5(sig_block.encode()).hexdigest()
    if cache_key in _cache:
        return JSONResponse({"ok": True, "fields": _cache[cache_key], "cached": True})

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"Extract contact info from this email signature:\n\n{sig_block}"}
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        raw = response.choices[0].message.content.strip()

        # Clean up in case model wraps in markdown
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        fields = json.loads(raw)
        
        # Cache limit
        if len(_cache) > 500:
            _cache.clear()
            
        _cache[cache_key] = fields
        return JSONResponse({"ok": True, "fields": fields, "cached": False})

    except json.JSONDecodeError:
        return JSONResponse({"ok": True, "fields": [], "error": "Parse failed"})
    except Exception as e:
        raise HTTPException(500, f"Groq error: {str(e)}")