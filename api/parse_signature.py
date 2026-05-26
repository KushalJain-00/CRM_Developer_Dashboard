"""
Signature Intelligence — extracts structured contact fields from email body.
"""
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from core.rate_limit import limiter
from core.auth import verify_token
import os, hashlib, json, httpx, re, asyncio
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

SYSTEM_PROMPT = """You are an expert contact information extractor specialized in parsing emails. 

Your task is to identify and extract structured data for EVERY distinct individual found in the email, including senders, recipients, and signatures.

Return ONLY a valid JSON array of objects. Use null if a field is not found.

Rules for accuracy:
1. **Association**: Strictly associate phone numbers, job titles, and companies with the person they belong to. 
2. **Multiple Contacts**: If you see multiple signatures or people, return one object per person.
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

def clean_email_text(text: str) -> str:
    """Basic cleaning to save tokens (removes long continuous non-space strings like base64)."""
    text = re.sub(r'([A-Za-z0-9+/=]{100,})', '', text)
    return text[:20000] # Limit to 20k chars

async def call_llm(provider, model, api_key, payload):
    url = PROVIDERS.get(provider, PROVIDERS["openrouter"])
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://crm.engine"
        headers["X-Title"] = "CRM Engine"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            raise Exception(f"AI API Error ({response.status_code}): {response.text}")
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

@router.post("/parse-signature")
@limiter.limit("200/minute")
async def parse_signature(request: Request, body: SignatureRequest):
    email_text = clean_email_text(body.body_text)

    if not email_text or len(email_text) < 10:
        return JSONResponse({"ok": True, "fields": [], "cached": False})

    # Cache check
    cache_string = f"{body.model}_{email_text}"
    cache_key = hashlib.md5(cache_string.encode()).hexdigest()
    cached_val = _cache.get(cache_key)
    if cached_val is not None:
        return JSONResponse({"ok": True, "fields": cached_val, "cached": True})

    payload = {
        "model": body.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract contact info from this email (Subject: {body.subject}):\n\n{email_text}"}
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
    }

    # Fallback chain: Initial provider -> Groq -> OpenRouter -> OpenAI
    chain = [
        {"provider": body.provider, "model": body.model, "api_key": body.api_key.strip() or os.getenv(f"{body.provider.upper()}_API_KEY", "")},
        {"provider": "groq", "model": "llama-3.3-70b-versatile", "api_key": os.getenv("GROQ_API_KEY", "")},
        {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct", "api_key": os.getenv("OPENROUTER_API_KEY", "")},
        {"provider": "openai", "model": "gpt-4o-mini", "api_key": os.getenv("OPENAI_API_KEY", "")}
    ]

    raw = None
    last_err = None
    for attempt in chain:
        prov = attempt["provider"]
        mod = attempt["model"]
        key = attempt["api_key"]
        
        if not key:
            continue
            
        payload["model"] = mod
        
        # Enforce JSON mode for supported providers
        if prov in ["openai", "groq"]:
            payload["response_format"] = {"type": "json_object"}
        elif "response_format" in payload:
            del payload["response_format"]
        
        # 5 Retries with exponential backoff for each provider in chain
        success = False
        for i in range(5):
            try:
                raw = await call_llm(prov, mod, key, payload)
                success = True
                break
            except Exception as e:
                last_err = str(e)
                await asyncio.sleep(2 ** i) # 1, 2, 4, 8, 16
        
        if success:
            break

    if raw is None:
        raise HTTPException(500, f"All models/retries failed. Last error: {last_err}")

    # Robust JSON extraction
    fields = None
    try:
        fields = json.loads(raw)
    except json.JSONDecodeError:
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