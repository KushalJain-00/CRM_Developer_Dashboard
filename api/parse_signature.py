"""
Signature Intelligence — uses email-reply-parser to isolate the signature
block, then a chosen LLM to extract structured contact fields from it.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os, hashlib, json, httpx, re
from collections import OrderedDict

router = APIRouter()

class LRUCache:
    def __init__(self, capacity: int):
        self.cache = OrderedDict()
        self.capacity = capacity

    def get(self, key):
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

_cache = LRUCache(500)

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
    body_text: str
    subject: str = ""
    provider: str = "openrouter"
    model: str = "meta-llama/llama-3.3-70b-instruct"
    api_key: str = ""

PROVIDERS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions"
}

def extract_signature_block(body_text: str) -> str:
    """
    Isolate signature from email body.
    Strategy: look for common signature delimiters, take everything after.
    Falls back to last 200 lines if no delimiter found to ensure we don't miss long thread signatures.
    """
    lines = body_text.replace('\r\n', '\n').split('\n')

    # Common signature delimiters
    delimiters = ['--', '___', '---', 'best regards', 'thanks & regards', 'thanks and regards',
                  'regards,', 'warm regards', 'sincerely,', 'thanks,', 'thank you,', 'cheers,', 'with regards']

    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if any(stripped.startswith(d) for d in delimiters):
            sig_lines = lines[i:]
            return '\n'.join(sig_lines[:200]).strip()

    # If no delimiter, take the last 200 lines to catch multi-person signatures in long threads
    return '\n'.join(lines[-200:]).strip()

@router.post("/parse-signature")
async def parse_signature(body: SignatureRequest):
    # Use user provided API key or fallback to environment variables
    api_key = body.api_key.strip()
    if not api_key:
        if body.provider == "groq":
            api_key = os.getenv("GROQ_API_KEY", "")
        elif body.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "")
        elif body.provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY", "")
            
    if not api_key:
        raise HTTPException(400, f"API Key for {body.provider} not provided and no fallback found.")

    sig_block = extract_signature_block(body.body_text)

    if not sig_block or len(sig_block) < 10:
        return JSONResponse({"ok": True, "fields": [], "cached": False})

    # Cache check (incorporating model so weak models don't poison the cache)
    cache_string = f"{body.model}_{sig_block}"
    cache_key = hashlib.md5(cache_string.encode()).hexdigest()
    cached_val = _cache.get(cache_key)
    if cached_val is not None:
        return JSONResponse({"ok": True, "fields": cached_val, "cached": True})

    url = PROVIDERS.get(body.provider, PROVIDERS["openrouter"])

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    if body.provider == "openrouter":
        headers["HTTP-Referer"] = "https://crm.engine"
        headers["X-Title"] = "CRM Engine"

    payload = {
        "model": body.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract contact info from this email signature:\n\n{sig_block}"}
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code != 200:
                print(f"AI API Error: {response.text}")
                raise HTTPException(500, f"AI API Error ({response.status_code})")
                
            data = response.json()
            raw = data["choices"][0]["message"]["content"].strip()

        # Robust JSON extraction
        fields = None
        try:
            fields = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback regex to find JSON arrays
            json_match = re.search(r'\[.*\]', raw, re.DOTALL)
            if json_match:
                try:
                    fields = json.loads(json_match.group(0))
                except Exception:
                    pass
                    
        if fields is None:
            return JSONResponse({"ok": True, "fields": [], "error": "Parse failed"})
        
        _cache.put(cache_key, fields)
        return JSONResponse({"ok": True, "fields": fields, "cached": False})

    except Exception as e:
        raise HTTPException(500, f"AI Error: {str(e)}")