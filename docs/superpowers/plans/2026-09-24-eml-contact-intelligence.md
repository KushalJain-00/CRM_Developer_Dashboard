# EML Contact Intelligence — Fresh Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the entire old EML feature (and n8n) with a pure-backend Python pipeline: upload .eml → MIME parse → multi-provider LLM fallback extraction → dedup → EML Supabase → browse/export/push-to-CRM.

**Architecture:** Approach A — new `services/llm_router.py`, `services/eml_processor.py`, `services/eml_store.py`, `api/eml.py` inside the existing FastAPI app. Frontend gets a new `frontend/eml.js` + 4 new views; ALL old EML code (backend, frontend, tests, n8n files) is deleted first. Same Render service.

**Tech Stack:** FastAPI, Python stdlib `email` (MIME), httpx (LLM calls), supabase-py (EML DB), slowapi, vanilla JS + XLSX.js (client Excel), pytest.

**Spec:** `docs/superpowers/specs/2026-09-24-eml-contact-intelligence-design.md`

## Global Constraints

- No salvaging old EML code — delete first, write fresh
- No n8n; no Google Sheets output
- No new Python dependencies (stdlib `email`, existing httpx/supabase/slowapi)
- Excel export: client-side XLSX.js only; CSV export: server-side stdlib csv
- LLM keys: client localStorage `EML_LLM_CHAIN`, sent per request as `chain` — never stored server-side, never logged
- Provider keys in chain JSON: `gemini`, `openrouter`, `groq`, `openai`, `deepseek`, `anthropic` (gemini = Google)
- Chain item shape: `{provider, model, api_key}` (snake_case, matches existing `ModelConfig`)
- Dedup: email match OR phone ≥10 digits match → DUPLICATE (n8n rules)
- Contact valid if ≥1 of email / phone_primary; missing optional fields stay null (designation absence OK)
- Non-EML CRM features must keep working after every task
- `pytest tests/ -v` green at end of every backend task
- EML Supabase: `EML_SUPABASE_URL` / `EML_SUPABASE_ANON_KEY` env vars (backend); tables `eml_emails`, `eml_contacts`
- Rate limit process endpoint: `30/minute` via existing slowapi limiter
- Auth level: same as rest of app — no `verify_token` on EML read/process routes; push-to-CRM uses `verify_token` (writes to main CRM, matches `POST /api/contacts/batch`)

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `services/llm_router.py` | Provider chain failover, retries, JSON extraction, LRU cache |
| Create | `services/eml_processor.py` | MIME parse, signature detect, local regex fallback, field merge |
| Create | `services/eml_store.py` | Supabase EML client: insert/list/dedup-key fetch/push flag |
| Create | `services/eml_dedup_rules.py` | Pure normalize + match functions (kept tiny for tests) |
| Create | `api/eml.py` | All `/api/eml/*` routes |
| Create | `db/eml_supabase_schema.sql` | One-time Supabase table DDL |
| Create | `frontend/eml.js` | All new EML UI logic |
| Create | `tests/test_llm_router.py` | Failover/retry/cache tests |
| Create | `tests/test_eml_processor.py` | MIME/signature/field tests |
| Create | `tests/test_eml_dedup_rules.py` | Dedup pure-function tests |
| Create | `tests/test_eml_api.py` | Route tests with mocked store |
| Modify | `main.py` | Register `api.eml` router only |
| Modify | `frontend/index.html` | Remove old EML views/nav; add 4 new views + nav; load `eml.js` |
| Modify | `frontend/app.js` | Remove ALL old EML code + call sites; patch `showView` titles |
| Modify | `frontend/style.css` | Minimal styles for new EML views |
| Modify | `render.yaml` | Add `EML_SUPABASE_URL`, `EML_SUPABASE_ANON_KEY` env keys |
| Modify | `tests/conftest.py` | Drop `eml_models` import |
| Delete | `api/eml_pipeline.py`, `api/eml_monitor.py`, `api/eml_export.py`, `api/eml_sse.py` | Old pipeline |
| Delete | `services/eml_batch.py`, `eml_dedup.py`, `eml_export.py`, `eml_parser.py`, `eml_retry.py`, `eml_signature.py` | Old services |
| Delete | `db/eml_models.py` | Old job models |
| Delete | `tests/test_eml_batch.py`, `test_eml_dedup.py`, `test_eml_export.py`, `test_eml_models.py`, `test_eml_monitor.py`, `test_eml_parser.py`, `test_eml_pipeline.py`, `test_eml_retry.py`, `test_eml_signature.py` | Old tests |
| Delete | `n8n-eml-setup.md`, `n8n-eml-workflow.json` | n8n |

---

### Task 1: Destroy old EML completely (app must still boot)

**Files:**
- Delete: all Delete-list files above
- Modify: `main.py:20-23,112-115` (remove 4 imports + 4 include_router lines)
- Modify: `db/database.py:55` (remove `from db import eml_models`)
- Modify: `tests/conftest.py:10` (remove `from db import eml_models`)
- Modify: `frontend/index.html` (nav item line ~68, `view-eml` block ~287-339, `view-eml-pipeline` block ~341-408)
- Modify: `frontend/app.js` (see step 2 for exact ranges/calls)
- Modify: `frontend/config.js` (remove `EML_SUPABASE_*` lines 11-12)

**Interfaces:**
- Produces: clean app with zero references to old EML; non-EML features unchanged

- [ ] **Step 1: Delete backend + n8n files**

```bash
rm -f api/eml_pipeline.py api/eml_monitor.py api/eml_export.py api/eml_sse.py \
  services/eml_batch.py services/eml_dedup.py services/eml_export.py \
  services/eml_parser.py services/eml_retry.py services/eml_signature.py \
  db/eml_models.py \
  tests/test_eml_batch.py tests/test_eml_dedup.py tests/test_eml_export.py \
  tests/test_eml_models.py tests/test_eml_monitor.py tests/test_eml_parser.py \
  tests/test_eml_pipeline.py tests/test_eml_retry.py tests/test_eml_signature.py \
  n8n-eml-setup.md n8n-eml-workflow.json
find . -path ./venv -prune -o -name '__pycache__' -type d -print0 | xargs -0 rm -rf
```

- [ ] **Step 2: Strip main.py, database.py, conftest.py**

`main.py` — remove these lines entirely:
```python
from api.eml_pipeline import router as eml_router
from api.eml_monitor import router as eml_monitor_router
from api.eml_export import router as eml_export_router
from api.eml_sse import router as sse_router
```
and:
```python
app.include_router(eml_router, prefix="/api")
app.include_router(eml_monitor_router, prefix="/api")
app.include_router(eml_export_router, prefix="/api")
app.include_router(sse_router, prefix="/api")
```

`db/database.py` — remove `from db import eml_models  # noqa` (line ~55).

`tests/conftest.py` — remove `from db import eml_models  # noqa` (line 10).

- [ ] **Step 3: Verify backend boots and tests pass**

Run:
```bash
python -c "import main" && pytest tests/ -v --ignore=tests/test_eml_api.py 2>&1 | tail -20
```
Expected: import OK; `test_api.py` + `test_parser.py` PASS (old eml tests gone).

- [ ] **Step 4: Strip old EML from `index.html`**

1. Delete nav item (`data-view="eml-pipeline"` block, ~lines 68-70).
2. Delete entire `<div class="view" id="view-eml">…</div>` (from `<!-- EML EMAIL EXTRACTOR DASHBOARD -->` through its closing `</div>` before the pipeline comment).
3. Delete entire `<div class="view" id="view-eml-pipeline">…</div>` (through closing `</div>` before `view-history`).
4. In `view-upload` drop-zone chips, remove `<span class="ft-chip eml-chip">📧 .eml</span>`.
5. Change `fileInput` accept from `.xlsx,.xls,.csv,.txt,.pdf,.eml` → `.xlsx,.xls,.csv,.txt,.pdf`.
6. Before `</body>`, after `<script src="app.js"></script>`, do NOT add eml.js yet (Task 6).

- [ ] **Step 5: Strip old EML from `app.js`**

Delete/replace these call sites FIRST (small edits), then the big block:

1. `handleFile` (~489-491): remove the `if (ext === 'eml') { handleEmlFile(file); return; }` branch.
2. `handleMultipleFiles` (~573-579): remove eml intercept lines; change remaining filter regex to `/\.(xlsx|xls|csv|txt|pdf)$/i` and error string to drop `.eml` mention.
3. `showView` (~1588-1593): remove `'eml-pipeline':'EML Pipeline'` from titles; change guard line to `if (!['upload','mapping','processing'].includes(id))`.
4. `saveToCRM` (~1616-1618): remove `if (document.body.classList.contains('eml-mode')) { return emlSaveToSupabase(); }` block.
5. History reload EML special-case (~1737 area and ~1764-1780): remove branches that set `EML.parsed` / `'EML Contacts'` / `'Bulk EML'` / `'EML Bulk Import'`.
6. Delete everything from the banner comment `/* ══════════════════════════════════════════════════════════════════════\n   EML EMAIL EXTRACTOR — v2.0 Enhanced` through **end of file** (all remaining code after that banner is old EML/bulk/pipeline — verified: file ends inside `emlPipelineShowMonitor`).

- [ ] **Step 6: Verify no dangling EML references**

Run:
```bash
grep -nE "handleEmlFile|parseEml|emlSaveToSupabase|handleBulkEml|BULK\.|emlPipeline|emlClient|EML\.|view-eml" frontend/app.js frontend/index.html main.py || echo CLEAN
```
Expected: `CLEAN`

- [ ] **Step 7: Confirm non-EML app still works**

Run:
```bash
python -c "from main import app; print('routes', len(app.routes))"
pytest tests/ -v 2>&1 | tail -10
```
Expected: app imports; all remaining tests PASS.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(eml): destroy old EML feature and n8n files — clean slate"
```

---

### Task 2: Dedup rules (pure functions)

**Files:**
- Create: `services/eml_dedup_rules.py`
- Test: `tests/test_eml_dedup_rules.py`

**Interfaces:**
- Produces:
  - `normalize_email(email: str | None) -> str`
  - `normalize_phone(phone: str | None) -> str` (digits only)
  - `is_duplicate(email, phone, existing_emails: set[str], existing_phones: set[str]) -> str | None` returns `"email"` | `"phone"` | `None`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_eml_dedup_rules.py
from services.eml_dedup_rules import normalize_email, normalize_phone, is_duplicate

def test_normalize_email():
    assert normalize_email("  Foo@Bar.COM ") == "foo@bar.com"
    assert normalize_email(None) == ""

def test_normalize_phone_keeps_digits():
    assert normalize_phone("+91 (98765) 43210") == "919876543210"
    assert normalize_phone(None) == ""

def test_dup_by_email():
    assert is_duplicate("a@b.com", None, {"a@b.com"}, set()) == "email"

def test_dup_by_phone_10_digits():
    # normalized phone compared as suffix/containment when >= 10 digits
    assert is_duplicate("x@y.com", "+91-98765-43210", set(), {"919876543210"}) == "phone"

def test_no_dup():
    assert is_duplicate("new@x.com", "9876543210", {"a@b.com"}, {"1111111111"}) is None

def test_short_phone_not_matched():
    assert is_duplicate("new@x.com", "12345", set(), {"12345"}) is None
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_eml_dedup_rules.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement**

```python
# services/eml_dedup_rules.py
"""Pure dedup helpers — ported from n8n workflow rules."""
import re

def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()

def normalize_phone(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")

def is_duplicate(email, phone, existing_emails: set[str], existing_phones: set[str]) -> str | None:
    e = normalize_email(email)
    if e and e in existing_emails:
        return "email"
    p = normalize_phone(phone)
    if len(p) >= 10:
        # match if any existing phone contains or equals (handles +91 prefix variance)
        for ep in existing_phones:
            if ep == p or (len(ep) >= 10 and (ep in p or p in ep)):
                return "phone"
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_eml_dedup_rules.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add services/eml_dedup_rules.py tests/test_eml_dedup_rules.py
git commit -m "feat(eml): dedup rules — email/phone match, n8n port"
```

---

### Task 3: LLM router with multi-provider fallback chain

**Files:**
- Create: `services/llm_router.py`
- Test: `tests/test_llm_router.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `class ChainEntry(BaseModel): provider: str; model: str; api_key: str`
  - `EXTRACTION_SYSTEM_PROMPT: str` — strict single-object JSON schema (all 10 contact fields)
  - `async def extract_json(chain: list[ChainEntry], user_prompt: str) -> dict | None`
    - Walks chain in order; 3 retries/provider; backoff `1, 2, 4`s (scaled to `0` in tests via `RETRY_BACKOFF` module list)
    - On HTTP error / 429 / bad JSON → next provider
    - LRU cache (500) keyed `md5(provider|model|user_prompt)` → returns cached dict
    - Returns parsed `dict` or `None` if all fail
  - `def parse_llm_json(raw: str) -> dict | None` — strips fences, finds first `{...}`, coerces list→first dict

- [ ] **Step 1: Write failing tests**

```python
# tests/test_llm_router.py
import pytest
from services import llm_router
from services.llm_router import ChainEntry, extract_json, parse_llm_json

def test_parse_llm_json_plain():
    assert parse_llm_json('{"name": "A"}') == {"name": "A"}

def test_parse_llm_json_fenced():
    assert parse_llm_json('```json\n{"name":"A"}\n```') == {"name": "A"}

def test_parse_llm_json_list_first():
    assert parse_llm_json('[{"name":"A"},{"name":"B"}]') == {"name": "A"}

def test_parse_llm_json_garbage():
    assert parse_llm_json("not json at all") is None

@pytest.mark.asyncio
async def test_failover_to_second_provider(monkeypatch):
    calls = []
    async def fake_call(provider, model, key, system, user):
        calls.append(provider)
        if provider == "gemini":
            raise Exception("500 boom")
        return '{"name": "OK"}'
    monkeypatch.setattr(llm_router, "_call_provider", fake_call)
    monkeypatch.setattr(llm_router, "RETRY_BACKOFF", [0, 0, 0])
    llm_router._cache.cache.clear()
    chain = [
        ChainEntry(provider="gemini", model="m", api_key="k"),
        ChainEntry(provider="groq", model="m", api_key="k"),
    ]
    out = await extract_json(chain, "prompt")
    assert out == {"name": "OK"}
    assert calls[0] == "gemini"
    assert "groq" in calls

@pytest.mark.asyncio
async def test_empty_chain_returns_none():
    assert await extract_json([], "p") is None

@pytest.mark.asyncio
async def test_cache_hit(monkeypatch):
    calls = []
    async def fake_call(provider, model, key, system, user):
        calls.append(provider)
        return '{"name": "CACHED"}'
    monkeypatch.setattr(llm_router, "_call_provider", fake_call)
    monkeypatch.setattr(llm_router, "RETRY_BACKOFF", [0, 0, 0])
    llm_router._cache.cache.clear()
    chain = [ChainEntry(provider="groq", model="m", api_key="k")]
    a = await extract_json(chain, "same-prompt")
    b = await extract_json(chain, "same-prompt")
    assert a == b == {"name": "CACHED"}
    assert len(calls) == 1  # second served from cache
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_llm_router.py -v`
Expected: FAIL (import error)

- [ ] **Step 3: Implement `services/llm_router.py`**

```python
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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_llm_router.py -v`
Expected: all PASS

- [ ] **Step 5: Full suite + commit**

```bash
pytest tests/ -v 2>&1 | tail -15
git add services/llm_router.py tests/test_llm_router.py
git commit -m "feat(eml): multi-provider LLM router with failover chain"
```

---

### Task 4: EML processor — MIME parse, signature, local extraction

**Files:**
- Create: `services/eml_processor.py`
- Test: `tests/test_eml_processor.py`

**Interfaces:**
- Consumes: `services.eml_dedup_rules` (not inside processor — dedup applied in API/store layer)
- Produces:
  - `@dataclass ParsedEml`: `file_name, subject, date, sender_name, sender_email, receiver_name, receiver_email, body_text, has_signature, signature_block`
  - `def parse_eml_bytes(raw: bytes, file_name: str) -> ParsedEml`
  - `def extract_local_fields(parsed: ParsedEml) -> dict` — 10-key dict, regex fallback
  - `def build_llm_prompt(parsed: ParsedEml) -> str` — headers + signature_block (or body[:2500])
  - `def merge_fields(local: dict, ai: dict | None) -> dict` — AI fills gaps; local wins if AI null; coerce all 10 keys

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_eml_processor.py -v`
Expected: FAIL (import error)

- [ ] **Step 3: Implement `services/eml_processor.py`**

```python
# services/eml_processor.py
"""Parse .eml bytes → headers/body/signature; local field extraction; LLM merge."""
import re, email, html as html_mod
from email import policy
from dataclasses import dataclass, field

FIELD_KEYS = ["name", "email", "phone_primary", "phone_secondary", "company",
              "designation", "address", "city", "pincode", "website"]

SIG_DELIM = re.compile(
    r"^(?:--\s*$|regards|best regards|thanks|warm regards|sincerely|cheers|"
    r"thanks\s*&\s*regards|thanks\s+and\s+regards|sent from my|with regards)",
    re.I,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(?:\+91[\s\-]?)?[6-9]\d{9}|\+\d{1,3}[\s\-]?\d{5,14}")
WEBSITE_RE = re.compile(r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)")
PINCODE_RE = re.compile(r"\b\d{6}\b")
COMPANY_RE = re.compile(
    r"([A-Z][A-Za-z0-9&.\- ]+(?:\s+[A-Z][A-Za-z0-9&.\- ]+){0,6}\s+"
    r"(?:Pvt\.?\s+Ltd\.?|Limited|Ltd\.?|Inc\.?|LLP|Corporation|Co\.))",
    re.I,
)
CITY_HINTS = re.compile(
    r"\b(Mumbai|Delhi|Bangalore|Bengaluru|Chennai|Kolkata|Pune|Hyderabad|Ahmedabad|"
    r"Jaipur|Surat|Lucknow|Indore|Nagpur|Thane|Navi Mumbai)\b", re.I,
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

def _html_to_text(raw: str) -> text if False else str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html_mod.unescape(text)

def _addr(msg, header: str) -> tuple[str, str]:
    raw = msg.get(header, "") or ""
    pairs = email.utils.getaddresses([raw])
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
    if cc_email:
        receiver_email = (receiver_email + ", " + cc_email).strip(", ")
        if cc_name:
            receiver_name = (receiver_name + ", " + cc_name).strip(", ")

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
            fields["phone_secondary"] = phones[1].strip()
    cm = COMPANY_RE.search(zone)
    if cm:
        fields["company"] = cm.group(0).strip()
    wm = WEBSITE_RE.search(zone)
    if wm:
        fields["website"] = wm.group(0).strip()
    pm = PINCODE_RE.search(zone)
    if pm:
        fields["pincode"] = pm.group(0)
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
            if len(s.split()) >= 2 and len(s) <= 60:
                fields["name"] = s
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
    elif parsed.sender_name:
        fields["name"] = parsed.sender_name
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
```

NOTE: fix the accidental `def _html_to_text(raw: str) -> text if False else str:` — signature must be `def _html_to_text(raw: str) -> str:`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_eml_processor.py -v`
Expected: all PASS (adjust regex edge cases only if a test legitimately fails on extraction detail — do not weaken assertions on headers/decode/merge)

- [ ] **Step 5: Full suite + commit**

```bash
pytest tests/ -v 2>&1 | tail -15
git add services/eml_processor.py tests/test_eml_processor.py
git commit -m "feat(eml): MIME parser, signature detection, local extraction, merge"
```

---

### Task 5: EML Supabase store + schema SQL

**Files:**
- Create: `services/eml_store.py`
- Create: `db/eml_supabase_schema.sql`
- Modify: `render.yaml` (add two env keys)
- Test: `tests/test_eml_api.py` will mock this; add light unit tests here for row mapping only

**Interfaces:**
- Consumes: env `EML_SUPABASE_URL`, `EML_SUPABASE_ANON_KEY`
- Produces:
  - `def get_eml_client()` — supabase Client (raises RuntimeError if unconfigured)
  - `async def fetch_dedup_keys() -> tuple[set[str], set[str]]` — all emails + phones from `eml_contacts` (normalize at call site)
  - `async def insert_email(row: dict) -> str` — returns id
  - `async def insert_contact(row: dict) -> str` — returns id
  - `async def list_contacts(search, status, pushed, page, page_size) -> dict` → `{items, total}`
  - `async def list_emails(page, page_size) -> dict` → `{items, total}`
  - `async def get_email(email_id) -> dict | None` (+ linked contacts via `source_email_id`)
  - `async def mark_pushed(contact_id) -> None`
  - `async def get_contact(contact_id) -> dict | None`

- [ ] **Step 1: Write schema SQL**

```sql
-- db/eml_supabase_schema.sql  (run ONCE in EML Supabase SQL editor)
create table if not exists eml_emails (
  id uuid primary key default gen_random_uuid(),
  file_name text,
  subject text,
  date text,
  sender_name text,
  sender_email text,
  receiver_name text,
  receiver_email text,
  body_text text,
  has_signature boolean default false,
  created_at timestamptz default now()
);

create table if not exists eml_contacts (
  id uuid primary key default gen_random_uuid(),
  name text,
  email text,
  phone_primary text,
  phone_secondary text,
  company text,
  designation text,
  address text,
  city text,
  pincode text,
  website text,
  source_email_id uuid references eml_emails(id) on delete set null,
  source_file text,
  dedup_status text default 'NEW',
  pushed_to_crm boolean default false,
  created_at timestamptz default now()
);

create index if not exists idx_eml_contacts_email on eml_contacts (email);
create index if not exists idx_eml_contacts_phone on eml_contacts (phone_primary);
create index if not exists idx_eml_contacts_source on eml_contacts (source_email_id);
```

- [ ] **Step 2: Add render.yaml env keys**

After `GROQ_API_KEY` entry add:
```yaml
      - key: EML_SUPABASE_URL
        sync: false
      - key: EML_SUPABASE_ANON_KEY
        sync: false
```

- [ ] **Step 3: Implement `services/eml_store.py`**

```python
# services/eml_store.py
"""Thin async wrappers over the EML Supabase project (eml_emails / eml_contacts)."""
import os, logging
from supabase import create_client, Client

logger = logging.getLogger(__name__)
_client: Client | None = None

def get_eml_client() -> Client:
    global _client
    if _client is not None:
        return _client
    url = os.getenv("EML_SUPABASE_URL", "")
    key = os.getenv("EML_SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise RuntimeError("EML Supabase not configured (EML_SUPABASE_URL / EML_SUPABASE_ANON_KEY)")
    _client = create_client(url, key)
    return _client

async def fetch_dedup_keys() -> tuple[set[str], set[str]]:
    sb = get_eml_client()
    rows = sb.table("eml_contacts").select("email, phone_primary").execute().data or []
    emails = {(r.get("email") or "").lower() for r in rows if r.get("email")}
    phones = {r.get("phone_primary") or "" for r in rows if r.get("phone_primary")}
    emails.discard("")
    phones.discard("")
    return emails, phones

async def insert_email(row: dict) -> str:
    sb = get_eml_client()
    data = sb.table("eml_emails").insert(row).execute().data
    return data[0]["id"]

async def insert_contact(row: dict) -> str:
    sb = get_eml_client()
    data = sb.table("eml_contacts").insert(row).execute().data
    return data[0]["id"]

async def get_contact(contact_id: str) -> dict | None:
    sb = get_eml_client()
    data = sb.table("eml_contacts").select("*").eq("id", contact_id).limit(1).execute().data
    return data[0] if data else None

async def get_email(email_id: str) -> dict | None:
    sb = get_eml_client()
    data = sb.table("eml_emails").select("*").eq("id", email_id).limit(1).execute().data
    if not data:
        return None
    email_row = data[0]
    contacts = sb.table("eml_contacts").select("*").eq("source_email_id", email_id).execute().data or []
    email_row["contacts"] = contacts
    return email_row

async def list_contacts(search="", status="", pushed=None, page=1, page_size=50) -> dict:
    sb = get_eml_client()
    q = sb.table("eml_contacts").select("*", count="exact")
    if search:
        s = search.replace("'", "")
        q = q.or_(
            f"name.ilike.%{s}%,email.ilike.%{s}%,phone_primary.ilike.%{s}%,"
            f"phone_secondary.ilike.%{s}%,company.ilike.%{s}%"
        )
    if status in ("NEW", "DUPLICATE"):
        q = q.eq("dedup_status", status)
    if pushed is not None:
        q = q.eq("pushed_to_crm", pushed)
    q = q.order("created_at", desc=True).range((page - 1) * page_size, page * page_size - 1)
    res = q.execute()
    return {"items": res.data or [], "total": res.count or 0}

async def list_emails(page=1, page_size=50) -> dict:
    sb = get_eml_client()
    res = (
        sb.table("eml_emails")
        .select("*", count="exact")
        .order("created_at", desc=True)
        .range((page - 1) * page_size, page * page_size - 1)
        .execute()
    )
    return {"items": res.data or [], "total": res.count or 0}

async def mark_pushed(contact_id: str) -> None:
    sb = get_eml_client()
    sb.table("eml_contacts").update({"pushed_to_crm": True}).eq("id", contact_id).execute()
```

NOTE: supabase-py is sync — these are `async def` only to fit FastAPI easily; calls block briefly (acceptable, ponytail). Do not add a threadpool unless Render latency shows a problem.

- [ ] **Step 4: Smoke-test store module imports**

Run: `python -c "from services import eml_store; print('ok')"`
Expected: ok (no client created until configured)

- [ ] **Step 5: Commit**

```bash
git add services/eml_store.py db/eml_supabase_schema.sql render.yaml
git commit -m "feat(eml): Supabase store client + schema SQL + render env"
```

---

### Task 6: API routes `/api/eml/*`

**Files:**
- Create: `api/eml.py`
- Modify: `main.py` (import + include_router)
- Test: `tests/test_eml_api.py`

**Interfaces:**
- Consumes: `services.llm_router.extract_json`, `services.eml_processor.*`, `services.eml_dedup_rules.*`, `services.eml_store.*`, `api.contacts` helpers for push (`validate_email`, `classify_phone`, `_find_or_create_company`, `ContactIn`, `Contact`, `Company`)
- Produces:
  - `POST /api/eml/process` — multipart: `files: list[UploadFile]`, `chain: str` (JSON array of `{provider,model,api_key}`) → `{ok, results: [{file, status: NEW|DUPLICATE|ERROR, extraction: llm|fallback|none, contact, error?, email_id?}], counts:{new,duplicate,error}}`
  - `GET /api/eml/contacts` — `?search=&status=&pushed=&page=&page_size=` → store list
  - `GET /api/eml/emails` — paginated
  - `GET /api/eml/emails/{id}` — detail + contacts
  - `GET /api/eml/contacts/export?format=csv` — CSV attachment of current filters
  - `POST /api/eml/contacts/{id}/push` — auth `verify_token`; maps EML contact → main CRM Contact/Company; `mark_pushed`
  - `POST /api/eml/contacts/push-bulk` — body `{ids: [str]}`, auth; loops single-push logic

- [ ] **Step 1: Write failing API tests (mock store + llm)**

```python
# tests/test_eml_api.py
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_process_requires_files():
    r = client.post("/api/eml/process", data={"chain": "[]"}, files=[])
    assert r.status_code == 422  # no files field

@patch("api.eml.eml_store")
@patch("api.eml.extract_json", new_callable=AsyncMock)
def test_process_single_new_contact(mock_llm, mock_store):
    mock_llm.return_value = {
        "name": "John Doe", "email": "john@acme.com", "phone_primary": "9876543210",
        "phone_secondary": None, "company": "Acme Pvt Ltd", "designation": "Manager",
        "address": None, "city": "Mumbai", "pincode": "400001", "website": "acme.com",
    }
    mock_store.fetch_dedup_keys = AsyncMock(return_value=(set(), set()))
    mock_store.insert_email = AsyncMock(return_value="eml-1")
    mock_store.insert_contact = AsyncMock(return_value="ct-1")

    raw = (b"From: John Doe <john@acme.com>\r\nTo: sales@x.com\r\nSubject: Hi\r\n\r\n"
           b"-- \r\nJohn Doe\r\nManager\r\n+91 98765 43210\r\n")
    r = client.post(
        "/api/eml/process",
        data={"chain": '[{"provider":"groq","model":"m","api_key":"k"}]'},
        files=[("files", ("hi.eml", raw, "message/rfc822"))],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["counts"]["new"] == 1
    assert body["results"][0]["status"] == "NEW"
    assert body["results"][0]["extraction"] == "llm"
    assert body["results"][0]["contact"]["company"] == "Acme Pvt Ltd"

@patch("api.eml.eml_store")
@patch("api.eml.extract_json", new_callable=AsyncMock)
def test_process_duplicate_email(mock_llm, mock_store):
    mock_llm.return_value = {"name": "J", "email": "dup@x.com", "phone_primary": None,
                             "phone_secondary": None, "company": None, "designation": None,
                             "address": None, "city": None, "pincode": None, "website": None}
    mock_store.fetch_dedup_keys = AsyncMock(return_value=({"dup@x.com"}, set()))
    mock_store.insert_email = AsyncMock(return_value="eml-2")
    mock_store.insert_contact = AsyncMock(return_value="ct-2")
    raw = b"From: J <dup@x.com>\r\nTo: a@b.com\r\nSubject: s\r\n\r\nbody\r\n"
    r = client.post("/api/eml/process", data={"chain": "[]"},
                    files=[("files", ("d.eml", raw, "message/rfc822"))])
    assert r.json()["results"][0]["status"] == "DUPLICATE"

@patch("api.eml.eml_store")
@patch("api.eml.extract_json", new_callable=AsyncMock)
def test_process_empty_chain_uses_fallback(mock_llm, mock_store):
    mock_llm.return_value = None
    mock_store.fetch_dedup_keys = AsyncMock(return_value=(set(), set()))
    mock_store.insert_email = AsyncMock(return_value="eml-3")
    mock_store.insert_contact = AsyncMock(return_value="ct-3")
    raw = (b"From: Alice <alice@z.com>\r\nTo: b@c.com\r\nSubject: s\r\n\r\n-- \r\n"
           b"Alice Shah\r\n+919876543210\r\nalice@z.com\r\n")
    r = client.post("/api/eml/process", data={"chain": "[]"},
                    files=[("files", ("f.eml", raw, "message/rfc822"))])
    res = r.json()["results"][0]
    assert res["status"] == "NEW"
    assert res["extraction"] == "fallback"
    assert res["contact"]["email"] == "alice@z.com"

def test_contacts_list_shape():
    with patch("api.eml.eml_store") as ms:
        ms.list_contacts = AsyncMock(return_value={"items": [], "total": 0})
        r = client.get("/api/eml/contacts?page=1")
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0}

def test_emails_list_shape():
    with patch("api.eml.eml_store") as ms:
        ms.list_emails = AsyncMock(return_value={"items": [], "total": 0})
        r = client.get("/api/eml/emails")
        assert r.status_code == 200
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_eml_api.py -v`
Expected: FAIL (import api.eml)

- [ ] **Step 3: Implement `api/eml.py`**

```python
# api/eml.py
"""Fresh EML contact intelligence API — process, browse, export, push."""
import csv, io, json, logging
from fastapi import APIRouter, File, Form, UploadFile, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession as S  # noqa keep import style consistent

from core.rate_limit import limiter
from core.auth import verify_token
from db.database import get_db
from db.models import Contact, Company, SessionData, Record, User
from api.contacts import ContactIn, validate_email, classify_phone, _find_or_create_company
from services import eml_store
from services.llm_router import ChainEntry, extract_json
from services.eml_processor import parse_eml_bytes, extract_local_fields, build_llm_prompt, merge_fields, FIELD_KEYS
from services.eml_dedup_rules import is_duplicate, normalize_email, normalize_phone

logger = logging.getLogger(__name__)
router = APIRouter(tags=["eml"])

class PushBulkBody(BaseModel):
    ids: List[str]

def _empty_fields() -> dict:
    return {k: None for k in FIELD_KEYS}

def _pick_contact(fields: dict, parsed) -> dict:
    """One contact per email (sender/signature primary). email fallback to sender."""
    out = merge_fields(_empty_fields(), fields)
    if not out.get("email") and parsed.sender_email:
        out["email"] = parsed.sender_email.split(",")[0].strip().lower()
    if not out.get("name") and parsed.sender_name:
        out["name"] = parsed.sender_name
    return out

@router.post("/eml/process")
@limiter.limit("30/minute")
async def eml_process(
    request: Request,
    files: list[UploadFile] = File(...),
    chain: str = Form("[]"),
):
    try:
        chain_list = [ChainEntry(**c) for c in json.loads(chain or "[]")]
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid chain JSON"})

    try:
        existing_emails, existing_phones = await eml_store.fetch_dedup_keys()
    except Exception as e:
        logger.error("dedup fetch failed: %s", e)
        return JSONResponse(status_code=503, content={"ok": False, "error": f"EML store unavailable: {e}"})

    results = []
    counts = {"new": 0, "duplicate": 0, "error": 0}

    for uf in files:
        name = uf.filename or "unnamed.eml"
        try:
            raw = await uf.read()
            if len(raw) > 10 * 1024 * 1024:
                raise ValueError("file too large (max 10MB)")
            parsed = parse_eml_bytes(raw, name)
            local = extract_local_fields(parsed)
            ai = await extract_json(chain_list, build_llm_prompt(parsed)) if chain_list else None
            extraction = "llm" if ai else "fallback"
            contact = _pick_contact(merge_fields(local, ai), parsed)

            email_id = await eml_store.insert_email({
                "file_name": name,
                "subject": parsed.subject,
                "date": parsed.date,
                "sender_name": parsed.sender_name,
                "sender_email": parsed.sender_email,
                "receiver_name": parsed.receiver_name,
                "receiver_email": parsed.receiver_email,
                "body_text": parsed.body_text,
                "has_signature": parsed.has_signature,
            })

            reason = is_duplicate(contact.get("email"), contact.get("phone_primary"),
                                  existing_emails, existing_phones)
            status = "DUPLICATE" if reason else "NEW"
            if not reason:
                if contact.get("email"):
                    existing_emails.add(normalize_email(contact["email"]))
                ph = normalize_phone(contact.get("phone_primary"))
                if len(ph) >= 10:
                    existing_phones.add(ph)

            # still store duplicate rows (with flag) — browseable, not re-pushed silently
            cid = await eml_store.insert_contact({
                **contact,
                "source_email_id": email_id,
                "source_file": name,
                "dedup_status": status,
                "pushed_to_crm": False,
            })
            counts["new" if status == "NEW" else "duplicate"] += 1
            results.append({"file": name, "status": status, "extraction": extraction,
                            "contact_id": cid, "email_id": email_id, "contact": contact})
        except Exception as e:
            logger.exception("process failed for %s", name)
            counts["error"] += 1
            results.append({"file": name, "status": "ERROR", "extraction": "none",
                            "error": str(e), "contact": None})

    return JSONResponse({"ok": True, "results": results, "counts": counts})

@router.get("/eml/contacts")
async def eml_list_contacts(
    search: str = "",
    status: str = "",
    pushed: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    try:
        return await eml_store.list_contacts(search, status, pushed, page, page_size)
    except Exception as e:
        raise HTTPException(503, f"EML store unavailable: {e}")

@router.get("/eml/emails")
async def eml_list_emails(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    try:
        return await eml_store.list_emails(page, page_size)
    except Exception as e:
        raise HTTPException(503, f"EML store unavailable: {e}")

@router.get("/eml/emails/{email_id}")
async def eml_get_email(email_id: str):
    row = await eml_store.get_email(email_id)
    if not row:
        raise HTTPException(404, "Email not found")
    return row

@router.get("/eml/contacts/export")
async def eml_export_csv(
    search: str = "",
    status: str = "",
    pushed: Optional[bool] = None,
):
    data = await eml_store.list_contacts(search, status, pushed, page=1, page_size=500)
    cols = ["name", "email", "phone_primary", "phone_secondary", "company", "designation",
            "address", "city", "pincode", "website", "source_file", "dedup_status", "pushed_to_crm"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for row in data["items"]:
        w.writerow([row.get(c, "") for c in cols])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=eml_contacts.csv"},
    )

async def _push_one(db: AsyncSession, contact: dict) -> str:
    email = contact.get("email") or ""
    if email and not validate_email(email):
        email = ""
    phone = contact.get("phone_primary") or ""
    if phone and classify_phone(phone) == "INVALID":
        phone = ""
    if not email and not phone:
        raise HTTPException(400, "Contact has no valid email or phone")

    cin = ContactIn(
        company_name=contact.get("company"),
        contact_name=contact.get("name"),
        email_primary=email or None,
        phone_primary=phone or None,
        phone_secondary=contact.get("phone_secondary"),
        address=contact.get("address"),
        city=contact.get("city"),
        pincode=contact.get("pincode"),
        website=contact.get("website"),
        position=contact.get("designation"),
        files=contact.get("source_file"),
        raw_data={k: contact.get(k) for k in FIELD_KEYS},
    )
    company = await _find_or_create_company(db, cin.company_name, cin) if cin.company_name else None
    c = Contact(
        company_id=company.id if company else None,
        name=cin.contact_name,
        email_primary=cin.email_primary,
        phone_primary=cin.phone_primary,
        phone_secondary=cin.phone_secondary,
        address=cin.address,
        position=cin.position,
        files=cin.files,
    )
    # city/pincode/website live on company in this schema; set via company if present
    db.add(c)
    await db.flush()
    return str(c.id)

@router.post("/eml/contacts/{contact_id}/push")
async def eml_push_contact(
    contact_id: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(verify_token),
):
    contact = await eml_store.get_contact(contact_id)
    if not contact:
        raise HTTPException(404, "Contact not found")
    crm_id = await _push_one(db, contact)
    await db.commit()
    await eml_store.mark_pushed(contact_id)
    return {"ok": True, "crm_contact_id": crm_id, "pushed": True}

@router.post("/eml/contacts/push-bulk")
async def eml_push_bulk(
    body: PushBulkBody,
    db: AsyncSession = Depends(get_db),
    _user=Depends(verify_token),
):
    pushed, failed = 0, []
    for cid in body.ids:
        contact = await eml_store.get_contact(cid)
        if not contact:
            failed.append({"id": cid, "error": "not found"})
            continue
        try:
            await _push_one(db, contact)
            await eml_store.mark_pushed(cid)
            pushed += 1
        except HTTPException as e:
            failed.append({"id": cid, "error": e.detail})
    await db.commit()
    return {"ok": True, "pushed": pushed, "failed": failed}
```

Clean up the silly `AsyncSession as S` import line — do not include it.

Also fix: Contact model fields — check `db/models.py` for actual column names (`name` vs `contact_name` etc.) before writing `Contact(...)` kwargs; map to real columns: company_id, name, email_primary, phone_primary, phone_secondary, address, position, files (and company city/pincode/website via `_find_or_create_company` + update company row if needed).

- [ ] **Step 4: Wire router in `main.py`**

Add after other imports:
```python
from api.eml import router as eml_new_router
```
Add after sig_router include:
```python
app.include_router(eml_new_router, prefix="/api")
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/ -v 2>&1 | tail -25`
Expected: ALL PASS including `test_eml_api.py`

If Contact column mismatch fails push tests: there is no push test above — verify manually:
```bash
python -c "from db.models import Contact; print([c.name for c in Contact.__table__.columns])"
```
and align `_push_one`.

- [ ] **Step 6: Commit**

```bash
git add api/eml.py main.py tests/test_eml_api.py
git commit -m "feat(eml): fresh /api/eml routes — process, list, export, push"
```

---

### Task 7: Frontend — new EML views + `eml.js`

**Files:**
- Modify: `frontend/index.html` (nav + 4 views + script tag)
- Create: `frontend/eml.js`
- Modify: `frontend/app.js` (`showView` titles for new views only — small patch)
- Modify: `frontend/style.css` (minimal view styles)

**Interfaces:**
- Consumes: `API_BASE`, `apiHeaders()`, `getAuthToken()`, `showNotification()`, `escapeHTML()`/`escHtml` (use own `e()` helper in eml.js to avoid coupling), XLSX global, `showView()` from app.js
- Produces global `EmlUI` behaviors wired to onclick handlers; localStorage key `EML_LLM_CHAIN`

- [ ] **Step 1: index.html — nav items** (replace old EML Pipeline nav, after History):

```html
<div class="nav-item" data-view="eml-upload" title="EML Upload" onclick="showView('eml-upload'); if(window.innerWidth<=768)toggleSidebar()">
  <span class="ni-icon">✉</span> <span class="ni-label">EML Upload</span>
</div>
<div class="nav-item" data-view="eml-contacts" title="EML Contacts" onclick="showView('eml-contacts'); if(window.innerWidth<=768)toggleSidebar()">
  <span class="ni-icon">👥</span> <span class="ni-label">EML Contacts</span>
</div>
<div class="nav-item" data-view="eml-emails" title="EML Emails" onclick="showView('eml-emails'); if(window.innerWidth<=768)toggleSidebar()">
  <span class="ni-icon">📨</span> <span class="ni-label">EML Emails</span>
</div>
<div class="nav-item" data-view="eml-settings" title="LLM Settings" onclick="showView('eml-settings'); if(window.innerWidth<=768)toggleSidebar()">
  <span class="ni-icon">⚙</span> <span class="ni-label">LLM Settings</span>
</div>
```

- [ ] **Step 2: index.html — 4 view containers** (insert before `view-history`):

```html
<div class="view" id="view-eml-upload">
  <div class="sec-hd"><div>
    <div class="sec-title">EML Upload</div>
    <div class="sec-sub">Drop .eml files — parsed on the server, AI-extracted, deduped</div>
  </div></div>
  <div class="drop-zone" id="emlDropZone" style="margin-top:16px">
    <div class="drop-circle">📧</div>
    <div class="drop-title">Drop .eml files here or click to browse</div>
    <div class="drop-desc">Single or bulk · multi-provider LLM fallback · auto dedup</div>
    <button class="btn btn-primary" type="button" id="emlPickBtn">Choose Files</button>
    <input type="file" id="emlFileInput" accept=".eml" multiple style="display:none">
  </div>
  <div id="emlProgress" style="display:none;margin-top:20px">
    <div class="progress-track" style="height:10px;border-radius:6px"><div class="progress-fill" id="emlProgressBar" style="width:0%"></div></div>
    <div id="emlProgressLabel" style="margin-top:8px;font-size:13px;color:var(--text-2)"></div>
  </div>
  <div id="emlResults" style="margin-top:20px"></div>
</div>

<div class="view" id="view-eml-contacts">
  <div class="sec-hd"><div>
    <div class="sec-title">EML Contacts</div>
    <div class="sec-sub">Extracted contacts — search, filter, export, push</div>
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
    <input id="emlCSearch" class="tbl-select" placeholder="Search name/email/phone…" style="min-width:200px">
    <select id="emlCStatus" class="tbl-select"><option value="">All status</option><option>NEW</option><option>DUPLICATE</option></select>
    <select id="emlCPushed" class="tbl-select"><option value="">Pushed: all</option><option value="false">Not pushed</option><option value="true">Pushed</option></select>
    <button class="btn btn-secondary btn-sm" onclick="EmlUI.loadContacts()">↻ Refresh</button>
    <button class="btn btn-success btn-sm" onclick="EmlUI.exportExcel()">⬇ Excel</button>
    <button class="btn btn-secondary btn-sm" onclick="EmlUI.exportCsv()">⬇ CSV</button>
    <button class="btn btn-primary btn-sm" onclick="EmlUI.pushSelected()">💾 Push selected</button>
  </div></div>
  <div style="overflow:auto;margin-top:12px;border:1px solid var(--border);border-radius:10px">
    <table class="data-table" id="emlContactsTable"><thead></thead><tbody></tbody></table>
  </div>
  <div id="emlContactsPager" style="margin-top:10px;display:flex;gap:8px;align-items:center"></div>
</div>

<div class="view" id="view-eml-emails">
  <div class="sec-hd"><div>
    <div class="sec-title">EML Emails</div>
    <div class="sec-sub">Inbox-style list of processed emails</div>
  </div>
  <button class="btn btn-secondary btn-sm" onclick="EmlUI.loadEmails()">↻ Refresh</button></div>
  <div id="emlEmailsList" style="margin-top:12px;display:flex;flex-direction:column;gap:8px"></div>
  <div id="emlEmailsPager" style="margin-top:10px;display:flex;gap:8px;align-items:center"></div>
</div>

<div class="view" id="view-eml-settings">
  <div class="sec-hd"><div>
    <div class="sec-title">LLM Settings</div>
    <div class="sec-sub">Ordered fallback chain — Google, OpenRouter, Groq, OpenAI, DeepSeek, Anthropic</div>
  </div></div>
  <p style="font-size:13px;color:var(--text-2)">Keys stay in this browser (localStorage). First working provider wins; failures fall through the chain.</p>
  <div id="emlChainList" style="display:flex;flex-direction:column;gap:12px;margin-top:12px"></div>
  <div style="display:flex;gap:8px;margin-top:16px">
    <button class="btn btn-secondary btn-sm" onclick="EmlUI.addChainItem()">+ Add provider</button>
    <button class="btn btn-primary" onclick="EmlUI.saveChain()">Save settings</button>
  </div>
</div>
```

- [ ] **Step 3: index.html — load eml.js**

After `<script src="app.js"></script>` add:
```html
<script src="eml.js"></script>
```

- [ ] **Step 4: app.js showView titles patch**

In titles object add:
```javascript
'eml-upload':'EML Upload','eml-contacts':'EML Contacts','eml-emails':'EML Emails','eml-settings':'LLM Settings'
```
And extend the topSub else-branch guard: `if (!['upload','mapping','processing','eml-upload','eml-contacts','eml-emails','eml-settings'].includes(id))`.
Also add hooks: `if (id==='eml-contacts') EmlUI.loadContacts(); if (id==='eml-emails') EmlUI.loadEmails(); if (id==='eml-settings') EmlUI.renderChain();` (guard `if (window.EmlUI)`).

- [ ] **Step 5: Implement `frontend/eml.js`** (complete file)

```javascript
/* frontend/eml.js — fresh EML feature (upload, contacts, emails, LLM chain, export, push) */
(function () {
  const API = window.CRM_API_BASE || '';
  const e = (s) => (s == null ? '' : String(s))
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const notify = (m, t) => { if (window.showNotification) showNotification(m, t || 'info'); };

  const CHAIN_KEY = 'EML_LLM_CHAIN';
  const PROVIDERS = [
    { id: 'gemini', label: 'Google Gemini', models: ['gemini-2.0-flash', 'gemini-2.5-flash-preview-05-20', 'gemini-1.5-flash'] },
    { id: 'openrouter', label: 'OpenRouter', models: ['openai/gpt-4o-mini', 'anthropic/claude-3.5-haiku', 'google/gemini-2.0-flash-001'] },
    { id: 'groq', label: 'Groq', models: ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'gemma2-9b-it'] },
    { id: 'openai', label: 'OpenAI', models: ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini'] },
    { id: 'deepseek', label: 'DeepSeek', models: ['deepseek-chat', 'deepseek-reasoner'] },
    { id: 'anthropic', label: 'Anthropic', models: ['claude-3-5-haiku-20241022', 'claude-3-5-sonnet-20241022'] },
  ];

  function getChain() {
    try { return JSON.parse(localStorage.getItem(CHAIN_KEY) || '[]'); } catch { return []; }
  }
  function saveChainLocal(chain) { localStorage.setItem(CHAIN_KEY, JSON.stringify(chain)); }

  async function authHeaders() {
    const h = {};
    if (window.getAuthToken) {
      try { const t = await getAuthToken(); if (t) h['Authorization'] = `Bearer ${t}`; } catch {}
    }
    return h;
  }

  const state = { contacts: [], contactPage: 1, contactTotal: 0, emails: [], emailPage: 1, emailTotal: 0, selected: new Set() };

  // ── Upload ──────────────────────────────────────────────
  async function processFiles(fileList) {
    const files = Array.from(fileList).filter(f => /\.eml$/i.test(f.name));
    if (!files.length) return notify('No .eml files selected', 'error');
    const fd = new FormData();
    files.forEach(f => fd.append('files', f));
    fd.append('chain', JSON.stringify(getChain()));
    const bar = document.getElementById('emlProgressBar');
    const label = document.getElementById('emlProgressLabel');
    const results = document.getElementById('emlResults');
    document.getElementById('emlProgress').style.display = 'block';
    results.innerHTML = '';
    bar.style.width = '10%';
    label.textContent = `Uploading ${files.length} file(s)…`;
    try {
      const res = await fetch(`${API}/api/eml/process`, { method: 'POST', body: fd });
      bar.style.width = '100%';
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || res.statusText);
      label.textContent = `Done — ${data.counts.new} new · ${data.counts.duplicate} dupes · ${data.counts.error} errors`;
      renderResults(data.results);
      notify(`Processed ${files.length} file(s)`, 'success');
    } catch (err) {
      label.textContent = 'Failed';
      notify('Process failed: ' + err.message, 'error');
      bar.style.width = '0%';
    }
  }

  function renderResults(results) {
    const el = document.getElementById('emlResults');
    el.innerHTML = `<div style="border:1px solid var(--border);border-radius:10px;overflow:auto">
      <table class="data-table"><thead><tr>
        <th>File</th><th>Status</th><th>Extraction</th><th>Name</th><th>Email</th><th>Phone</th><th>Company</th><th>Designation</th>
      </tr></thead><tbody>
      ${results.map(r => {
        const c = r.contact || {};
        const color = r.status === 'NEW' ? '#16A34A' : r.status === 'DUPLICATE' ? '#D97706' : '#E11D48';
        return `<tr><td>${e(r.file)}</td>
          <td style="color:${color};font-weight:600">${e(r.status)}</td>
          <td>${e(r.extraction)}</td>
          <td>${e(c.name)}</td><td>${e(c.email)}</td><td>${e(c.phone_primary)}</td>
          <td>${e(c.company)}</td><td>${e(c.designation)}</td></tr>`;
      }).join('')}
      </tbody></table></div>
      <div style="margin-top:12px"><button class="btn btn-primary" onclick="showView('eml-contacts')">View all contacts →</button></div>`;
  }

  // ── Contacts ───────────────────────────────────────────
  async function loadContacts(page) {
    state.contactPage = page || 1;
    const search = document.getElementById('emlCSearch')?.value || '';
    const status = document.getElementById('emlCStatus')?.value || '';
    const pushed = document.getElementById('emlCPushed')?.value || '';
    const qs = new URLSearchParams({ page: state.contactPage, page_size: 50 });
    if (search) qs.set('search', search);
    if (status) qs.set('status', status);
    if (pushed) qs.set('pushed', pushed);
    try {
      const res = await fetch(`${API}/api/eml/contacts?${qs}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      state.contacts = data.items; state.contactTotal = data.total;
      state.selected = new Set();
      renderContacts();
    } catch (err) { notify('Load contacts failed: ' + err.message, 'error'); }
  }

  function renderContacts() {
    const table = document.getElementById('emlContactsTable');
    const cols = ['name','email','phone_primary','phone_secondary','company','designation','city','source_file','dedup_status','pushed_to_crm'];
    table.querySelector('thead').innerHTML = `<tr><th><input type="checkbox" id="emlSelAll"></th>${cols.map(c => `<th>${c}</th>`).join('')}</tr>`;
    table.querySelector('tbody').innerHTML = state.contacts.map(r => `<tr>
      <td><input type="checkbox" class="eml-row-sel" value="${e(r.id)}" ${state.selected.has(r.id)?'checked':''}></td>
      ${cols.map(c => `<td>${e(r[c])}</td>`).join('')}
    </tr>`).join('') || `<tr><td colspan="11" style="padding:20px;text-align:center;color:var(--text-2)">No contacts yet</td></tr>`;
    document.getElementById('emlSelAll')?.addEventListener('change', ev => {
      table.querySelectorAll('.eml-row-sel').forEach(cb => {
        cb.checked = ev.target.checked;
        if (ev.target.checked) state.selected.add(cb.value); else state.selected.delete(cb.value);
      });
    });
    table.querySelectorAll('.eml-row-sel').forEach(cb => cb.addEventListener('change', () => {
      if (cb.checked) state.selected.add(cb.value); else state.selected.delete(cb.value);
    }));
    const pages = Math.max(1, Math.ceil(state.contactTotal / 50));
    document.getElementById('emlContactsPager').innerHTML =
      `<button class="btn btn-secondary btn-sm" ${state.contactPage<=1?'disabled':''} onclick="EmlUI.loadContacts(${state.contactPage-1})">← Prev</button>
       <span style="font-size:12px;color:var(--text-2)">Page ${state.contactPage} / ${pages} · ${state.contactTotal} total</span>
       <button class="btn btn-secondary btn-sm" ${state.contactPage>=pages?'disabled':''} onclick="EmlUI.loadContacts(${state.contactPage+1})">Next →</button>`;
  }

  function exportExcel() {
    if (!state.contacts.length) return notify('No contacts to export', 'error');
    const cols = ['name','email','phone_primary','phone_secondary','company','designation','address','city','pincode','website','source_file','dedup_status','pushed_to_crm'];
    const rows = state.contacts.map(r => cols.map(c => r[c] ?? ''));
    const ws = XLSX.utils.aoa_to_sheet([cols, ...rows]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'EML Contacts');
    XLSX.writeFile(wb, `eml_contacts_${Date.now()}.xlsx`);
  }

  function exportCsv() {
    const search = document.getElementById('emlCSearch')?.value || '';
    const status = document.getElementById('emlCStatus')?.value || '';
    const pushed = document.getElementById('emlCPushed')?.value || '';
    const qs = new URLSearchParams({ format: 'csv' });
    if (search) qs.set('search', search);
    if (status) qs.set('status', status);
    if (pushed) qs.set('pushed', pushed);
    window.location.href = `${API}/api/eml/contacts/export?${qs}`;
  }

  async function pushSelected() {
    const ids = [...state.selected];
    if (!ids.length) return notify('Select contacts first', 'error');
    try {
      const headers = Object.assign({ 'Content-Type': 'application/json' }, await authHeaders());
      const res = await fetch(`${API}/api/eml/contacts/push-bulk`, {
        method: 'POST', headers, body: JSON.stringify({ ids }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      notify(`Pushed ${data.pushed} contact(s)${data.failed?.length ? `, ${data.failed.length} failed` : ''}`, data.failed?.length ? 'info' : 'success');
      loadContacts(state.contactPage);
    } catch (err) { notify('Push failed: ' + err.message, 'error'); }
  }

  // ── Emails ─────────────────────────────────────────────
  async function loadEmails(page) {
    state.emailPage = page || 1;
    try {
      const res = await fetch(`${API}/api/eml/emails?page=${state.emailPage}&page_size=50`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      state.emails = data.items; state.emailTotal = data.total;
      renderEmails();
    } catch (err) { notify('Load emails failed: ' + err.message, 'error'); }
  }

  function renderEmails() {
    const list = document.getElementById('emlEmailsList');
    list.innerHTML = state.emails.map(m => `
      <div class="eml-mail-row" style="border:1px solid var(--border);border-radius:10px;padding:12px 14px;cursor:pointer;background:var(--bg-1)"
           onclick="EmlUI.openEmail('${e(m.id)}')">
        <div style="display:flex;justify-content:space-between;gap:12px">
          <strong style="font-size:14px">${e(m.subject || '(no subject)')}</strong>
          <span style="font-size:12px;color:var(--text-2);white-space:nowrap">${e(m.date)}</span>
        </div>
        <div style="font-size:12px;color:var(--text-2);margin-top:4px">
          From: ${e(m.sender_name)} &lt;${e(m.sender_email)}&gt; → ${e(m.receiver_email)}
          ${m.has_signature ? ' · ✍ signature' : ''}
        </div>
      </div>`).join('') || `<div class="empty-state">No emails processed yet</div>`;
    const pages = Math.max(1, Math.ceil(state.emailTotal / 50));
    document.getElementById('emlEmailsPager').innerHTML =
      `<button class="btn btn-secondary btn-sm" ${state.emailPage<=1?'disabled':''} onclick="EmlUI.loadEmails(${state.emailPage-1})">← Prev</button>
       <span style="font-size:12px;color:var(--text-2)">Page ${state.emailPage} / ${pages} · ${state.emailTotal}</span>
       <button class="btn btn-secondary btn-sm" ${state.emailPage>=pages?'disabled':''} onclick="EmlUI.loadEmails(${state.emailPage+1})">Next →</button>`;
  }

  async function openEmail(id) {
    try {
      const res = await fetch(`${API}/api/eml/emails/${id}`);
      const m = await res.json();
      if (!res.ok) throw new Error(m.detail || 'Not found');
      const body = (m.body_text || '').slice(0, 4000);
      notify(`${m.subject || 'Email'} — ${(m.contacts || []).length} contact(s) extracted`, 'info');
      alert(
        `Subject: ${m.subject || ''}\nFrom: ${m.sender_name} <${m.sender_email}>\nTo: ${m.receiver_email}\nSignature: ${m.has_signature ? 'yes' : 'no'}\n\n` +
        `Contacts: ${(m.contacts || []).map(c => c.name || c.email).join(', ') || 'none'}\n\n---\n${body}`
      );
    } catch (err) { notify(err.message, 'error'); }
  }

  // ── LLM chain settings ─────────────────────────────────
  function renderChain() {
    const chain = getChain();
    const box = document.getElementById('emlChainList');
    if (!chain.length) {
      box.innerHTML = `<div class="empty-state" style="border:1px dashed var(--border);border-radius:10px;padding:24px;text-align:center;color:var(--text-2)">
        No providers yet — extraction will use local regex fallback only. Add at least one provider.</div>`;
      return;
    }
    box.innerHTML = chain.map((c, i) => {
      const p = PROVIDERS.find(x => x.id === c.provider) || PROVIDERS[0];
      return `<div style="border:1px solid var(--border);border-radius:10px;padding:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;background:var(--bg-1)">
        <span style="font-weight:600;font-size:12px;color:var(--text-2);min-width:24px">#${i + 1}</span>
        <select class="tbl-select eml-p" data-i="${i}" onchange="EmlUI.onProviderChange(${i})">
          ${PROVIDERS.map(x => `<option value="${x.id}" ${x.id===c.provider?'selected':''}>${x.label}</option>`).join('')}
        </select>
        <select class="tbl-select eml-m" data-i="${i}">
          ${p.models.map(m => `<option ${m===c.model?'selected':''}>${e(m)}</option>`).join('')}
          ${c.model && !p.models.includes(c.model) ? `<option selected>${e(c.model)}</option>` : ''}
        </select>
        <input type="password" class="tbl-select eml-k" data-i="${i}" placeholder="API key" value="${e(c.api_key || '')}" style="flex:1;min-width:160px">
        <button class="btn btn-secondary btn-sm" onclick="EmlUI.moveChain(${i},${i-1})" ${i===0?'disabled':''}>↑</button>
        <button class="btn btn-secondary btn-sm" onclick="EmlUI.moveChain(${i},${i+1})" ${i===chain.length-1?'disabled':''}>↓</button>
        <button class="btn btn-danger btn-sm" onclick="EmlUI.removeChainItem(${i})">✕</button>
      </div>`;
    }).join('');
  }

  function syncChainFromDom() {
    const chain = getChain();
    document.querySelectorAll('#emlChainList .eml-p').forEach(sel => {
      const i = +sel.dataset.i;
      if (chain[i]) chain[i].provider = sel.value;
    });
    document.querySelectorAll('#emlChainList .eml-m').forEach(sel => {
      const i = +sel.dataset.i;
      if (chain[i]) chain[i].model = sel.value;
    });
    document.querySelectorAll('#emlChainList .eml-k').forEach(inp => {
      const i = +inp.dataset.i;
      if (chain[i]) chain[i].api_key = inp.value.trim();
    });
    return chain;
  }

  function addChainItem() {
    const chain = syncChainFromDom();
    chain.push({ provider: 'gemini', model: 'gemini-2.0-flash', api_key: '' });
    saveChainLocal(chain);
    renderChain();
  }
  function removeChainItem(i) {
    const chain = syncChainFromDom();
    chain.splice(i, 1);
    saveChainLocal(chain);
    renderChain();
  }
  function moveChain(from, to) {
    const chain = syncChainFromDom();
    if (to < 0 || to >= chain.length) return;
    const [item] = chain.splice(from, 1);
    chain.splice(to, 0, item);
    saveChainLocal(chain);
    renderChain();
  }
  function onProviderChange(i) {
    const chain = syncChainFromDom();
    const p = PROVIDERS.find(x => x.id === chain[i].provider);
    if (p) chain[i].model = p.models[0];
    saveChainLocal(chain);
    renderChain();
  }
  function saveChain() {
    const chain = syncChainFromDom().filter(c => c.provider && c.model);
    saveChainLocal(chain);
    const missing = chain.filter(c => !c.api_key).length;
    notify(missing ? `Saved — ${missing} provider(s) missing keys (will be skipped)` : 'LLM chain saved', missing ? 'info' : 'success');
  }

  // ── boot ───────────────────────────────────────────────
  function initUpload() {
    const input = document.getElementById('emlFileInput');
    const zone = document.getElementById('emlDropZone');
    if (!input || !zone) return;
    document.getElementById('emlPickBtn')?.addEventListener('click', ev => { ev.stopPropagation(); input.click(); });
    zone.addEventListener('click', () => input.click());
    input.addEventListener('change', () => { if (input.files.length) processFiles(input.files); input.value = ''; });
    zone.addEventListener('dragover', ev => { ev.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', ev => {
      ev.preventDefault(); zone.classList.remove('drag-over');
      if (ev.dataTransfer.files.length) processFiles(ev.dataTransfer.files);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initUpload);
  } else { initUpload(); }

  window.EmlUI = {
    loadContacts, exportExcel, exportCsv, pushSelected,
    loadEmails, openEmail,
    renderChain, addChainItem, removeChainItem, moveChain, onProviderChange, saveChain,
  };
})();
```

- [ ] **Step 6: Minimal CSS** — append to `style.css`:

```css
/* Fresh EML views */
#view-eml-upload .drop-zone.drag-over,
.eml-mail-row:hover { border-color: var(--accent, #378ADD); }
.eml-mail-row { transition: border-color .15s ease; }
#emlContactsTable th { text-transform: capitalize; font-size: 11px; color: var(--text-2); }
#emlContactsTable td { font-size: 12px; padding: 8px 10px; border-bottom: 1px solid var(--border); }
```

- [ ] **Step 7: Grep for dangling references**

Run:
```bash
grep -nE "emlSaveToSupabase|handleEmlFile|view-eml-pipeline|emlPipeline" frontend/*.html frontend/*.js || echo CLEAN
node --check frontend/eml.js && node --check frontend/app.js
```
Expected: CLEAN; both syntax OK.

- [ ] **Step 8: Manual browser smoke (local)**

Run: `python -m uvicorn main:app --port 8000`
Open `http://localhost:8000` → sidebar shows 4 EML items → LLM Settings renders/adds providers → Upload accepts only .eml → Contacts/Emails show empty states without JS errors (console).

- [ ] **Step 9: Commit**

```bash
git add frontend/index.html frontend/eml.js frontend/app.js frontend/style.css
git commit -m "feat(eml): fresh frontend — upload, contacts, emails, LLM chain, export, push"
```

---

### Task 4b (fold into Task 5/6 timing): full pipeline integration test

Covered by `tests/test_eml_api.py` (process NEW/DUPLICATE/fallback). No separate task.

---

### Task 8: Final verification & cleanup

- [ ] **Step 1: Full test suite**

Run: `pytest tests/ -v 2>&1 | tail -30`
Expected: 0 failed

- [ ] **Step 2: No old-EML / n8n residue**

Run:
```bash
grep -rnE "eml_pipeline|eml_monitor|eml_sse|eml_batch|eml_retry|EmlJob|handleBulkEml|n8n" \
  --include='*.py' --include='*.js' --include='*.html' --include='*.md' . \
  | grep -v venv | grep -v docs/superpowers | grep -v __pycache__ || echo CLEAN
ls n8n* 2>/dev/null || echo "no n8n files"
```
Expected: CLEAN; no n8n files

- [ ] **Step 3: Spec coverage checklist** (manual)

- [ ] Multi-provider chain gemini/openrouter/groq/openai/deepseek/anthropic — settings UI + router
- [ ] Fields: name, sender, receiver, email, phones, company, designation (nullable), address, city, pincode, website, source_*, dedup_status, pushed_to_crm
- [ ] Dedup email OR phone≥10
- [ ] Views: upload, contacts, emails, settings, export/push
- [ ] Excel client-side + CSV server-side
- [ ] push-to-CRM single + bulk with auth
- [ ] n8n deleted

- [ ] **Step 4: Live smoke with `eml examples/` (if keys available)**

Run server, upload 2-3 files from `eml examples/`, confirm NEW/DUPLICATE badges, contacts list fills, Excel downloads.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(eml): complete fresh EML contact intelligence rebuild"
```

- [ ] **Step 6: Deploy notes for user** (do not deploy unless asked)

- Run `db/eml_supabase_schema.sql` once in EML Supabase SQL editor
- Set Render env: `EML_SUPABASE_URL`, `EML_SUPABASE_ANON_KEY`
- Confirm Supabase RLS allows anon insert/select/update on `eml_emails`/`eml_contacts` (or use service role key server-side if RLS blocks)

---

## Self-Review notes (fixed during writing)

- Spec §4 contact validity (email OR phone): enforced in `_push_one` (push rejects neither-nor) and process always stores extracted fields with dedup flag — matches spec "no silent drops"
- Spec §5 empty chain → local fallback: Task 6 skips `extract_json` when chain empty; test `test_process_empty_chain_uses_fallback`
- Spec §6 all endpoints present including CSV export; xlsx is client-side per Global Constraints
- Type consistency: `ChainEntry(provider, model, api_key)` used in api + router; `ParsedEml` fields match processor tests; `EmlUI.*` names match index.html onclick + showView hooks
- `_html_to_text` return annotation typo called out inline for executor
