# services/llm_router.py
"""Multi-provider LLM chain: ordered failover, retries, JSON-only extraction."""
import hashlib, json, re, asyncio, logging
from collections import OrderedDict
from typing import Optional
from pydantic import BaseModel
import httpx

logger = logging.getLogger(__name__)

RETRY_BACKOFF = [1, 2, 4]  # tests monkeypatch to [0,0,0]

class ChainEntry(BaseModel):
    provider: str
    model: str
    api_key: str

EXTRACTION_SYSTEM_PROMPT = """You extract one contact from an email signature/header.
Return ONLY a raw JSON object (no markdown) with EXACTLY these keys; use null if unknown:
{"name":null,"email":null,"phone_primary":null,"phone_secondary":null,"company":null,"designation":null,"address":null,"city":null,"pincode":null,"website":null}
Rules: designation may be null. Prefer signature block over email body. Never invent values."""

PROVIDERS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/beta/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "gemini": None,  # URL built per-call with model+key
}

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
_client: Optional[httpx.AsyncClient] = None

def _http() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client

def parse_llm_json(raw: str) -> dict | None:
    if not raw:
        return None
    text = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if isinstance(data, list):
        data = data[0] if data else None
    return data if isinstance(data, dict) else None

async def _call_provider(provider: str, model: str, api_key: str, system: str, user: str) -> str:
    if provider not in PROVIDERS and provider != "gemini":
        raise Exception(f"Unknown provider: {provider}")
    headers = {"Content-Type": "application/json"}
    if provider == "anthropic":
        url = PROVIDERS["anthropic"]
        headers.update({"x-api-key": api_key, "anthropic-version": "2023-06-01"})
        payload = {"model": model, "max_tokens": 2048, "temperature": 0.1,
                   "system": system, "messages": [{"role": "user", "content": user}]}
    elif provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {"system_instruction": {"parts": [{"text": system}]},
                   "contents": [{"parts": [{"text": user}]}],
                   "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}}
    else:
        url = PROVIDERS[provider]
        headers["Authorization"] = f"Bearer {api_key}"
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://crm.engine"
            headers["X-Title"] = "CRM Engine"
        payload = {"model": model, "temperature": 0.1, "max_tokens": 2048,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        if provider in ("openai", "groq", "deepseek"):
            payload["response_format"] = {"type": "json_object"}
    resp = await _http().post(url, headers=headers, json=payload)
    if resp.status_code != 200:
        raise Exception(f"{provider} HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if provider == "anthropic":
        return data["content"][0]["text"].strip()
    if provider == "gemini":
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    return data["choices"][0]["message"]["content"].strip()

async def extract_json(chain: list[ChainEntry], user_prompt: str) -> dict | None:
    if not chain:
        return None
    first = chain[0]
    cache_key = hashlib.md5(f"{first.provider}|{first.model}|{user_prompt}".encode()).hexdigest()
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    last_err = None
    for entry in chain:
        if not entry.api_key:
            continue
        for i in range(3):
            try:
                raw = await _call_provider(entry.provider, entry.model, entry.api_key,
                                           EXTRACTION_SYSTEM_PROMPT, user_prompt)
                parsed = parse_llm_json(raw)
                if parsed is not None:
                    _cache.put(cache_key, parsed)
                    return parsed
                last_err = "invalid JSON"
            except Exception as e:
                last_err = str(e)
                logger.debug("llm fail %s attempt %s: %s", entry.provider, i, e)
            if i < len(RETRY_BACKOFF):
                await asyncio.sleep(RETRY_BACKOFF[i])
    logger.warning("llm_router exhausted chain: %s", last_err)
    return None
