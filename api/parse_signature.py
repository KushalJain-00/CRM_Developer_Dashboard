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

Your task is to identify and extract structured data for EVERY distinct individual found in the email, particularly focusing on email signature blocks which contain the richest information.

Return ONLY a valid JSON array of objects. Do not include markdown code blocks like ```json ... ```. Output raw JSON ONLY. Use null if a field is not found.

Rules for accuracy:
1. **Signatures**: Pay extremely close attention to the bottom of emails. Signatures usually contain the Name, Designation/Job Title, Company, Phone Numbers, and Address clustered together.
2. **Designation**: Job titles are almost always found immediately below or next to the person's name in their signature. Actively look for words indicating roles (e.g., Manager, Director, Engineer, Executive, President, Head, Associate, Founder, etc.) and assign it to the "designation" field.
3. **Company**: The company name is usually found in the signature block, often near the website or address. 
4. **Association**: Strictly associate phone numbers, job titles, and companies with the person they belong to. 
5. **Multiple Contacts**: If you see multiple signatures or people (e.g., in a forwarded thread), return one object per person.
6. **Robustness**: Even if you only find one contact, still return it inside a JSON array.
7. **JSON Schema (USE EXACTLY THESE KEYS)**:
[
  {
    "name": "<extracted full name>",
    "company": "<extracted company name>",
    "designation": "<extracted job title>",
    "phone_primary": "<extracted main phone>",
    "phone_secondary": "<extracted alt phone>",
    "email": "<extracted email address - CRITICAL FOR MATCHING>",
    "website": "<extracted url>",
    "address": "<extracted full address>",
    "city": "<extracted city>",
    "pincode": "<extracted zip/postal code>"
  }
]
"""

from typing import List, Optional

class ModelConfig(BaseModel):
    provider: str
    model: str
    api_key: str

class SignatureRequest(BaseModel):
    body_text: str
    subject: str = ""
    chain: List[ModelConfig] = []

PROVIDERS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/beta/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models/"
}

def clean_email_text(text: str) -> str:
    """Basic cleaning to save tokens (removes long continuous non-space strings like base64)."""
    text = re.sub(r'([A-Za-z0-9+/=]{100,})', '', text)
    return text[:100000] # Limit to 100k chars

async def call_llm(provider, model, api_key, system_prompt, user_prompt):
    url = PROVIDERS.get(provider)
    if not url:
        raise Exception(f"Unknown provider: {provider}")

    headers = {
        "Content-Type": "application/json"
    }

    if provider == "anthropic":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        payload = {
            "model": model,
            "max_tokens": 4096,
            "temperature": 0.1,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ]
        }
    elif provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [{
                "parts": [{"text": user_prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096
            }
        }
    else:
        # OpenAI compatible endpoints (OpenRouter, Groq, OpenAI, DeepSeek)
        headers["Authorization"] = f"Bearer {api_key}"
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://crm.engine"
            headers["X-Title"] = "CRM Engine"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }
        if provider in ["openai", "groq", "deepseek"]:
            payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
            raise Exception(f"{provider} API Error ({response.status_code}): {response.text}")
            
        data = response.json()
        if provider == "anthropic":
            return data["content"][0]["text"].strip()
        elif provider == "gemini":
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except (KeyError, IndexError):
                raise Exception(f"Gemini API returned unexpected structure: {data}")
        else:
            return data["choices"][0]["message"]["content"].strip()

@router.post("/parse-signature")
@limiter.limit("200/minute")
async def parse_signature(request: Request, body: SignatureRequest):
    email_text = clean_email_text(body.body_text)

    if not email_text or len(email_text) < 10:
        return JSONResponse({"ok": True, "fields": [], "cached": False})

    # Cache check
    cache_string = f"{body.chain[0].model if body.chain else 'nomodel'}_{email_text}"
    cache_key = hashlib.md5(cache_string.encode()).hexdigest()
    cached_val = _cache.get(cache_key)
    if cached_val is not None:
        return JSONResponse({"ok": True, "fields": cached_val, "cached": True})

    chain = body.chain
    if not chain:
        return JSONResponse({"ok": False, "error": "No AI configuration provided in the chain."})

    user_prompt = f"Extract contact info from this email (Subject: {body.subject}):\n\n{email_text}"

    raw = None
    last_err = None
    for attempt in chain:
        prov = attempt.provider
        mod = attempt.model
        key = attempt.api_key
        
        if not key:
            continue
            
        success = False
        for i in range(3): # 3 Retries per provider
            try:
                raw = await call_llm(prov, mod, key, SYSTEM_PROMPT, user_prompt)
                success = True
                break
            except Exception as e:
                last_err = str(e)
                await asyncio.sleep(2 ** i) # 1, 2, 4
        
        if success:
            break

    if raw is None:
        raise HTTPException(500, f"All models/retries failed. Last error: {last_err}")

    # Robust JSON extraction
    fields = None
    try:
        fields = json.loads(raw)
    except json.JSONDecodeError:
        json_match = re.search(r'(\[.*\]|\{.*\})', raw, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                fields = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                pass
                
    if fields is None:
        return JSONResponse({"ok": True, "fields": [], "error": "Parse failed"})
    
    _cache.put(cache_key, fields)
    return JSONResponse({"ok": True, "fields": fields, "cached": False})