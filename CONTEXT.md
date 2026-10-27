# CRM Developer Dashboard — Full Project Context

> **Last Updated:** 2026-10-16
> **Project Name:** CRM Intelligence / CRM Engine v4.0
> **Stack:** FastAPI (Python) + Vanilla JS SPA + Supabase Auth + PostgreSQL (Supabase) / SQLite (dev)
> **Deployment:** Backend → Render (`crm-developer-dashboard.onrender.com`) | Frontend → Vercel (`crmdevloper.vercel.app`)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Directory Structure](#2-directory-structure)
3. [Architecture Diagram](#3-architecture-diagram)
4. [Backend — Detailed Breakdown](#4-backend--detailed-breakdown)
   - [Entry Point (main.py)](#41-entry-point-mainpy)
   - [Database Layer (db/)](#42-database-layer-db)
   - [Models & Schema (db/models.py)](#43-models--schema-dbmodelspy)
   - [Core Utilities (core/)](#44-core-utilities-core)
   - [API Routes (api/)](#46-api-routes-api)
   - [Services (services/)](#47-services-services)
5. [Frontend — Detailed Breakdown](#5-frontend--detailed-breakdown)
   - [Pages & HTML Structure](#51-pages--html-structure)
   - [Application State (app.js)](#52-application-state-appjs)
   - [Complete Function Reference](#53-complete-function-reference)
   - [Styling & Theming](#54-styling--theming)
   - [Legacy v3 System](#55-legacy-v3-system)
6. [API Endpoint Reference](#6-api-endpoint-reference)
7. [Data Flow & Application Lifecycle](#7-data-flow--application-lifecycle)
8. [External Services & Integrations](#8-external-services--integrations)
9. [Environment Variables](#9-environment-variables)
10. [Deployment Configuration](#10-deployment-configuration)
11. [Testing](#11-testing)
12. [Key Design Decisions & Caveats](#12-key-design-decisions--caveats)

---

## 1. Project Overview

**CRM Developer Dashboard** is a full-stack CRM intelligence platform that transforms raw contact data from various file formats (Excel, PDF, CSV, EML emails) into structured, validated, and enriched CRM records. It provides:

- **Multi-format file parsing** — XLS, XLSX, CSV, TXT, PDF, EML
- **Intelligent field detection** — Auto-maps 23+ field types with confidence scoring
- **Data validation & normalization** — Email regex, Indian/international phone classification, landline detection, title casing
- **Deduplication** — Full-row fingerprint-based exact match detection
- **Dashboard & Analytics** — KPIs, charts (Chart.js), geographic/segment/reachability analytics
- **CRM CRUD** — Contacts, Companies, Call Logs with full create/read/update/delete
- **AI Email Signature Extraction** — Multi-provider LLM chain (Groq, OpenAI, OpenRouter, DeepSeek, Anthropic, Gemini) with ordered failover (`services/llm_router.py`, 1 attempt per provider)
- **EML Contact Intelligence** — Server-side .eml processing (`POST /api/eml/process`): MIME parse, local regex extraction + LLM enrichment, dedup against EML Supabase store, auto-push into CRM contacts
- **Export** — Excel (XLSX.js client-side), PDF (ReportLab server-side), VCF (vCard 3.0), ZIP archive
- **Session History** — Reload, export (with call logs merged), and delete past uploads
- **Authentication** — Supabase Auth (email/password); JWT required on all `/api/*` routes

---

## 2. Directory Structure

```
CRM_Developer/
├── main.py                     # FastAPI app entry point (128 lines)
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (secrets, git-ignored)
├── .gitignore                  # Git ignore rules
├── crm.db                      # Local SQLite database (dev only, git-ignored)
├── render.yaml                 # Render.com deployment config
├── vercel.json                 # Vercel deployment config (frontend)
├── README.md                   # User-facing usage guide
│
├── api/                        # FastAPI route handlers
│   ├── __init__.py
│   ├── auth.py                 # POST /api/auth/upsert
│   ├── calls.py                # Call log CRUD (inline SQLAlchemy, no crud/ layer)
│   ├── contacts.py             # Batch import, CRUD (LARGEST ROUTE FILE — 409 lines)
│   ├── eml.py                  # EML contact intelligence: process, browse, export, push (476 lines)
│   ├── export_pdf.py           # PDF export endpoint
│   ├── history.py              # Session queries + history/export routes
│   └── parse.py                # File upload & parsing (.xls, .pdf)
│
├── core/                       # Shared utilities
│   ├── __init__.py
│   ├── auth.py                 # Supabase JWT verification (verify_token dependency)
│   └── rate_limit.py           # slowapi rate limiter
│
├── db/                         # Database configuration & models
│   ├── __init__.py
│   ├── database.py             # Async SQLAlchemy engine, session factory, init_db()
│   ├── models.py               # 6 ORM models: User, Company, Contact, CallLog, SessionData, Record
│   └── eml_supabase_schema.sql # DDL for eml_emails / eml_contacts (EML Supabase project)
│
├── services/                   # Business logic services
│   ├── __init__.py
│   ├── parser.py               # XLS/PDF parsing with multi-strategy extraction
│   ├── pdf_exporter.py         # ReportLab PDF report generation
│   ├── llm_router.py           # Multi-provider LLM chain: ordered failover, JSON-only extraction
│   ├── eml_processor.py        # .eml MIME parse, local field extraction, LLM merge
│   ├── eml_store.py            # Async wrappers over EML Supabase (eml_emails / eml_contacts)
│   └── eml_dedup_rules.py      # Pure dedup helpers: email/phone/name matching
│
├── frontend/                   # Static SPA frontend (served by FastAPI)
│   ├── index.html              # Main app page (440 lines)
│   ├── signin.html             # Authentication page (605 lines)
│   ├── app.js                  # Core CRM SPA logic (2,160 lines)
│   ├── eml.js                  # EML UI module: process, contacts, emails, LLM settings (433 lines)
│   ├── config.js               # API URL & CRM Supabase keys
│   └── style.css               # Main stylesheet with 4-theme system (2,056 lines)
│
├── scripts/
│   └── clear_data.py           # Manual wipe of CRM tables + EML staging area
│
├── .github/workflows/
│   └── keep-alive.yml          # Cron ping /health every 10 min to keep Render awake
│
├── docs/                       # Developer docs & design plans
│
├── tests/                      # Pytest test suite (7 files, 54 tests)
│   ├── conftest.py             # In-memory SQLite + verify_token dependency override
│   ├── test_api.py             # /api/auth/upsert integration tests
│   ├── test_cors.py            # CORS allow-list preflight contract
│   ├── test_eml_api.py         # /api/eml/* endpoint tests
│   ├── test_eml_dedup_rules.py # Dedup helper tests
│   ├── test_eml_processor.py   # MIME parse / local extraction tests
│   ├── test_llm_router.py      # LLM chain failover / JSON parse tests
│   └── test_parser.py          # Parser helper function tests
│
└── eml examples/               # Sample .eml files for testing
```

---

## 3. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Vercel)                         │
│  signin.html ──► index.html + app.js + eml.js (SPA)               │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ Supabase    │  │ Client-side  │  │ Views: Upload, Map,    │  │
│  │ Auth SDK    │  │ XLSX/CSV     │  │ Dashboard, Analytics,  │  │
│  │             │  │ Parsing      │  │ Table, Quality, Dedup, │  │
│  │             │  │              │  │ History, EML UI module │  │
│  └──────┬──────┘  └──────┬───────┘  └────────────┬───────────┘  │
│         │                │                        │              │
└─────────┼────────────────┼────────────────────────┼──────────────┘
          │                │                        │
          ▼                ▼                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                     BACKEND (Render — FastAPI)                   │
│                                                                  │
│  ┌──────────┐ ┌────────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ api/     │ │ api/       │ │ api/     │ │ api/             │  │
│  │ auth.py  │ │contacts.py │ │calls.py  │ │eml.py            │  │
│  │          │ │(batch,CRUD)│ │(inline   │ │(process,push,    │  │
│  │          │ │            │ │ CRUD)    │ │ export)          │  │
│  └────┬─────┘ └─────┬──────┘ └────┬─────┘ └───────┬──────────┘  │
│       │              │             │               │             │
│  ┌────▼──────────────▼─────────────▼───┐   ┌──────▼──────────┐  │
│  │         inlined DB queries           │   │  LLM Providers  │  │
│  │         (api/auth.py, api/history.py)│   │  via llm_router │  │
│  └────────────────┬────────────────────┘   │  Groq, OpenAI,  │  │
│                   │                         │  OpenRouter,    │  │
│  ┌────────────────▼────────────────────┐   │  DeepSeek,      │  │
│  │   db/ (Async SQLAlchemy + models)   │   │  Anthropic,     │  │
│  │   SQLite (dev) / PostgreSQL (prod)  │   │  Gemini         │  │
│  └─────────────────────────────────────┘   └─────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  services/                                                │   │
│  │  parser.py (XLS: xlrd, PDF: PyMuPDF)                     │   │
│  │  pdf_exporter.py (ReportLab PDF generation)               │   │
│  │  llm_router.py · eml_processor.py · eml_store.py          │   │
│  │  eml_dedup_rules.py                                       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────┐
│  SUPABASE                        │
│  ┌───────────┐ ┌──────────────┐  │
│  │ Auth      │ │ PostgreSQL   │  │
│  │ (JWT)     │ │ (via pgpool) │  │
│  └───────────┘ └──────────────┘  │
│  CRM Project:                    │
│    omqlplhfkriwjubjafgr          │
│  EML Project (separate):        │
│    ewlcrbkfwwaunpdanbcv          │
└─────────────────────────────────┘
```

---

## 4. Backend — Detailed Breakdown

### 4.1 Entry Point (`main.py`)

**File:** `main.py` (128 lines)

- **Framework:** FastAPI v0.111.0 with uvicorn
- **Lifespan:** `asynccontextmanager` that calls `init_db()` with a 10-second timeout on startup
- **Middleware:**
  - CORS: explicit allow-list from `ALLOWED_ORIGINS` env, merged with hardcoded defaults (both Vercel domains + localhost dev ports). Env can only ADD origins; defaults are always allowed. `allow_credentials=False`
  - Rate limiting: slowapi `Limiter` by IP address
- **Global exception handler:** Catches all unhandled exceptions, ensures CORS headers are sent (for allowed origins) even on 500 errors
- **Routers (all prefixed `/api`):** Every router is mounted with `Depends(verify_token)` at the router level — **all `/api/*` routes require a valid Supabase JWT**, except `/api/auth/upsert` which carries its own `verify_token` dependency. `/health` is defined directly on the app and stays public.
  - `parse_router` — File parsing
  - `pdf_router` — PDF export
  - `contacts_router` — Contact CRUD + batch import
  - `calls_router` — Call log CRUD
  - `auth_router` — User auth upsert (own verify_token)
  - `history_router` — Upload session history
  - `sig_router` — Legacy email signature AI extraction
  - `eml_new_router` — EML contact intelligence API
- **Static files:** `frontend/` directory served at `/` with `html=True`
- **Health check:** `GET /health` returns `{"status": "ok"}`

### 4.2 Database Layer (`db/`)

**File:** `db/database.py` (64 lines)

- **Engine:** Async SQLAlchemy
  - **SQLite (dev):** `sqlite+aiosqlite:///./crm.db`, `check_same_thread=False`
  - **PostgreSQL (prod):** `postgresql+asyncpg://...`, with:
    - `pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`, `pool_recycle=300`
    - `statement_cache_size=0` (required for pgBouncer/Supabase connection pooling)
    - SSL with `check_hostname=False`, `verify_mode=CERT_NONE` (Supabase self-signed certs)
- **URL Transformation:** Auto-converts `postgres://` or `postgresql://` to `postgresql+asyncpg://`; strips query params (`?pgbouncer=true`) for PostgreSQL
- **Session:** `async_sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False)`
- **`get_db()`:** FastAPI dependency yielding an `AsyncSession`
- **`init_db()`:** Creates all tables + runs migration: `ALTER TABLE contacts ADD COLUMN files TEXT` (swallows error if column exists)

### 4.3 Models & Schema (`db/models.py`)

**File:** `db/models.py` (113 lines)

6 SQLAlchemy ORM models:

| Model | Table | Key Columns | Relationships |
|-------|-------|-------------|---------------|
| **User** | `users` | `id` (PK), `email` (unique, indexed), `name`, `provider_uid` (indexed, Supabase UID), `last_login`, `created_at` | → `sessions` (one-to-many SessionData) |
| **Company** | `companies` | `id` (PK), `name` (indexed), `address`, `city` (indexed), `pincode`, `website`, `industry`, `product`, `created_at`, `updated_at` | → `contacts`, `call_logs` |
| **Contact** | `contacts` | `id` (PK), `company_id` (FK), `name`, `email_primary` (indexed), `email_secondary`, `phone_primary` (indexed), `phone_secondary`, `phone_country` (default "IN"), `whatsapp`, `position`, `files` (Text), `created_at`, `updated_at` | → `company`, `call_logs` |
| **CallLog** | `call_logs` | `id` (PK), `contact_id` (FK), `company_id` (FK), `call_date`, `duration_minutes`, `call_type` (Incoming/Outgoing/Follow-up), `outcome` (Connected/Voicemail/No Answer/Callback Scheduled), `notes`, `next_action`, `next_action_date`, `created_by`, `created_at` | → `contact`, `company` |
| **SessionData** | `session_data` | `id` (PK), `file_name`, `sheet_name`, `upload_date`, `mapping` (JSON), `is_active` (Boolean), `user_id` (FK, nullable), `total_records`, `imported`, `skipped` | → `user`, `records` |
| **Record** | `records` | `id` (PK), `session_id` (FK), `data` (JSON), `created_at` | → `session` |

**ER Relationships:**
```
User 1──* SessionData 1──* Record
Company 1──* Contact 1──* CallLog
Company 1──* CallLog (also directly)
```

### 4.4 Core Utilities (`core/`)

**`core/auth.py`** (25 lines):
- `get_supabase_client()` — Creates Supabase client from `SUPABASE_URL` + `SUPABASE_ANON_KEY`
- `verify_token(credentials)` — FastAPI `Security` dependency using `HTTPBearer`. Calls `supabase.auth.get_user(token)` to validate JWT. Returns user on success, raises HTTP 401 on failure.

**`core/rate_limit.py`** (4 lines):
- `limiter = Limiter(key_func=get_remote_address)` — IP-based rate limiting via slowapi

### 4.5 CRUD Operations

The old `crud/` package was inlined into its only callers: user upsert lives in `api/auth.py`, and session/contact/call-log queries live as private `_`-prefixed helpers in `api/history.py` (`_list_sessions`, `_get_session`, `_get_session_records`, `_delete_session`, `_get_all_session_records`, `_find_contacts_by_emails`, `_find_contacts_by_phones`, `_get_call_logs_for_contacts`, `_rows_with_contact`).

### 4.6 API Routes (`api/`)

All routes below (except `/api/auth/upsert`, which carries its own dependency) inherit JWT auth from the router-level `Depends(verify_token)` applied in `main.py`.

#### `api/auth.py` (36 lines)
- **`POST /api/auth/upsert`** — Protected by `verify_token` (route-level). Upserts the user inline, returns `{ok, user_id, email}`.

#### `api/parse.py` (45 lines)
- **`POST /api/parse`** — Accepts file upload (max 30MB). Routes `.xls` → `parse_xls()`, `.pdf` → `parse_pdf()`. Returns `{ok, sheet, headers, rows, rowCount}`. Note: `.xlsx` is NOT handled here (parsed client-side via XLSX.js).

#### `api/contacts.py` (409 lines) — **LARGEST ROUTE FILE**

Constants:
- `INDIAN_MOBILE_RE` — `^(\+91[\s\-]?)?[6-9]\d{9}$`
- `INTL_PHONE_RE` — `^\+(?!91)\d{1,3}[\s\-]?\d{5,14}$`
- `EMAIL_RE` — `^[\w.+%-]+@[\w.-]+\.[a-z]{2,}$`

Routes:
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/contacts/batch` | **Major endpoint.** Batch import: resolves user, creates SessionData, pre-fetches existing contacts (chunked), O(1) duplicate check via hash maps, validates email/phone, classifies phone country, finds/creates Company (cached), creates Contact, archives raw data as Record. Returns `{ok, imported, skipped, flagged_foreign, session_id, contact_ids}` |
| `PUT` | `/api/contacts/{id}` | Updates contact fields with validation (body: `ContactIn`); updates or creates company |
| `DELETE` | `/api/contacts/{id}` | Deletes single contact |
| `DELETE` | `/api/contacts` | Bulk delete (query param `ids`, chunked 5000) |

Read/list/stats endpoints (`GET /api/contacts`, `GET /api/contacts/{id}`, `GET /api/contacts/stats/summary`) were removed - the frontend never called them (Customer Profiles uses `/api/eml/contacts`).

#### `api/calls.py` (143 lines)
Call log CRUD is implemented inline with SQLAlchemy in this file.
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/calls` | Creates call log; verifies contact exists; auto-fills company_id from contact |
| `GET` | `/api/calls/contact/{contact_id}` | Lists call logs for a contact |
| `PUT` | `/api/calls/{log_id}` | Updates call log fields |
| `DELETE` | `/api/calls/{log_id}` | Deletes call log |

#### `api/history.py` (198 lines - includes inlined session/contact query helpers)
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/history` | Lists sessions, optionally filtered by email |
| `GET` | `/api/history/{id}` | Session records (paginated), with `_contact_id` attached for frontend editing |
| `DELETE` | `/api/history/{id}` | Deletes session |
| `GET` | `/api/history/{id}/export` | **Export with call logs merged.** Attaches to each record: `_last_call_date`, `_last_call_type`, `_last_outcome`, `_last_notes`, `_total_calls`, `_next_action`, `_next_action_date`, `_all_call_summary` |

#### `api/export_pdf.py` (42 lines)
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/export/pdf` | Calls `generate_pdf()`, returns PDF bytes with Content-Disposition attachment (filename sanitized against header injection) |

#### `api/eml.py` (476 lines) — active EML contact intelligence API
Multipart/process endpoint uses `services/eml_processor.py` (MIME parse + local extraction), `services/llm_router.py` (single-attempt multi-provider LLM chain), `services/eml_store.py` (EML Supabase persistence), and `services/eml_dedup_rules.py` (dedup). After processing, contacts are auto-pushed (merge-or-create) into the main CRM database.

| Method | Path | Rate Limit | Purpose |
|--------|------|------------|---------|
| `POST` | `/api/eml/process` | **30/min** | Accepts `.eml` file uploads + LLM chain JSON; parses each file, extracts contacts (local regex + LLM), dedups against EML store, inserts into `eml_emails`/`eml_contacts`, auto-pushes NEW/merged contacts into CRM. 45s total LLM budget (`EML_PROCESS_BUDGET` env). Returns `{ok, results, counts}` |
| `GET` | `/api/eml/contacts` | — | Paginated staged contacts with search/status/pushed filters |
| `GET` | `/api/eml/emails` | — | Paginated raw email records |
| `GET` | `/api/eml/emails/{email_id}` | — | Single email with nested contacts |
| `GET` | `/api/eml/contacts/export` | — | Streaming CSV export of staged contacts |
| `POST` | `/api/eml/contacts/{contact_id}/push` | — | Manually push one staged contact to CRM (409 if already pushed) |
| `POST` | `/api/eml/contacts/push-bulk` | — | Bulk push selected staged contacts to CRM |

### 4.7 Services (`services/`)

**`services/parser.py`** (302 lines):
- **`parse_xls(content)`** — Parses ALL valid sheets in XLS. Skips lookup/index sheets (patterns: "mob no", "email id", "phone list", "mobile list", "index", "lookup"). Uses `xlrd`. (`.xlsx` is parsed client-side via XLSX.js.)
- **`parse_pdf(content)`** — 2-tier fallback: (1) PyMuPDF table extraction via `page.find_tables()`, (2) `_extract_contacts_from_text()` for free-form text
- **`_extract_contacts_from_text(text)`** — Contact extraction using block-based parsing + regex (Indian phone, email, URL, pincode)
- **`_extract_fields_from_block(block)`** — Extracts Name, Company, Phone, Email, Website, Pincode, Address using regex for company keywords (ltd, pvt, inc) and Indian address keywords (road, nagar, GIDC)
- **`_dedupe_headers(headers)`** — Deduplicates column names by appending `_1`, `_2` suffixes
- **Config:** `PARSER_TIMEOUT` (env, default 15s XLS / 30s PDF), `PDF_MAX_PAGES` (env, default 200)

**`services/pdf_exporter.py`** (210 lines):
- **`generate_pdf(payload)`** — Builds A4 PDF with ReportLab:
  - Cover section (navy background, title, source info, timestamp)
  - KPI dashboard (Total Records, Fields Mapped, Data Quality %, With Email, With Phone)
  - Data Quality Report (color-coded progress bars: green >75%, amber >40%, rose ≤40%)
  - CRM Data table (first 8 columns, styled headers, alternating rows)
  - Footer with branding

**`services/llm_router.py`** (145 lines):
- **`extract_json(chain, user_prompt, deadline)`** — Ordered failover across the user-configured provider chain; returns parsed JSON dict or `None`
- **Retry policy:** intentionally **1 attempt per provider** (retries blew the Cloudflare ~100s proxy deadline budget; locked by `test_failing_provider_called_exactly_once`)
- **Wall-clock deadline:** optional `deadline` (monotonic) stops the chain early so `/eml/process` stays under the proxy timeout
- **Cache:** capped 500-entry dict (FIFO), keyed by MD5 of `{provider}|{model}|{prompt}`
- **Providers:** OpenRouter, Groq, OpenAI, DeepSeek, Anthropic, Gemini (Gemini URL built per-call)
- **`parse_llm_json(raw)`** — Strips markdown fences, JSON-decodes, extracts first `{...}` block as fallback

**`services/eml_processor.py`** (282 lines):
- **`parse_eml_bytes(raw, file_name)`** — MIME parse via Python `email` module (policy=default); decodes parts, extracts headers (From/To/CC/BCC/Subject/Date), body text, signature block
- **`extract_local_fields(parsed)`** — Regex-based local extraction (name, email, phones, company, designation, address, city, pincode, website) without any LLM call
- **`build_llm_prompt(parsed)`** — Builds the untrusted-content-wrapped prompt for the LLM
- **`merge_fields(local, ai)`** — Field-wise merge: AI values fill gaps left by local extraction

**`services/eml_store.py`** (89 lines):
- Thin sync-client wrappers (Supabase Python SDK) over the separate EML Supabase project: `fetch_dedup_keys()`, `insert_email()`, `insert_contact()`, `get_contact()`, `get_email()`, `list_contacts()`, `list_emails()`, `mark_pushed()`
- Search strings are sanitized before PostgREST `or_()` filter construction
- Uses `EML_SUPABASE_URL`/`EML_SUPABASE_ANON_KEY` env (falls back to `SUPABASE_URL`/`SUPABASE_ANON_KEY`)

**`services/eml_dedup_rules.py`** (34 lines):
- **`normalize_email/phone/name`** — Lowercase/strip, digits-only, whitespace-collapsed
- **`is_duplicate(email, phone, existing_emails, existing_phones, ...)`** — Returns reason string (`"email"`, `"phone"`, `"name"`) or `None`; phone match handles `+91` prefix variance via substring containment

---

## 5. Frontend — Detailed Breakdown

### 5.1 Pages & HTML Structure

#### `signin.html` (605 lines)
- Self-contained page with inline CSS (~290 lines)
- Split layout: Left brand panel + Right auth form
- Sign In form (email/password) + Sign Up form (name/email/password)
- Supabase Auth SDK: `signInWithPassword()`, `signUp()`
- After successful auth: calls `POST /api/auth/upsert` to sync user to backend, stores session in `localStorage('crm-session')`, redirects to `index.html`
- Visual effects: parallax blob, 3D glass tilt, input focus animations

#### `index.html` (440 lines)
- **Auth Guard:** Inline script checks `localStorage('crm-session')` + Supabase token → redirects to `signin.html` if missing
- **CSP Headers:** `connect-src` allows Supabase, the Render backend, OpenRouter, Groq, OpenAI
- **External libs:** Plus Jakarta Sans + Inter + Outfit + DM Sans + JetBrains Mono fonts, XLSX.js, Chart.js, JSZip, Supabase CDN
- Loads `app.js` then `eml.js` (EML UI module)

**Layout:**
- 3 ambient background blur orbs
- **Sidebar** (fixed, 260px / 76px collapsed):
  - Logo "CRM Engine v4.0"
  - Nav: Import File, Dashboard, Analytics, Data Table, Data Quality, Deduplication, History, EML Upload, Customer Profiles, Staged Contacts, EML Emails, LLM Settings
  - Export: Save to CRM, Export Excel, PDF, VCF, ZIP
  - File info card, User info with avatar, Sign Out
- **Main content area** with topbar (hamburger, title, action buttons, 4-theme picker)

**SPA Views** (one active at a time):
| View ID | Purpose |
|---------|---------|
| `view-upload` | Drop zone for spreadsheet files (`.xlsx,.xls,.csv,.txt,.pdf` multiple), feature info cards |
| `view-mapping` | Field detection/mapping table: column → type dropdown, confidence %, include checkbox |
| `view-processing` | Loading animation with progress bar and step indicators |
| `view-dashboard` | KPI grid, insight grid, 2 chart rows |
| `view-analytics` | Tab pills (Geographic, Segments, Reachability, Top Records, Distribution) |
| `view-table` | Search, column/value filters, page size, data table with pagination + Edit/Delete/View actions |
| `view-quality` | Quality score, field-by-field fill rates, email/phone validation breakdown |
| `view-dedup` | Duplicate group cards with Keep First / Remove All actions |
| `view-eml-upload` | EML file drop zone (eml.js) — server-side process + AI chain |
| `view-customer-profiles` | Unified contact profile card grid (searchable, paginated) |
| `view-eml-contacts` | Staged EML contacts table with search/status/pushed filters + bulk push |
| `view-eml-emails` | Stored raw email browser with detail view |
| `view-eml-settings` | LLM provider chain configuration (eml.js, `localStorage('EML_LLM_CHAIN')`) |
| `view-history` | Upload history list with Reload/Export/Delete |

**Modals & Panels:**
- **Edit Modal** — Dynamic form for editing contact fields
- **Contact Detail Panel** — Slide-out panel with contact info + call log form + call history

### 5.2 Application State (`app.js`)

**Global constants:**
- `API_BASE` — From `window.CRM_API_BASE`
- `crmClient` — Supabase client instance

**Main state object `S`:**
```javascript
{
  rawData: [],      // Raw parsed rows
  headers: [],      // Column headers
  mapping: {},      // Column → {type, confidence, include}
  clean: [],        // Processed/validated rows
  fileName: '',
  sheetName: '',
  filtered: [],     // Currently filtered/displayed rows
  page: 1,
  pageSize: 50,
  sortCol: null,
  sortDir: 1,
  charts: [],       // Chart.js instances
  currentView: 'upload',
  dupGroups: [],    // Duplicate groups
  validation: {     // Validation stats
    dropped: 0, invalidEmails: 0,
    landlines: 0, foreign: 0, total: 0
  },
  dbContacts: [],   // contacts loaded from backend
  sessionId: null,
  userEmail: null
}
```

**Field Types (`FT`):** 25 types — company, contact, phone, email, address, city, pincode, website, product, industry, amount, date, status, id, keyword, location, facebook, member, fax, whatsapp, files, stdcode, landline, other, skip

**LLM chain state** lives in `eml.js` under `localStorage('EML_LLM_CHAIN')` — an ordered array of `{provider, model, api_key}` entries (default provider: Gemini). OpenRouter model list is fetched dynamically from its public `/api/v1/models` endpoint.

### 5.3 Complete Function Reference

#### `app.js` — Auth & Session
| Function | Purpose |
|----------|---------|
| `getAuthToken()` | Gets Supabase JWT access token |
| `apiHeaders()` | Builds headers with `Authorization: Bearer` |
| `apiUploadHeaders()` | Headers for FormData (no Content-Type) |
| `syncAuthSession()` | Validates session, syncs user to backend via `POST /api/auth/upsert` |
| `signOut()` | Signs out of Supabase, clears localStorage |

#### `app.js` — Theme & UI
| Function | Purpose |
|----------|---------|
| `isDarkTheme()` | Returns true for dark/ocean/sunset themes |
| `setTheme(name)` | Sets `data-theme`, updates picker, re-renders charts |
| `toggleSidebar()` | Mobile sidebar open/close |
| `toggleSidebarCollapse()` | Desktop sidebar collapse, persists to localStorage |
| `showView(id)` | SPA view switching with data guard; delegates EML views to `EmlUI`/`AppUI` |

#### `app.js` — File Handling
| Function | API Call | Purpose |
|----------|----------|---------|
| `getValidSheets(wb)` | — | Filters workbook sheets (skips index/lookup) |
| `detectField(col, samples)` | — | Auto-detects column type (25 types, confidence %) |
| `handleFile(file)` | — | Routes by extension: .txt → phone list, .csv → parse, .xlsx → XLSX.js, .xls/.pdf → backend |
| `handleMultipleFiles(fileList)` | `POST /api/parse` | Merges multiple files |
| `readFileAsArrayBuffer(file)` | — | Promise-based reader |
| `readFileAsText(file)` | — | Promise-based reader |
| `handleViaBackend(file, ext)` | `POST /api/parse` | Server-side parsing for .xls/.pdf |
| `mergeUnnamedCols(keys, data)` | — | Merges adjacent unnamed Excel columns |

#### `app.js` — Data Processing
| Function | Purpose |
|----------|---------|
| `buildMapping()` | Builds mapping UI with confidence, fill rate, sample data |
| `startProcessing()` | Animated progress → processData → findDuplicates → buildAllViews |
| `processData()` | Cleans data: email validation, phone classification (Indian/international/landline), title casing, URL normalization, mandatory rule enforcement (email OR phone required) |
| `normalizeToStandardFields()` | Maps ANY column structure to 15 standard CRM fields |
| `findDuplicates()` | Full-row fingerprint-based exact match grouping |

#### `app.js` — Validation
| Function | Purpose |
|----------|---------|
| `isValidEmail(v)` | Strict email regex validation |
| `escapeHTML(str)` | XSS prevention |
| `classifyPhone(v)` | Indian mobile / international / landline / invalid |

#### `app.js` — Dashboard & Analytics
| Function | Purpose |
|----------|---------|
| `buildAllViews()` | Calls all build* functions |
| `buildDashboard()` | KPIs + Insights + Charts |
| `buildKPIs()` | Total Records, Fields, Completeness, Email/Phone/Web coverage, Duplicates |
| `buildInsights()` | Contactable records, Missing details, Product coverage, Online presence, Top location |
| `buildMainCharts()` | Bar/donut charts: city distribution, industry, reachability, website presence |
| `buildAnalytics()` | Tab pills (Geographic, Segments, Reachability, Top Records, Distribution) |
| `renderGeoTab/SegTab/ReachTab/TopTab/DistTab(c)` | Individual analytics tab renderers |
| `buildQuality()` | Quality score, fill rates, email/phone breakdown |
| `buildDedup()` | Duplicate group cards |
| `keepFirst(gi)` / `removeAllDupes()` | Deduplication actions |

#### `app.js` — Data Table
| Function | Purpose |
|----------|---------|
| `buildTableControls()` | Column filter dropdown |
| `onColFilterChange()` | Value filter population |
| `filterTable()` | Search + column/value filtering |
| `renderTable()` | Table with type-aware formatting (email links, phone badges, etc.) + action buttons |
| `sortTable(i)` | Column sort toggle |
| `renderPag(total)` / `goPage(p)` | Pagination |

#### `app.js` — Charts
| Function | Purpose |
|----------|---------|
| `addBarChart(parent, title, labels, data, ...)` | Chart.js bar chart with theme colors |
| `addDonutChart(parent, title, labels, data, ...)` | Chart.js doughnut with center total |
| `killCharts()` | Destroys all chart instances |

#### `app.js` — Export
| Function | API Call | Purpose |
|----------|----------|---------|
| `downloadPDF()` | `POST /api/export/pdf` | Backend PDF with fallback to browser print |
| `_printPDFFallback()` | — | Generates HTML report + print dialog |
| `downloadExcel()` | — | Client-side XLSX export with auto-width |
| `downloadVCF()` | — | vCard 3.0 generation |
| `downloadZip()` | `POST /api/export/pdf` | ZIP with Excel + VCF + PDF |

#### `app.js` — CRM CRUD
| Function | API Call | Purpose |
|----------|----------|---------|
| `saveToCRM()` | `POST /api/contacts/batch` | Batch save all contacts |
| `loadHistory()` | `GET /api/history` | Load upload history |
| `reloadSession(id)` | `GET /api/history/{id}` | Reload saved session |
| `deleteSession(id)` | `DELETE /api/history/{id}` | Delete session |
| `exportSessionWithCalls(id)` | `GET /api/history/{id}/export` | Export with call logs as Excel |
| `editRow(idx)` | — | Opens edit modal |
| `saveEdit()` | `PUT /api/contacts/{id}` | Saves edits with validation |
| `deleteRow(idx)` | `DELETE /api/contacts/{id}` | Deletes contact |
| `showContactPanel(idx)` | `GET /api/calls/contact/{id}` | Opens contact panel with call logs |
| `addCallLogFromPanel()` | `POST /api/calls` | Adds call log |

#### `app.js` — Customer Profiles
| Function | API Call | Purpose |
|----------|----------|---------|
| `AppUI.loadCustomerProfiles(page)` | `GET /api/eml/contacts` | Renders paginated profile card grid (exported as `window.AppUI`) |

#### `eml.js` — EML UI Module (exported as `window.EmlUI`)
| Function | API Call | Purpose |
|----------|----------|---------|
| `processFiles(fileList)` | `POST /api/eml/process` | Uploads .eml files + chain, renders progress/results |
| `loadContacts(page)` / `renderContacts()` | `GET /api/eml/contacts` | Staged contacts table with filters |
| `loadEmails(page)` / `renderEmails()` | `GET /api/eml/emails` | Raw email browser |
| `openEmail(id)` | `GET /api/eml/emails/{id}` | Email detail with nested contacts |
| `exportExcel()` / `exportCsv()` | `GET /api/eml/contacts/export` (CSV) | Export staged contacts |
| `pushSelected()` | `POST /api/eml/contacts/push-bulk` | Bulk push to CRM |
| `renderChain()` / `addChainItem()` / `removeChainItem()` / `moveChain()` / `onProviderChange()` / `saveChain()` | — | LLM chain editor (localStorage `EML_LLM_CHAIN`) |
| `prewarmBackend()` | `GET /health` | Pings backend to wake Render before uploads |
| `fetchRetry(url, opts)` | — | Fetch with escalating retry delays (3s→90s) for cold Render instances |

### 5.4 Styling & Theming

**`style.css`** (2,056 lines, ~80KB):
- **4-theme system:** `nexus-light` (default), `nexus-dark`, `ocean`, `sunset`
- **65+ CSS custom properties** covering: sidebar, backgrounds, surfaces, borders, text, accent colors, typography, radius, shadows, transitions
- **Fonts:** Plus Jakarta Sans (display), Inter/DM Sans (body), JetBrains Mono (monospace)
- **Sidebar:** Fixed 260px (76px collapsed), dark background, active state nav items
- **Ambient orbs:** Fixed positioned blurred circles for glassmorphism
- **Base reset** with smooth transitions between themes

### 5.5 Legacy v3 System

`crm_system_v3.html` / `crm_theme.css` have been **removed** from the repo. All UI lives in `index.html` + `app.js` + `eml.js`.

---

## 6. API Endpoint Reference

Every `/api/*` route requires a valid Supabase JWT (router-level `Depends(verify_token)` in `main.py`, or route-level for `/api/auth/upsert`). Only `/health` is public.

| Method | Path | Rate Limit | Handler | Purpose |
|--------|------|------------|---------|---------|
| `GET` | `/health` | No | `main.py` | Health check (public) |
| `POST` | `/api/auth/upsert` | No | `api/auth.py` | Create/update user |
| `POST` | `/api/parse` | No | `api/parse.py` | Parse uploaded file (XLS/PDF) |
| `POST` | `/api/contacts/batch` | No | `api/contacts.py` | Batch import contacts |
| `PUT` | `/api/contacts/{id}` | No | `api/contacts.py` | Update contact |
| `DELETE` | `/api/contacts/{id}` | No | `api/contacts.py` | Delete contact |
| `DELETE` | `/api/contacts` | No | `api/contacts.py` | Bulk delete contacts |
| `POST` | `/api/calls` | No | `api/calls.py` | Create call log |
| `GET` | `/api/calls/contact/{id}` | No | `api/calls.py` | List call logs for contact |
| `PUT` | `/api/calls/{id}` | No | `api/calls.py` | Update call log |
| `DELETE` | `/api/calls/{id}` | No | `api/calls.py` | Delete call log |
| `GET` | `/api/history` | No | `api/history.py` | List upload sessions |
| `GET` | `/api/history/{id}` | No | `api/history.py` | Get session records |
| `DELETE` | `/api/history/{id}` | No | `api/history.py` | Delete session |
| `GET` | `/api/history/{id}/export` | No | `api/history.py` | Export session with call logs |
| `POST` | `/api/export/pdf` | No | `api/export_pdf.py` | Generate PDF report |
| `POST` | `/api/eml/process` | **30/min** | `api/eml.py` | Process .eml uploads (parse + LLM + dedup + auto-push to CRM) |
| `GET` | `/api/eml/contacts` | No | `api/eml.py` | List staged EML contacts (paginated, filterable) |
| `GET` | `/api/eml/emails` | No | `api/eml.py` | List stored raw emails |
| `GET` | `/api/eml/emails/{id}` | No | `api/eml.py` | Single email with nested contacts |
| `GET` | `/api/eml/contacts/export` | No | `api/eml.py` | CSV export of staged contacts |
| `POST` | `/api/eml/contacts/{id}/push` | No | `api/eml.py` | Push one staged contact to CRM |
| `POST` | `/api/eml/contacts/push-bulk` | No | `api/eml.py` | Bulk push staged contacts to CRM |

---

## 7. Data Flow & Application Lifecycle

### Authentication Flow
```
signin.html → Supabase signInWithPassword() → JWT token
  → POST /api/auth/upsert (sync user to backend DB)
  → localStorage('crm-session') = {email, name, token}
  → Redirect to index.html
```

### File Import Flow
```
User drops file(s) → handleFile() / handleMultipleFiles()
  ├── .xlsx → Client-side XLSX.js parsing (getValidSheets, merge sheets)
  ├── .csv  → Client-side CSV parsing
  ├── .txt  → Client-side phone list parsing
  ├── .xls  → POST /api/parse → services/parser.py → parse_xls()
  ├── .pdf  → POST /api/parse → services/parser.py → parse_pdf()
  └── .eml  → EML Upload view (eml.js) → POST /api/eml/process (separate flow, below)

→ buildMapping() → Auto-detect 25 field types with confidence
→ User confirms mapping
→ startProcessing()
  → processData() → Validate emails, classify phones, normalize fields
  → findDuplicates() → Fingerprint-based exact match
  → buildAllViews() → Dashboard, Analytics, Table, Quality, Dedup
```

### CRM Save Flow
```
saveToCRM() → POST /api/contacts/batch
  → api/contacts.py batch handler:
    1. Resolve user_email → user_id
    2. Create SessionData record
    3. Pre-fetch existing contacts (chunked email/phone queries)
    4. For each contact:
       a. Validate email (regex)
       b. Validate/classify phone (Indian/international)
       c. Enforce: must have email OR phone
       d. Check exact duplicate (email+phone+name+whatsapp+position+company+city+industry)
       e. Find or create Company (cached per batch)
       f. Create Contact record
       g. Archive raw_data as Record
    5. Return {imported, skipped, flagged_foreign, session_id}
```

### EML Processing Flow
```
EML Upload view (eml.js) → processFiles()
  → POST /api/eml/process (multipart files + chain JSON)
    1. Fetch existing dedup keys from EML Supabase (eml_emails/eml_contacts)
    2. For each file (45s total LLM budget, EML_PROCESS_BUDGET env):
       a. services/eml_processor.parse_eml_bytes() — MIME parse + header/body extraction
       b. extract_local_fields() — regex contact extraction (no LLM)
       c. services/llm_router.extract_json() — single-attempt multi-provider LLM chain
       d. merge_fields(local, ai) — field-wise merge
       e. eml_dedup_rules.is_duplicate() — email/phone/name match against store
       f. eml_store.insert_email() / insert_contact() — persist to EML Supabase
       g. _merge_into_crm() — auto-push NEW/merged contacts into CRM DB (batch commit)
    3. Return {ok, results, counts: {new, duplicate, merged, error}}
```

### Export Flow
```
Excel: Client-side XLSX.js → .xlsx download
PDF:   POST /api/export/pdf → ReportLab → PDF bytes → download
       (fallback: client-side HTML → window.print())
VCF:   Client-side vCard 3.0 generation → .vcf download
ZIP:   JSZip(Excel + VCF + PDF from backend) → .zip download
```

---

## 8. External Services & Integrations

| Service | URL | Purpose |
|---------|-----|---------|
| **Supabase (CRM)** | `omqlplhfkriwjubjafgr.supabase.co` | Main CRM: Auth (JWT), PostgreSQL database |
| **Supabase (EML)** | `ewlcrbkfwwaunpdanbcv.supabase.co` | Separate project for EML email data (`eml_emails`, `eml_contacts` tables) |
| **Render** | `crm-developer-dashboard.onrender.com` | Backend API hosting |
| **Vercel** | `crmdevloper.vercel.app` | Frontend static hosting |
| **Groq** | `api.groq.com` | LLM API for email signature extraction |
| **OpenAI** | `api.openai.com` | LLM API (signature extraction) |
| **OpenRouter** | `openrouter.ai` | LLM API aggregator + model listing |
| **DeepSeek** | `api.deepseek.com` | LLM API (signature extraction) |
| **Anthropic** | `api.anthropic.com` | LLM API (signature extraction) |
| **Google Gemini** | `generativelanguage.googleapis.com` | LLM API (signature extraction) |

---

## 9. Environment Variables

| Variable | Used In | Default | Required | Purpose |
|----------|---------|---------|----------|---------|
| `DATABASE_URL` | `db/database.py` | `sqlite+aiosqlite:///./crm.db` | No (has default) | Database connection string |
| `SUPABASE_URL` | `core/auth.py` | `""` | Yes (for auth) | Supabase project URL |
| `SUPABASE_ANON_KEY` | `core/auth.py` | `""` | Yes (for auth) | Supabase anonymous API key |
| `EML_SUPABASE_URL` | `services/eml_store.py` | falls back to `SUPABASE_URL` | No (falls back) | EML Supabase project URL |
| `EML_SUPABASE_ANON_KEY` | `services/eml_store.py` | falls back to `SUPABASE_ANON_KEY` | No (falls back) | EML Supabase anon key |
| `ALLOWED_ORIGINS` | `main.py` | merged with hardcoded defaults | No | Extra CORS origins (comma-separated; env can only ADD to defaults) |
| `PARSER_TIMEOUT` | `services/parser.py` | 15 (XLS) / 30 (PDF) | No | Processing timeout seconds |
| `PDF_MAX_PAGES` | `services/parser.py` | 200 | No | Max PDF pages to process |
| `EML_PROCESS_BUDGET` | `api/eml.py` | 45 | No | Total LLM wall-clock budget (seconds) for `/api/eml/process` |
| `PYTHON_VERSION` | `render.yaml` | 3.11.8 | No | Python version on Render |

**Frontend config (`config.js`):**
| Variable | Value | Purpose |
|----------|-------|---------|
| `window.CRM_API_BASE` | `https://crm-developer-dashboard.onrender.com` | Backend API URL |
| `window.CRM_SUPABASE_URL` | `https://omqlplhfkriwjubjafgr.supabase.co` | CRM Supabase URL |
| `window.CRM_SUPABASE_ANON_KEY` | (JWT) | CRM Supabase anon key (public, RLS-protected) |

> Note: EML Supabase credentials are **server-side only** (render.yaml env vars); the frontend never talks to the EML Supabase project directly.

---

## 10. Deployment Configuration

### Backend (Render) — `render.yaml`
- **Service:** `web` (Python)
- **Name:** `crm-intelligence-api`
- **Build:** `pip install -r requirements.txt`
- **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Python:** 3.11.8
- **Env vars:** `PYTHON_VERSION`, `ALLOWED_ORIGINS`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DATABASE_URL`, `EML_SUPABASE_URL`, `EML_SUPABASE_ANON_KEY` (secret keys use `sync: false`)
- **Keep-alive:** `.github/workflows/keep-alive.yml` pings `/health` every 10 minutes via cron to prevent Render cold starts

### Frontend (Vercel) — `vercel.json`
- **Builder:** `@vercel/static` for `frontend/**`
- **Routes:** `/(.*) → /frontend/$1` with filesystem handle + SPA fallback to `index.html`
- **URL:** `crmdevloper.vercel.app` (note: typo in "devloper"; the corrected `crmdeveloper.vercel.app` is also in the CORS allow-list)

### CORS
- Backend: explicit allow-list — `ALLOWED_ORIGINS` env (comma-separated) **merged with** hardcoded defaults (both Vercel domains + localhost:3000/5173/5500/127.0.0.1:5500/8000). The env var can only ADD origins; defaults are always allowed so a stale env cannot break the live frontend. Unknown origins get no CORS headers (preflight → 400). Covered by `tests/test_cors.py`.

---

## 11. Testing

### Test Infrastructure (`tests/conftest.py`)
- **Auth bypass:** `app.dependency_overrides[verify_token] = _fake_user` — protected routes are testable without real Supabase JWTs
- **In-memory SQLite** (`sqlite+aiosqlite://`) for fast, isolated tests
- **Session-scoped event loop** + engine with all tables created
- **Per-test `db_session`** fixture with rollback after each test

### Test Files (7 files, 54 tests)
| File | Tests | What's Tested |
|------|-------|---------------|
| `tests/conftest.py` | — | Fixtures + `verify_token` dependency override |
| `tests/test_api.py` | 2 | `POST /api/auth/upsert` — create new user, upsert existing user (same email → update name, not duplicate) |
| `tests/test_cors.py` | 4 | CORS preflight contract — allows both Vercel domains + localhost, rejects unknown origins |
| `tests/test_eml_api.py` | 9 | `/api/eml/*` endpoint behavior (process, contacts, push) |
| `tests/test_eml_dedup_rules.py` | 6 | `is_duplicate()` / normalize helpers |
| `tests/test_eml_processor.py` | 9 | MIME parsing, local field extraction, merge |
| `tests/test_llm_router.py` | 10 | Chain failover (single attempt per provider), JSON parsing, caching |
| `tests/test_parser.py` | 7 | `_dedupe_headers()`, `_extract_contacts_from_text()` |

### Running Tests
```bash
python3 -m pytest tests/ -q
```
Last run: **47 passed**.

---

## 12. Key Design Decisions & Caveats

### Architecture
- **Monolith:** Single FastAPI app serves both API and static frontend (mounted at `/`)
- **Async-first:** All CRM database operations use async SQLAlchemy + asyncpg/aiosqlite; EML Supabase access uses the sync Supabase Python SDK (called from async handlers)
- **No ORM migrations:** Uses raw `ALTER TABLE` SQL in `init_db()` for schema evolution
- **Dual database support:** SQLite for local dev, PostgreSQL (Supabase) for production, auto-detected from `DATABASE_URL`

### Security
- ✅ **All `/api/*` routes require JWT auth** — router-level `Depends(verify_token)` in `main.py` for every router; `/api/auth/upsert` carries its own dependency; only `/health` is public
- ✅ **CORS is an explicit allow-list** — `ALLOWED_ORIGINS` env merged with hardcoded defaults (Vercel domains + localhost); unknown origins receive no CORS headers. Locked by `tests/test_cors.py`
- ⚠️ **SSL verification disabled** — `check_hostname=False`, `verify_mode=CERT_NONE` for Supabase PostgreSQL
- ⚠️ **LLM API keys stored client-side** — User-provided keys for AI features are stored in `localStorage('EML_LLM_CHAIN')` (or legacy `CRM_AI_SETTINGS`) and sent to backend per request
- ✅ Supabase anon keys are intentionally public (security via Row Level Security)

### Performance
- **Chunked queries:** All bulk operations (contacts lookup, call logs, bulk delete) use chunked IN queries (2000-5000 per chunk)
- **Company caching:** During batch import, companies are cached per batch to avoid repeated lookups
- **LLM caching:** capped 500-entry dict cache in `services/llm_router.py`
- **Connection pooling:** pgBouncer-compatible settings (statement_cache_size=0, pool_size=5, max_overflow=10)
- **LLM deadline budget:** `/eml/process` enforces a wall-clock deadline (default 45s) so the request finishes under the Cloudflare ~100s proxy timeout; `services/llm_router.py` makes **1 attempt per provider** (deliberate — retries blew the deadline; locked by `test_failing_provider_called_exactly_once`)
- **Render keep-alive:** GitHub Actions cron pings `/health` every 10 min

### Data Processing
- **15 standard CRM fields:** All imported data is normalized to: Company Name, Location, Address, Pincode, Website, Person Name 1/2, Designation, Mobile 1/2, WhatsApp, Email 1/2, Files, Products/Misc
- **Phone classification:** Indian mobile (`6-9XXXXXXXXX`), international (`+CC...`), landline, invalid
- **Duplicate detection:** Full-row fingerprint from email + phone + name + whatsapp + position + company + city + industry; EML pipeline adds email/phone/name matching via `eml_dedup_rules.py`
- **File parsing:** .xlsx and .csv are parsed client-side (XLSX.js); .xls and .pdf are sent to backend (xlrd, PyMuPDF); .eml is uploaded to `/api/eml/process` (server-side MIME parse + LLM)

### Frontend
- **Pure vanilla JS SPA** — No framework (React, Vue, etc.). Core logic in `app.js` (2,160 lines) + EML UI module in `eml.js` (433 lines)
- **4-theme system** — nexus-light, nexus-dark, ocean, sunset with 65+ CSS custom properties
- **Chart.js** for all visualizations
- **XLSX.js** for client-side Excel parsing/generation
- **JSZip** for ZIP archive creation
- **CRM Supabase client only in the browser** — EML Supabase is accessed exclusively server-side via `services/eml_store.py`

### Known Limitations
- `.xlsx` files cannot be parsed server-side (only client-side via XLSX.js)
- PDF parsing has a 3-tier fallback but may not extract all contact data from complex layouts
- `/api/eml/process` processes files serially within the 45s LLM budget; large batches may partially complete (per-file results still returned)
- No WebSocket/real-time updates — all data is fetched on demand
- Session history filters show both user's sessions AND orphan sessions (no user association)
- `GET /api/calls/contact/{id}` lacks an explicit route-level `Depends(verify_token)` but is still protected by the router-level dependency in `main.py`

---

## Python Dependencies

From `requirements.txt`:

```
fastapi==0.111.0              # Web framework
uvicorn[standard]==0.29.0     # ASGI server
python-multipart==0.0.9       # File upload handling
xlrd==2.0.1                   # .xls file parsing
reportlab==4.1.0              # PDF report generation
python-dotenv==1.0.1          # .env file loading
httpx==0.27.0                 # Async HTTP client (LLM API calls)
sqlalchemy[asyncio]>=2.0.30   # ORM (async extras)
supabase==2.4.5               # Supabase Python client (auth + EML store)
slowapi==0.1.9                # Rate limiting
asyncpg>=0.29.0               # PostgreSQL async driver
aiosqlite                     # SQLite async driver
PyMuPDF                       # PDF parsing (via fitz)
```

---

## Frontend Libraries (CDN)

- **XLSX.js** (`xlsx.full.min.js`) — Excel parsing/generation
- **Chart.js** — Data visualization
- **JSZip** — ZIP archive creation
- **Supabase JS SDK** (`@supabase/supabase-js@2`) — Auth & database client
- **Google Fonts** — Plus Jakarta Sans, Inter, Outfit, DM Sans, JetBrains Mono
