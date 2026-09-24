# EML Contact Intelligence — Fresh Rebuild Design

> **Date:** 2026-09-24
> **Status:** Approved (design sections 1–4)
> **Scope:** Rebuild ONLY the EML feature from scratch. Rest of the CRM site stays as-is. No n8n — all processing in Python code on the existing Render service.

---

## 1. Goal

Replace the old EML feature (frontend MIME parsing + n8n webhook → Gemini → Google Sheets) with a pure-backend pipeline:

**Upload .eml → server parses MIME → multi-provider LLM fallback-chain extraction → dedup → save to EML Supabase → browse/export/push-to-CRM.**

Success: any common .eml type parses; required fields land in the DB; contacts exportable to Excel; LLM providers (Google, OpenRouter, Groq, OpenAI, DeepSeek, Anthropic) work as an ordered failover chain.

---

## 2. Approach (approved)

Backend pipeline inside the existing FastAPI app (Approach A):

- New `services/eml_processor.py` + `services/llm_router.py` + `api/eml.py`
- New frontend EML views replace old `view-eml` / bulk-EML code
- Same Render service, same auth/rate-limit/DB session patterns
- No new microservice, no n8n, no new Python deps for core flow (stdlib `email` for MIME; existing `httpx`, `XLSX.js` client-side for Excel)

---

## 3. Processing Flow

```
Frontend upload .eml (single or bulk)
  → POST /api/eml/process (multipart)
  → services/eml_processor.py:
      1. Parse MIME (Python stdlib email module)
         - headers: From, To, Subject, Date
         - walk parts: text/plain, text/html (HTML → text), skip attachments
         - decode base64 / quoted-printable / RFC 2047 encoded-words
      2. Signature detection (local heuristic):
         - "-- " delimiter, or trailing cluster containing phone/email/company
         - sets has_signature; isolates signature block for extraction
      3. Build extraction prompt: headers + signature block (or body fallback)
      4. services/llm_router.py:
         - ordered user-configured chain of providers
         - per provider: 3 retries, exponential backoff (1s, 2s, 4s)
         - on error/rate-limit/invalid-JSON → failover to next provider
         - LRU cache keyed by md5(model + prompt) (existing pattern)
         - total failure → local regex fallback extraction
      5. Parse structured JSON → contact fields
      6. Local scans (always): emails, phone numbers from body/signature
      7. Dedup (n8n logic port):
         - normalize: email lowercase; phone strip non-digits
         - email match OR phone ≥10 digits match → DUPLICATE
         - else → NEW
      8. Save to EML Supabase: eml_emails + eml_contacts
  → return per-file result {ok, duplicate, contact, error}
```

Bulk: one bad file does not fail the batch; each file gets its own result entry.

### Local regex fallback (LLM unavailable)

Extract whatever is present: emails, Indian mobile `(\+91)?[6-9]\d{9}`, international `\+\d+`, company keywords (Ltd/Pvt/Inc/LLP), website, pincode. Missing fields stay null — absence is OK per field requirements.

---

## 4. Data Schema (EML Supabase project `ewlcrbkfwwaunpdanbcv`)

### `eml_emails`

| Field | Required | Source |
|-------|----------|--------|
| `file_name` | yes | upload |
| `subject` | no | MIME header |
| `date` | no | MIME header |
| `sender_name` | no | From header |
| `sender_email` | yes | From header |
| `receiver_name` | no | To header (multiple joined) |
| `receiver_email` | yes | To header |
| `body_text` | no | decoded body (preview) |
| `has_signature` | yes | signature heuristic |

### `eml_contacts`

| Field | Required | Source |
|-------|----------|--------|
| `name` | no | signature or From |
| `email` | yes* | signature or sender_email |
| `phone_primary` | no | signature/body scan |
| `phone_secondary` | no | signature/body scan |
| `company` | no | signature (LLM + regex) |
| `designation` | no | signature (LLM) — **absence OK** |
| `address` | no | signature |
| `city` | no | signature |
| `pincode` | no | signature |
| `website` | no | signature |
| `source_email_id` | yes | FK/linkage to eml_emails |
| `source_file` | yes | original file name |
| `dedup_status` | yes | `NEW` / `DUPLICATE` |
| `pushed_to_crm` | bool | default false; set true on push |

\* Contact is valid if **at least one** of email / phone_primary is present (aligns with CRM batch rule). Otherwise file is saved with contact fields as extracted but flagged in result as low-completeness (still stored — no silent drops).

If Supabase tables are missing, backend creates them on first use (`create table if not exists` via SQL) or fails with a clear setup error — decide at implementation: prefer explicit migration SQL in repo (`db/eml_supabase_schema.sql`) run once by the user.

---

## 5. LLM Router

Chain config from frontend, stored client-side only (same security pattern as existing `CRM_AI_SETTINGS`):

```json
[
  { "provider": "google",    "model": "gemini-2.0-flash", "apiKey": "..." },
  { "provider": "openrouter","model": "...",              "apiKey": "..." },
  { "provider": "groq",      "model": "llama-3.3-70b-versatile", "apiKey": "..." },
  { "provider": "openai",    "model": "gpt-4o-mini",      "apiKey": "..." },
  { "provider": "deepseek",  "model": "deepseek-chat",    "apiKey": "..." },
  { "provider": "anthropic", "model": "claude-3-5-haiku-20241022", "apiKey": "..." }
]
```

- **Providers:** Google Gemini, OpenRouter, Groq, OpenAI, DeepSeek, Anthropic (OpenAI-compatible adapters where applicable; Gemini has its own REST shape)
- **Sent with each** `POST /api/eml/process` request body
- **Failover:** try in order; skip on 4xx/5xx/timeout/bad JSON; next provider
- **Retries:** 3 per provider, backoff 1s/2s/4s
- **Response contract:** strict JSON `{name, email, phone_primary, phone_secondary, company, designation, address, city, pincode, website}` — any field may be null
- **System prompt:** "Extract from this email signature/header info; return only JSON; null if unknown"
- **No backend key storage.** Empty chain → local fallback only (still works, degraded)

---

## 6. API Endpoints (`/api/eml`, rate-limited via existing slowapi)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/eml/process` | Single/bulk .eml upload → full pipeline → per-file results |
| GET | `/api/eml/contacts` | Paginated contacts; `?search=&status=NEW\|DUPLICATE&pushed=` |
| GET | `/api/eml/emails` | Paginated email list (subject, sender, receiver, date) |
| GET | `/api/eml/emails/{id}` | Email detail + body preview + linked contacts |
| POST | `/api/eml/contacts/{id}/push` | Push contact → main CRM (internal call into existing batch/contact create logic); sets `pushed_to_crm=true` |
| POST | `/api/eml/contacts/push-bulk` | Bulk push selected ids |
| GET | `/api/eml/contacts/export` | CSV export server-side (stdlib csv) — Excel `.xlsx` is client-side via existing XLSX.js (no new Python dep) |

Auth: follow current EML feature level (same as rest of app); do not introduce new auth scope in this rebuild unless trivial to reuse `verify_token`.

---

## 7. Frontend — 5 Views (replaces old EML UI)

Old code deleted: `view-eml` markup, `EML` state, `handleEmlFile`, `parseEml`, `parseSingleEml`, `extractSignatureData`, `buildEmlDashboard`, `renderEmlContacts`, `renderSigPanel`, bulk-EML (`BULK`, `handleBulkEml`, bulk dashboard/export/push), old EML Supabase direct client writes (writes now go through backend).

### 7.1 Upload + processing
- Drop zone: single or multiple `.eml`
- Progress bar; per-file row: filename → `NEW` / `DUPLICATE` / `ERROR` badge
- Bulk continues on individual failures

### 7.2 Contacts browser
- Table columns: name, email, phone_primary, phone_secondary, company, designation, source_file, dedup_status, pushed_to_crm
- Search (name/email/phone/company); filters: status, pushed
- Pagination

### 7.3 Emails list (inbox-style)
- Rows: subject, sender_name/email, receiver, date, has_signature indicator
- Click → modal: body preview + linked extracted contact(s)

### 7.4 LLM settings
- Ordered chain editor: add/remove/reorder (drag or up/down buttons)
- Per entry: provider select → model dropdown (static lists; OpenRouter may fetch model list like existing AI settings)
- API key input (password field), saved to `localStorage('EML_LLM_CHAIN')`
- Providers: Google, OpenRouter, Groq, OpenAI, DeepSeek, Anthropic
- Test button optional (nice-to-have, not required for v1)

### 7.5 Export + Push
- Select rows (single/bulk checkboxes)
- **Export Excel** — client-side XLSX.js from current filtered/selected contacts (columns = all `eml_contacts` fields)
- **Export CSV** — via backend endpoint (alternative)
- **Push to CRM** — calls push endpoints; success → `pushed_to_crm` badge updates

Navigation: reuse existing sidebar/topbar patterns; new EML section replaces old one. CRM views untouched.

---

## 8. Error Handling

- Per-file results in bulk; HTTP 200 with result array (not all-or-nothing)
- LLM total failure → regex fallback → file still saved; result notes `extraction: "fallback"`
- Dedup/Supabase write failure → file result `error` with message; others continue
- No API keys in logs; never echo keys in responses
- Rate limit endpoint via existing slowapi limiter (reuse pattern from `parse_signature.py`)

---

## 9. Testing

| File | Covers |
|------|--------|
| `tests/test_eml_processor.py` | MIME parse (plain, HTML, multipart, base64, quoted-printable, RFC2047); signature detect true/false; dedup NEW/DUPLICATE (email + phone rules); field extraction fallback; multiple To recipients |
| `tests/test_llm_router.py` | Chain order, failover on error, retry/backoff counts, invalid-JSON failover, cache hit, empty-chain → fallback (providers mocked with httpx/mocking — no live API) |
| Manual | Real files from `eml examples/` against a live configured chain |

**Gate:** `pytest tests/ -v` fully green before calling the feature done.

---

## 10. Explicitly Out of Scope

- n8n (files `n8n-eml-*.md/json` become obsolete; delete during implementation)
- Google Sheets output
- Vision/image-based signature extraction (text-only v1; Gemini vision can be a later chain entry)
- New microservice or second Render instance
- Changes to non-EML CRM features (upload Excel/PDF, dashboards, call logs, analytics)
- Backend storage of LLM keys
- New Python dependencies for Excel (client-side XLSX.js instead)

---

## 11. Files Touched (expected)

**New:**
- `services/eml_processor.py`
- `services/llm_router.py`
- `api/eml.py`
- `db/eml_supabase_schema.sql` (or equivalent migration note)
- `tests/test_eml_processor.py`
- `tests/test_llm_router.py`
- Frontend: EML views (markup section in `index.html` or new partials; logic in `app.js` or `eml.js` — prefer new `frontend/eml.js` to avoid growing the 3.5k-line `app.js` further)

**Modified:**
- `main.py` (register `eml` router)
- `frontend/index.html` (nav + view containers)
- `frontend/style.css` (view styles, reuse theme vars)

**Deleted (old EML feature):**
- Old EML functions/state in `frontend/app.js` (or entire file split if we move to `eml.js`)
- `n8n-eml-setup.md`, `n8n-eml-workflow.json`
- Old EML-specific API files if superseded (`eml_pipeline.py`, `eml_sse.py`, `eml_monitor.py`, `eml_export.py` — confirm usage before delete; superseded by new `api/eml.py`)

---

## 12. Deployment

- Same Render service (`crm-intelligence-api`), no `render.yaml` structural change
- EML Supabase credentials: reuse existing `EML_SUPABASE_URL` / `EML_SUPABASE_ANON_KEY` (or service role if writes need it — check RLS at implementation; prefer least privilege)
- Frontend: same Vercel static hosting, new/updated pages under `frontend/`
