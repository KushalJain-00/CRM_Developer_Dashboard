# CRM Developer Dashboard — Full Project Context

> **Last Updated:** 2026-07-12
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
   - [CRUD Operations (crud/)](#45-crud-operations-crud)
   - [API Routes (api/)](#46-api-routes-api)
   - [Services (services/)](#47-services-services)
5. [Frontend — Detailed Breakdown](#5-frontend--detailed-breakdown)
   - [Pages & HTML Structure](#51-pages--html-structure)
   - [Application State (app.js)](#52-application-state-appjs)
   - [Complete Function Reference (app.js)](#53-complete-function-reference-appjs)
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
- **AI Email Signature Extraction** — Multi-provider LLM chain (Groq, OpenAI, OpenRouter, DeepSeek, Anthropic, Gemini) with fallback and retry logic
- **Bulk EML Processing** — Batch process 100-200 .eml files with parallel AI extraction
- **Export** — Excel (XLSX.js client-side), PDF (ReportLab server-side), VCF (vCard 3.0), ZIP archive
- **Session History** — Reload, export (with call logs merged), and delete past uploads
- **Authentication** — Supabase Auth (email/password) with JWT token verification

---

## 2. Directory Structure

```
CRM_Developer/
├── main.py                     # FastAPI app entry point
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (secrets, git-ignored)
├── .gitignore                  # Git ignore rules
├── crm.db                      # Local SQLite database (dev only, git-ignored)
├── render.yaml                 # Render.com deployment config
├── vercel.json                 # Vercel deployment config (frontend)
│
├── api/                        # FastAPI route handlers
│   ├── __init__.py
│   ├── auth.py                 # POST /api/auth/upsert
│   ├── calls.py                # CRUD for call logs
│   ├── contacts.py             # Batch import, CRUD, stats (LARGEST ROUTE FILE — 545 lines)
│   ├── export_pdf.py           # PDF export endpoint
│   ├── history.py              # Upload session history + export with call logs
│   ├── parse.py                # File upload & parsing (.xls, .pdf)
│   └── parse_signature.py      # AI-powered email signature extraction (multi-LLM)
│
├── core/                       # Shared utilities
│   ├── __init__.py
│   ├── auth.py                 # Supabase JWT verification (verify_token dependency)
│   └── rate_limit.py           # slowapi rate limiter
│
├── crud/                       # Database CRUD operations
│   ├── __init__.py
│   ├── auth.py                 # User upsert (create or update)
│   ├── calls.py                # CallLog CRUD
│   └── history.py              # Session/Record queries + contact lookup helpers
│
├── db/                         # Database configuration & models
│   ├── __init__.py
│   ├── database.py             # Async SQLAlchemy engine, session factory, init_db()
│   └── models.py               # 6 ORM models: User, Company, Contact, CallLog, SessionData, Record
│
├── services/                   # Business logic services
│   ├── __init__.py
│   ├── parser.py               # XLS/PDF parsing with multi-strategy extraction
│   └── pdf_exporter.py         # ReportLab PDF report generation
│
├── frontend/                   # Static SPA frontend (served by FastAPI)
│   ├── index.html              # Main app page (425 lines)
│   ├── signin.html             # Authentication page (600 lines)
│   ├── app.js                  # All application JS logic (3,589 lines, 177KB)
│   ├── config.js               # API URLs & Supabase keys
│   ├── style.css               # Main stylesheet with 4-theme system (1,914 lines)
│   ├── crm_system_v3.html      # Legacy v3 (self-contained, no backend)
│   └── crm_theme.css           # Legacy v3 theme CSS
│
├── tests/                      # Pytest test suite
│   ├── conftest.py             # Fixtures (in-memory SQLite, async session)
│   ├── test_api.py             # User upsert CRUD tests
│   └── test_parser.py          # Parser helper function tests
│
├── test_batch.py               # Manual integration test (Render CORS check)
├── test_engine.py              # Diagnostic script (asyncpg engine creation)
└── eml examples/               # Sample .eml files for testing
```

---

## 3. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Vercel)                         │
│  signin.html ──► index.html + app.js (SPA)                      │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ Supabase    │  │ Client-side  │  │ Views: Upload, Map,    │  │
│  │ Auth SDK    │  │ XLSX/CSV/EML │  │ Dashboard, Analytics,  │  │
│  │             │  │ Parsing      │  │ Table, Quality, Dedup, │  │
│  │             │  │              │  │ History, EML, Bulk EML │  │
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
│  │ auth.py  │ │contacts.py │ │calls.py  │ │parse_signature.py│  │
│  │          │ │(batch,CRUD)│ │(CRUD)    │ │(multi-LLM chain) │  │
│  └────┬─────┘ └─────┬──────┘ └────┬─────┘ └───────┬──────────┘  │
│       │              │             │               │             │
│  ┌────▼──────────────▼─────────────▼───┐   ┌──────▼──────────┐  │
│  │         crud/ (DB operations)       │   │  LLM Providers  │  │
│  │  auth.py │ calls.py │ history.py    │   │  Groq, OpenAI,  │  │
│  └────────────────┬────────────────────┘   │  OpenRouter,    │  │
│                   │                         │  DeepSeek,      │  │
│  ┌────────────────▼────────────────────┐   │  Anthropic,     │  │
│  │   db/ (Async SQLAlchemy + models)   │   │  Gemini         │  │
│  │   SQLite (dev) / PostgreSQL (prod)  │   └─────────────────┘  │
│  └─────────────────────────────────────┘                        │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  services/                                                │   │
│  │  parser.py (XLS: xlrd/openpyxl, PDF: PyMuPDF)            │   │
│  │  pdf_exporter.py (ReportLab PDF generation)               │   │
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

**File:** `main.py` (101 lines)

- **Framework:** FastAPI v0.111.0 with uvicorn
- **Lifespan:** `asynccontextmanager` that calls `init_db()` with a 10-second timeout on startup
- **Middleware:**
  - CORS: `allow_origins=["*"]`, `allow_credentials=False`
  - Rate limiting: slowapi `Limiter` by IP address
- **Global exception handler:** Catches all unhandled exceptions, ensures CORS headers are sent even on 500 errors
- **Routers (all prefixed `/api`):**
  - `parse_router` — File parsing
  - `pdf_router` — PDF export
  - `contacts_router` — Contact CRUD + batch import
  - `calls_router` — Call log CRUD
  - `auth_router` — User auth upsert
  - `history_router` — Upload session history
  - `sig_router` — Email signature AI extraction
- **Static files:** `frontend/` directory served at `/` with `html=True`
- **Health check:** `GET /health` returns `{"status": "ok"}`

### 4.2 Database Layer (`db/`)

**File:** `db/database.py` (66 lines)

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

**File:** `db/models.py` (114 lines)

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

**`core/auth.py`** (26 lines):
- `get_supabase_client()` — Creates Supabase client from `SUPABASE_URL` + `SUPABASE_ANON_KEY`
- `verify_token(credentials)` — FastAPI `Security` dependency using `HTTPBearer`. Calls `supabase.auth.get_user(token)` to validate JWT. Returns user on success, raises HTTP 401 on failure.

**`core/rate_limit.py`** (5 lines):
- `limiter = Limiter(key_func=get_remote_address)` — IP-based rate limiting via slowapi

### 4.5 CRUD Operations (`crud/`)

**`crud/auth.py`** (23 lines):
- `upsert_user(db, email, name, provider_uid)` — Queries by email. If exists: updates `last_login`, `name`, `provider_uid`. If not: creates new User. Returns the user.

**`crud/calls.py`** (63 lines):
- `create_call_log(db, contact_id, company_id, ...)` — Creates and persists a CallLog
- `get_call_logs(db, contact_id, company_id, skip, limit)` — Filtered, paginated, ordered by `call_date DESC`
- `update_call_log(db, log_id, **kwargs)` — Partial update
- `delete_call_log(db, log_id)` — Delete by ID

**`crud/history.py`** (86 lines):
- `list_sessions(db, email, limit)` — Lists sessions; filters to user's sessions + orphan sessions (user_id IS NULL)
- `get_session(db, session_id)` — Single session by ID
- `get_session_records(db, session_id, page, page_size)` — Paginated records with total count
- `delete_session(db, session_id)` — Cascading delete
- `get_all_session_records(db, session_id)` — All records (no pagination)
- `find_contacts_by_emails(db, emails)` — Chunked IN query (2000/chunk)
- `find_contacts_by_phones(db, phones)` — Chunked IN query (2000/chunk)
- `get_call_logs_for_contacts(db, contact_ids)` — Returns `{contact_id: [CallLog, ...]}` chunked

### 4.6 API Routes (`api/`)

#### `api/auth.py` (20 lines)
- **`POST /api/auth/upsert`** — Protected by `verify_token`. Calls `crud_upsert_user`, returns `{ok, user_id, email}`.

#### `api/parse.py` (44 lines)
- **`POST /api/parse`** — Accepts file upload (max 30MB). Routes `.xls` → `parse_xls()`, `.pdf` → `parse_pdf()`. Returns `{ok, sheet, headers, rows, rowCount}`. Note: `.xlsx` is NOT handled here (parsed client-side via XLSX.js).

#### `api/contacts.py` (545 lines) — **LARGEST ROUTE FILE**

Constants:
- `INDIAN_MOBILE_RE` — `^(\+91[\s\-]?)?[6-9]\d{9}$`
- `INTL_PHONE_RE` — `^\+(?!91)\d{1,3}[\s\-]?\d{5,14}$`
- `EMAIL_RE` — `^[\w.+%-]+@[\w.-]+\.[a-z]{2,}$`

Routes:
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/contacts/batch` | **Major endpoint.** Batch import: resolves user, creates SessionData, pre-fetches existing contacts (chunked), O(1) duplicate check via hash maps, validates email/phone, classifies phone country, finds/creates Company (cached), creates Contact, archives raw data as Record. Returns `{ok, imported, skipped, flagged_foreign, session_id, contact_ids}` |
| `GET` | `/api/contacts` | Paginated listing (default 50, max 500) with search (ILIKE on name/email/phone/company) and city/industry filters. Returns total count. |
| `GET` | `/api/contacts/{id}` | Single contact with company join |
| `PUT` | `/api/contacts/{id}` | Updates contact fields with validation; updates or creates company |
| `DELETE` | `/api/contacts/{id}` | Deletes single contact |
| `DELETE` | `/api/contacts` | Bulk delete (query param `ids`, chunked 5000) |
| `GET` | `/api/contacts/stats/summary` | Dashboard stats: total contacts, with_email, with_phone, total companies, top 10 cities, top 10 industries |

#### `api/calls.py` (145 lines)
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/calls` | Creates call log; verifies contact exists; auto-fills company_id from contact |
| `GET` | `/api/calls/contact/{contact_id}` | Lists call logs for a contact |
| `PUT` | `/api/calls/{log_id}` | Updates call log fields |
| `DELETE` | `/api/calls/{log_id}` | Deletes call log |

#### `api/history.py` (151 lines)
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/history` | Lists sessions, optionally filtered by email |
| `GET` | `/api/history/{id}` | Session records (paginated), with `_contact_id` attached for frontend editing |
| `DELETE` | `/api/history/{id}` | Deletes session |
| `GET` | `/api/history/{id}/export` | **Export with call logs merged.** Attaches to each record: `_last_call_date`, `_last_call_type`, `_last_outcome`, `_last_notes`, `_total_calls`, `_next_action`, `_next_action_date`, `_all_call_summary` |

#### `api/export_pdf.py` (43 lines)
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/export/pdf` | Calls `generate_pdf()`, returns PDF bytes with Content-Disposition attachment |

#### `api/parse_signature.py` (224 lines)
- **LRU Cache:** In-memory, 500-entry capacity, keyed by MD5 of `{model}_{email_text}`
- **Multi-provider LLM chain:** Iterates through user-configured `chain` of `{provider, model, api_key}` with fallback
- **Retry logic:** 3 retries per provider with exponential backoff (1s, 2s, 4s)
- **Supported providers:** OpenRouter, Groq, OpenAI, DeepSeek, Anthropic, Gemini
- **Rate limited:** 200 requests/minute via slowapi

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/parse-signature` | Cleans email text, cache check, iterates chain, calls LLM, parses JSON response, returns `{ok, fields, cached}` |

**System Prompt** instructs the LLM to extract: `name, company, designation, phone_primary, phone_secondary, email, website, address, city, pincode` from email signatures.

### 4.7 Services (`services/`)

**`services/parser.py`** (317 lines):
- **`parse_xls(content)`** — Parses ALL valid sheets in XLS/XLSX. Skips lookup/index sheets (patterns: "mob no", "email id", "phone list", "mobile list", "index", "lookup"). Merges multi-sheet data. Uses `xlrd` for `.xls`, `openpyxl` for `.xlsx`.
- **`parse_pdf(content)`** — 3-tier fallback: (1) PyMuPDF table extraction via `page.find_tables()`, (2) raw text extraction, (3) `_extract_contacts_from_text()` for free-form text
- **`_extract_contacts_from_text(text)`** — Sophisticated contact extraction using block-based parsing + regex (Indian phone, email, URL, pincode) + delimiter splitting
- **`_extract_fields_from_block(block)`** — Extracts Name, Company, Phone, Email, Website, Pincode, Address using regex for company keywords (ltd, pvt, inc) and Indian address keywords (road, nagar, GIDC)
- **`_dedupe_headers(headers)`** — Deduplicates column names by appending `_1`, `_2` suffixes
- **Config:** `PARSER_TIMEOUT` (env, default 15s XLS / 30s PDF), `PDF_MAX_PAGES` (env, default 200)

**`services/pdf_exporter.py`** (211 lines):
- **`generate_pdf(payload)`** — Builds A4 PDF with ReportLab:
  - Cover section (navy background, title, source info, timestamp)
  - KPI dashboard (Total Records, Fields Mapped, Data Quality %, With Email, With Phone)
  - Data Quality Report (color-coded progress bars: green >75%, amber >40%, rose ≤40%)
  - CRM Data table (first 8 columns, styled headers, alternating rows)
  - Footer with branding

---

## 5. Frontend — Detailed Breakdown

### 5.1 Pages & HTML Structure

#### `signin.html` (600 lines)
- Self-contained page with inline CSS (~290 lines)
- Split layout: Left brand panel + Right auth form
- Sign In form (email/password) + Sign Up form (name/email/password)
- Supabase Auth SDK: `signInWithPassword()`, `signUp()`
- After successful auth: calls `POST /api/auth/upsert` to sync user to backend, stores session in `localStorage('crm-session')`, redirects to `index.html`
- Visual effects: parallax blob, 3D glass tilt, input focus animations

#### `index.html` (425 lines)
- **Auth Guard:** Inline script checks `localStorage('crm-session')` + Supabase token → redirects to `signin.html` if missing
- **CSP Headers:** Allows connections to Supabase, OpenRouter, Groq, OpenAI
- **External libs:** Plus Jakarta Sans + Inter + Outfit + DM Sans + JetBrains Mono fonts, XLSX.js, Chart.js, JSZip, Supabase CDN

**Layout:**
- 3 ambient background blur orbs
- **Sidebar** (fixed, 260px / 76px collapsed):
  - Logo "CRM Engine v4.0"
  - Nav: Import File, Dashboard, Analytics, Data Table, Data Quality, Deduplication, History
  - Export: Save to CRM, Export Excel, PDF, VCF, ZIP
  - File info card, User info with avatar, Sign Out
- **Main content area** with topbar (hamburger, title, action buttons, AI Settings gear, 4-theme picker)

**SPA Views** (one active at a time):
| View ID | Purpose |
|---------|---------|
| `view-upload` | Drop zone for files (`.xlsx,.xls,.csv,.txt,.pdf,.eml` multiple), feature info cards |
| `view-mapping` | Field detection/mapping table: column → type dropdown, confidence %, include checkbox |
| `view-processing` | Loading animation with progress bar and step indicators |
| `view-dashboard` | KPI grid, insight grid, 2 chart rows |
| `view-analytics` | Tab pills (Geographic, Segments, Reachability, Top Records, Distribution) |
| `view-table` | Search, column/value filters, page size, data table with pagination + Edit/Delete/View actions |
| `view-quality` | Quality score, field-by-field fill rates, email/phone validation breakdown |
| `view-dedup` | Duplicate group cards with Keep First / Remove All actions |
| `view-eml` | EML email extractor: KPIs, message preview, contacts, domain intelligence |
| `view-history` | Upload history list with Reload/Export/Delete |

**Modals & Panels:**
- **Edit Modal** — Dynamic form for editing contact fields
- **AI Settings Modal** — Provider chain configuration (drag-to-reorder, add/remove fallback)
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
  sortCol: -1,
  sortDir: 'asc',
  charts: [],       // Chart.js instances
  currentView: 'upload',
  dupGroups: [],    // Duplicate groups
  validation: {     // Validation stats
    dropped: 0, invalidEmails: 0,
    landlines: 0, foreign: 0, total: 0
  },
  dbContacts: {},   // {contact_id: contact} map from backend
  sessionId: null,
  userEmail: null
}
```

**Field Types (`FT`):** 23 types — company, contact, phone, email, address, city, pincode, website, product, industry, amount, date, status, id, keyword, location, facebook, member, fax, whatsapp, files, stdcode, landline, other, skip

**AI Models per Provider:**
- OpenRouter: dynamic (fetched from API)
- Groq: llama-3.3-70b-versatile, llama-3.1-8b-instant, gemma2-9b-it, mixtral-8x7b-32768
- OpenAI: gpt-4o-mini, gpt-4o, gpt-4.1-mini, gpt-4.1-nano
- Anthropic: claude-sonnet-4-20250514, claude-3-5-haiku-20241022
- DeepSeek: deepseek-chat, deepseek-reasoner
- Gemini: gemini-2.0-flash, gemini-2.5-flash-preview-05-20

**EML state (`EML`):** `{raw, parsed, contacts, filtered, sigData, sigLoading}`

**Bulk EML state (`BULK`):** `{files, rows, processed, errors, errorList}`

### 5.3 Complete Function Reference (`app.js`)

#### Auth & Session
| Function | Purpose |
|----------|---------|
| `getAuthToken()` | Gets Supabase JWT access token |
| `apiHeaders()` | Builds headers with `Authorization: Bearer` |
| `apiUploadHeaders()` | Headers for FormData (no Content-Type) |
| `syncAuthSession()` | Validates session, syncs user to backend via `POST /api/auth/upsert` |
| `signOut()` | Signs out of Supabase, clears localStorage |

#### Theme & UI
| Function | Purpose |
|----------|---------|
| `isDarkTheme()` | Returns true for dark/ocean/sunset themes |
| `setTheme(name)` | Sets `data-theme`, updates picker, re-renders charts |
| `toggleSidebar()` | Mobile sidebar open/close |
| `toggleSidebarCollapse()` | Desktop sidebar collapse, persists to localStorage |
| `showView(id)` | SPA view switching with data guard |

#### AI Settings
| Function | Purpose |
|----------|---------|
| `getAiSettings()` | Reads chain from `localStorage('CRM_AI_SETTINGS')` |
| `initAiSettings()` | Initializes AI chain from stored settings |
| `openAiSettingsModal()` / `closeAiSettingsModal()` | Modal open/close |
| `renderAiChain()` | Renders provider chain UI with drag handles |
| `moveChainItem(from, to)` | Reorders chain |
| `onChainDragStart/Over/Drop/End` | Drag-and-drop reordering |
| `addAiFallback()` / `removeAiFallback(index)` | Add/remove providers |
| `syncCurrentChainFromUI()` | Reads UI values into chain array |
| `onProviderChange(index)` | Updates model dropdown |
| `updateModelOptionsForIndex()` | Fetches OpenRouter models or uses static list |
| `saveAiSettings()` | Validates API keys, saves to localStorage |

#### File Handling
| Function | API Call | Purpose |
|----------|----------|---------|
| `getValidSheets(wb)` | — | Filters workbook sheets (skips index/lookup) |
| `detectField(col, samples)` | — | Auto-detects column type (23 types, confidence %) |
| `handleFile(file)` | — | Routes by extension: .eml → `handleEmlFile`, .txt → phone list, .csv → parse, .xlsx → XLSX.js, .xls/.pdf → backend |
| `handleMultipleFiles(fileList)` | `POST /api/parse` | Merges multiple files; routes .eml separately |
| `readFileAsArrayBuffer(file)` | — | Promise-based reader |
| `readFileAsText(file)` | — | Promise-based reader |
| `handleViaBackend(file, ext)` | `POST /api/parse` | Server-side parsing for .xls/.pdf |
| `mergeUnnamedCols(keys, data)` | — | Merges adjacent unnamed Excel columns |

#### Data Processing
| Function | Purpose |
|----------|---------|
| `buildMapping()` | Builds mapping UI with confidence, fill rate, sample data |
| `startProcessing()` | Animated progress → processData → findDuplicates → buildAllViews |
| `processData()` | Cleans data: email validation, phone classification (Indian/international/landline), title casing, URL normalization, mandatory rule enforcement (email OR phone required) |
| `normalizeToStandardFields()` | Maps ANY column structure to 15 standard CRM fields |
| `findDuplicates()` | Full-row fingerprint-based exact match grouping |

#### Validation
| Function | Purpose |
|----------|---------|
| `isValidEmail(v)` | Strict email regex validation |
| `escapeHTML(str)` | XSS prevention |
| `classifyPhone(v)` | Indian mobile / international / landline / invalid |

#### Dashboard & Analytics
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

#### Data Table
| Function | Purpose |
|----------|---------|
| `buildTableControls()` | Column filter dropdown |
| `onColFilterChange()` | Value filter population |
| `filterTable()` | Search + column/value filtering |
| `renderTable()` | Table with type-aware formatting (email links, phone badges, etc.) + action buttons |
| `sortTable(i)` | Column sort toggle |
| `renderPag(total)` / `goPage(p)` | Pagination |

#### Charts
| Function | Purpose |
|----------|---------|
| `addBarChart(parent, title, labels, data, ...)` | Chart.js bar chart with theme colors |
| `addDonutChart(parent, title, labels, data, ...)` | Chart.js doughnut with center total |
| `killCharts()` | Destroys all chart instances |

#### Export
| Function | API Call | Purpose |
|----------|----------|---------|
| `downloadPDF()` | `POST /api/export/pdf` | Backend PDF with fallback to browser print |
| `_printPDFFallback()` | — | Generates HTML report + print dialog |
| `downloadExcel()` | — | Client-side XLSX export with auto-width |
| `downloadVCF()` | — | vCard 3.0 generation |
| `downloadZip()` | `POST /api/export/pdf` | ZIP with Excel + VCF + PDF |

#### CRM CRUD
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

#### EML Email Extractor
| Function | API Call | Purpose |
|----------|----------|---------|
| `handleEmlFile(file)` | — | Reads .eml file as text |
| `triggerEmlMorph(fileName)` | — | Particle animation during parsing |
| `parseEml(fileName)` | `POST /api/parse-signature` | Full MIME parser + AI signature extraction |
| `decodePartBody(body, headers)` | — | Base64/quoted-printable decoding |
| `decodeEmlEncoding(str)` | — | RFC 2047 encoded word decoding |
| `extractSignatureData(bodyText)` | — | Local signature extraction (fallback) |
| `buildEmlDashboard()` | — | Renders EML KPIs, preview, contacts, domains |
| `renderEmlContacts()` | — | Contact cards with avatar |
| `renderSigPanel()` | — | AI-extracted signature display |
| `emlExportCSV()` / `emlExportExcel()` | — | Export EML contacts |
| `emlSaveToSupabase()` | Supabase `eml_emails` + `eml_contacts` | Saves to EML-specific Supabase tables |
| `emlSendToCRM()` | — | Pushes EML contacts into main CRM pipeline |

#### Bulk EML Processor
| Function | API Call | Purpose |
|----------|----------|---------|
| `handleBulkEml(fileList)` | `POST /api/parse-signature` (per file) | Batch process 100-200 EML files with parallel AI (concurrency=2, 1.5s delay, 3 retries, 60s cooldown) |
| `parseSingleEml(raw, fileName)` | — | Standalone EML parser |
| `showBulkProgress/updateBulkProgress/hideBulkProgress` | — | Progress overlay |
| `showBulkDashboard()` | — | Bulk results with data table + domain breakdown |
| `exportBulkExcel()` | — | 3-sheet Excel (All Contacts, Unique, Domain Summary) |
| `pushBulkToCRM()` | — | Deduplicates, normalizes, pushes to CRM |

### 5.4 Styling & Theming

**`style.css`** (1,914 lines, 78KB):
- **4-theme system:** `nexus-light` (default), `nexus-dark`, `ocean`, `sunset`
- **65+ CSS custom properties** covering: sidebar, backgrounds, surfaces, borders, text, accent colors, typography, radius, shadows, transitions
- **Fonts:** Plus Jakarta Sans (display), Inter/DM Sans (body), JetBrains Mono (monospace)
- **Sidebar:** Fixed 260px (76px collapsed), dark background, active state nav items
- **Ambient orbs:** Fixed positioned blurred circles for glassmorphism
- **Base reset** with smooth transitions between themes

### 5.5 Legacy v3 System

**`crm_system_v3.html`** (1,653 lines, 86KB) — Self-contained single-file version:
- Same core: field detection, mapping, processing, dashboard, analytics, quality, dedup
- **Missing from v3:** Auth, Supabase, EML extraction, history/reload, VCF/ZIP export, contact panel, call logs, multi-file merge, backend API, data normalization, phone validation
- Uses `crm_theme.css` (636 lines) — single light theme, simpler design tokens

---

## 6. API Endpoint Reference

| Method | Path | Auth | Rate Limit | Handler | Purpose |
|--------|------|------|-----------|---------|---------|
| `GET` | `/health` | No | No | `main.py` | Health check |
| `POST` | `/api/auth/upsert` | **Yes** | No | `api/auth.py` | Create/update user |
| `POST` | `/api/parse` | No | No | `api/parse.py` | Parse uploaded file (XLS/PDF) |
| `POST` | `/api/parse-signature` | No | **200/min** | `api/parse_signature.py` | AI email signature extraction |
| `POST` | `/api/contacts/batch` | No | No | `api/contacts.py` | Batch import contacts |
| `GET` | `/api/contacts` | No | No | `api/contacts.py` | List contacts (paginated, searchable) |
| `GET` | `/api/contacts/{id}` | No | No | `api/contacts.py` | Get single contact |
| `PUT` | `/api/contacts/{id}` | No | No | `api/contacts.py` | Update contact |
| `DELETE` | `/api/contacts/{id}` | No | No | `api/contacts.py` | Delete contact |
| `DELETE` | `/api/contacts` | No | No | `api/contacts.py` | Bulk delete contacts |
| `GET` | `/api/contacts/stats/summary` | No | No | `api/contacts.py` | Dashboard stats |
| `POST` | `/api/calls` | No | No | `api/calls.py` | Create call log |
| `GET` | `/api/calls/contact/{id}` | No | No | `api/calls.py` | List call logs for contact |
| `PUT` | `/api/calls/{id}` | No | No | `api/calls.py` | Update call log |
| `DELETE` | `/api/calls/{id}` | No | No | `api/calls.py` | Delete call log |
| `GET` | `/api/history` | No | No | `api/history.py` | List upload sessions |
| `GET` | `/api/history/{id}` | No | No | `api/history.py` | Get session records |
| `DELETE` | `/api/history/{id}` | No | No | `api/history.py` | Delete session |
| `GET` | `/api/history/{id}/export` | No | No | `api/history.py` | Export session with call logs |
| `POST` | `/api/export/pdf` | No | No | `api/export_pdf.py` | Generate PDF report |

> ⚠️ **Note:** Only `POST /api/auth/upsert` enforces JWT authentication. All other endpoints are unprotected. The `verify_token` dependency is imported but not used on most routes.

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
  └── .eml  → handleEmlFile() → parseEml() → POST /api/parse-signature

→ buildMapping() → Auto-detect 23 field types with confidence
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
Single EML:
  handleEmlFile() → parseEml()
    1. Parse MIME headers, multipart boundaries
    2. Decode base64/quoted-printable body parts
    3. Extract contacts from headers (From, To, CC)
    4. Extract phones/URLs from body text
    5. POST /api/parse-signature (AI signature extraction)
    6. Build EML dashboard

Bulk EML (100-200 files):
  handleBulkEml()
    → parseSingleEml() per file (local parsing)
    → Parallel AI calls (concurrency=2, 1.5s delay)
    → 3 retries with 60s cooldown on rate limit
    → showBulkDashboard() with results
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
| `GROQ_API_KEY` | `render.yaml` | — | No | Groq LLM API key (configured in Render but not read in Python code; user provides via AI Settings UI) |
| `ALLOWED_ORIGINS` | `render.yaml` | — | No | CORS origins (not actually read in `main.py` — it uses `allow_origins=["*"]`) |
| `PARSER_TIMEOUT` | `services/parser.py` | 15 (XLS) / 30 (PDF) | No | Processing timeout seconds |
| `PDF_MAX_PAGES` | `services/parser.py` | 200 | No | Max PDF pages to process |
| `PYTHON_VERSION` | `render.yaml` | 3.11.8 | No | Python version on Render |

**Frontend config (`config.js`):**
| Variable | Value | Purpose |
|----------|-------|---------|
| `window.CRM_API_BASE` | `https://crm-developer-dashboard.onrender.com` | Backend API URL |
| `window.CRM_SUPABASE_URL` | `https://omqlplhfkriwjubjafgr.supabase.co` | CRM Supabase URL |
| `window.CRM_SUPABASE_ANON_KEY` | (JWT) | CRM Supabase anon key (public, RLS-protected) |
| `window.EML_SUPABASE_URL` | `https://ewlcrbkfwwaunpdanbcv.supabase.co` | EML Supabase URL |
| `window.EML_SUPABASE_ANON_KEY` | (JWT) | EML Supabase anon key |

---

## 10. Deployment Configuration

### Backend (Render) — `render.yaml`
- **Service:** `web` (Python)
- **Name:** `crm-intelligence-api`
- **Build:** `pip install -r requirements.txt`
- **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Python:** 3.11.8
- **Secrets:** `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DATABASE_URL`, `GROQ_API_KEY`

### Frontend (Vercel) — `vercel.json`
- **Builder:** `@vercel/static` for `frontend/**`
- **Routes:** `/(.*) → /frontend/$1` (SPA fallback to `index.html`)
- **URL:** `crmdevloper.vercel.app` (note: typo in "devloper")

### CORS
- Backend: `allow_origins=["*"]` (fully open)
- Render `ALLOWED_ORIGINS` env var is configured but **not actually read** by the application

---

## 11. Testing

### Test Infrastructure (`tests/conftest.py`)
- **In-memory SQLite** (`sqlite+aiosqlite://`) for fast, isolated tests
- **Session-scoped event loop** + engine with all tables created
- **Per-test `db_session`** fixture with rollback after each test

### Test Files
| File | Tests | What's Tested |
|------|-------|---------------|
| `tests/test_api.py` | 2 | `crud.auth.upsert_user` — create new user, update existing user (same email → update name, not duplicate) |
| `tests/test_parser.py` | ~6 | `_dedupe_headers()` — no dupes, dupes → `_1` suffix, None → `Unnamed`; `_extract_contacts_from_text()` — phone extraction, empty text, email extraction, numbered blocks |
| `test_batch.py` | 1 (manual) | Integration test: POST to live Render endpoint with empty batch, checks CORS headers |
| `test_engine.py` | 1 (manual) | Diagnostic: asyncpg engine creation with cache disabled |

### Running Tests
```bash
pytest tests/ -v
```

---

## 12. Key Design Decisions & Caveats

### Architecture
- **Monolith:** Single FastAPI app serves both API and static frontend (mounted at `/`)
- **Async-first:** All database operations use async SQLAlchemy + asyncpg/aiosqlite
- **No ORM migrations:** Uses raw `ALTER TABLE` SQL in `init_db()` for schema evolution
- **Dual database support:** SQLite for local dev, PostgreSQL (Supabase) for production, auto-detected from `DATABASE_URL`

### Security Concerns
- ⚠️ **Most API routes are unprotected** — `verify_token` is imported but NOT applied as a dependency on contacts, calls, history, parse, export, or parse-signature routes. Only `POST /api/auth/upsert` enforces auth.
- ⚠️ **CORS is fully open** — `allow_origins=["*"]`
- ⚠️ **SSL verification disabled** — `check_hostname=False`, `verify_mode=CERT_NONE` for Supabase PostgreSQL
- ⚠️ **LLM API keys stored client-side** — User-provided keys for AI features are stored in `localStorage('CRM_AI_SETTINGS')` and sent to backend per request
- ✅ Supabase anon keys are intentionally public (security via Row Level Security)

### Performance
- **Chunked queries:** All bulk operations (contacts lookup, call logs, bulk delete) use chunked IN queries (2000-5000 per chunk)
- **Company caching:** During batch import, companies are cached per batch to avoid repeated lookups
- **LLM caching:** In-memory LRU cache (500 entries) for parsed email signatures
- **Connection pooling:** pgBouncer-compatible settings (statement_cache_size=0, pool_size=5, max_overflow=10)

### Data Processing
- **15 standard CRM fields:** All imported data is normalized to: Company Name, Location, Address, Pincode, Website, Person Name 1/2, Designation, Mobile 1/2, WhatsApp, Email 1/2, Files, Products/Misc
- **Phone classification:** Indian mobile (`6-9XXXXXXXXX`), international (`+CC...`), landline, invalid
- **Duplicate detection:** Full-row fingerprint from email + phone + name + whatsapp + position + company + city + industry
- **File parsing:** .xlsx and .csv are parsed client-side (XLSX.js); .xls and .pdf are sent to backend (xlrd, PyMuPDF)

### Frontend
- **Pure vanilla JS SPA** — No framework (React, Vue, etc.). All 3,589 lines in a single `app.js`
- **4-theme system** — nexus-light, nexus-dark, ocean, sunset with 65+ CSS custom properties
- **Chart.js** for all visualizations
- **XLSX.js** for client-side Excel parsing/generation
- **JSZip** for ZIP archive creation
- **Two Supabase clients** — One for main CRM auth/data, one for separate EML email feature

### Known Limitations
- `.xlsx` files cannot be parsed server-side (only client-side via XLSX.js)
- PDF parsing has a 3-tier fallback but may not extract all contact data from complex layouts
- No pagination on bulk EML results table (capped at 500 rows display)
- No WebSocket/real-time updates — all data is fetched on demand
- Session history filters show both user's sessions AND orphan sessions (no user association)
- The `ALLOWED_ORIGINS` env var in Render is configured but not actually used by the application (CORS is `*`)

---

## Python Dependencies

```
fastapi==0.111.0          # Web framework
uvicorn[standard]==0.29.0 # ASGI server
python-multipart==0.0.9   # File upload handling
pdfplumber==0.11.0        # (installed but NOT used — PyMuPDF used instead)
openpyxl==3.1.2           # .xlsx file parsing
xlrd==2.0.1               # .xls file parsing
reportlab==4.1.0          # PDF report generation
pandas>=2.0.0             # Data manipulation (installed but minimal usage)
python-dotenv==1.0.1      # .env file loading
httpx==0.27.0             # Async HTTP client (LLM API calls)
groq==0.9.0               # Groq Python SDK (installed but httpx used instead)
sqlalchemy>=2.0.30        # ORM
psycopg2-binary           # PostgreSQL sync driver (likely unused — asyncpg used)
supabase==2.4.5           # Supabase Python client (auth only)
slowapi==0.1.9            # Rate limiting
asyncpg>=0.29.0           # PostgreSQL async driver
pytest                    # Testing
pytest-asyncio            # Async test support
aiofiles                  # Async file I/O
aiosqlite                 # SQLite async driver
PyMuPDF                   # PDF parsing (via fitz)
```

---

## Frontend Libraries (CDN)

- **XLSX.js** (`xlsx.full.min.js`) — Excel parsing/generation
- **Chart.js** — Data visualization
- **JSZip** — ZIP archive creation
- **Supabase JS SDK** (`@supabase/supabase-js@2`) — Auth & database client
- **Google Fonts** — Plus Jakarta Sans, Inter, Outfit, DM Sans, JetBrains Mono
