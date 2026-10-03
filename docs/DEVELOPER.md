# CRM Intelligence — Developer Guide

This document contains technical details for maintaining, developing, and deploying the CRM Engine v4.0.

## Architecture
- **Backend:** FastAPI (Python 3.11.8) hosted on Render.
- **Frontend:** Vanilla JS SPA hosted on Vercel.
- **Database:** PostgreSQL via Supabase (prod) / SQLite (local dev).
- **Authentication:** Supabase Auth (JWT).
- **Core Features:** File parsing (.xls, .pdf, .eml, .csv, .txt), AI signature extraction via multi-LLM chain, chunked duplicate detection, ReportLab PDF export.

## Local Setup
1. Create a virtual environment:
   ```bash
   python -m venv venv && source venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the backend:
   ```bash
   uvicorn main:app --reload --port 8000
   ```
4. The frontend will be served at `http://localhost:8000`.

## Environment Variables (.env)
- `DATABASE_URL` — Database connection string (defaults to local SQLite if missing).
- `SUPABASE_URL` — Required for authentication.
- `SUPABASE_ANON_KEY` — Required for authentication.
- `PARSER_TIMEOUT` — Timeout for XLS/PDF parsing (default 15/30).

## Deployment
- **Backend (Render):** Uses `render.yaml`. Builds with `pip install -r requirements.txt` and runs `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- **Frontend (Vercel):** Uses `vercel.json`. Uses `@vercel/static` builder for the `frontend/` directory with a rewrite rule to serve the SPA `index.html`.

## Project Layout
- `/main.py` — FastAPI entry point.
- `/api/` — Route handlers (auth, contacts, calls, history, parse, export).
- `/core/` — Utilities (Auth, rate limiters).
- `/crud/` — Database operations.
- `/db/` — SQLAlchemy engine and models.
- `/services/` — Business logic (EML processing, LLM routing, PDF generation).
- `/frontend/` — Static assets (HTML, JS, CSS).

## Testing
Run the pytest suite, which uses an in-memory SQLite database:
```bash
pytest tests/ -v
```
