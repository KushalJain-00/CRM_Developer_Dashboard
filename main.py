from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from api.auth    import router as auth_router
from api.history import router as history_router
from api.parse import router as parse_router
from api.export_pdf import router as pdf_router
from api.contacts import router as contacts_router
from api.calls import router as calls_router
from api.eml import router as eml_new_router
from db.database import init_db, AsyncSessionLocal
from sqlalchemy import text


import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup"""
    logger.info("Starting database initialization...")
    try:
        # 30s so Render free-tier cold starts (slow first DB connect) don't kill startup
        await asyncio.wait_for(init_db(), timeout=30.0)
        logger.info("Database initialized successfully.")
    except asyncio.TimeoutError:
        logger.error("CRITICAL: Database connection timed out! If you are using Supabase on Render, make sure you use the Connection Pooler URL (IPv4) instead of the direct database URL (IPv6).")
        raise
    except Exception as e:
        logger.error(f"CRITICAL: Database initialization failed: {str(e)}")
        raise
    yield


app = FastAPI(
    title="CRM Intelligence API",
    version="2.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from core.rate_limit import limiter

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ponytail: env ALLOWED_ORIGINS can only ADD origins — defaults below are always
# allowed, so a missing/stale env var (Render dashboard vs render.yaml) can't
# silently break CORS for the live frontend.
DEFAULT_ORIGINS = (
    "https://crmdeveloper.vercel.app,"
    "https://crmdevloper.vercel.app,"
    "http://localhost:3000,http://localhost:5173,"
    "http://localhost:5500,http://127.0.0.1:5500,http://localhost:8000"
)
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
ALLOWED_ORIGINS += [o for o in DEFAULT_ORIGINS.split(",") if o not in ALLOWED_ORIGINS]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler — ensures CORS headers are always sent, even on 500 errors
from fastapi import Request, Depends
from fastapi.responses import JSONResponse
import traceback
from core.auth import verify_token

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # ponytail: full tracebacks are great in dev but can leak SQL / connection
    # strings in prod. For production, swap to structured (JSON) logging with a
    # redaction filter and drop traceback.format_exc().
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    logger.error(traceback.format_exc())
    origin = request.headers.get("origin", "")
    headers = {}
    if origin in ALLOWED_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Methods"] = "*"
        headers["Access-Control-Allow-Headers"] = "*"
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=headers,
    )

from fastapi.staticfiles import StaticFiles

@app.get("/health")
async def health_check():
    """Health check: pings the DB so callers detect cold starts / broken connections."""
    try:
        async with AsyncSessionLocal() as s:
            await asyncio.wait_for(s.execute(text("SELECT 1")), timeout=3.0)
        return {"status": "ok"}
    except Exception as e:
        logger.warning(f"Health check degraded: {e}")
        return JSONResponse(status_code=503, content={"status": "degraded"})

# Auth-protected routers: every /api route requires a valid Supabase JWT.
# /api/auth/upsert carries its own verify_token dependency in api/auth.py, so
# it is included here without the router-level dependency. /health is defined
# directly on the app and stays public.
app.include_router(parse_router, prefix="/api", dependencies=[Depends(verify_token)])
app.include_router(pdf_router, prefix="/api", dependencies=[Depends(verify_token)])
app.include_router(contacts_router, prefix="/api", dependencies=[Depends(verify_token)])
app.include_router(calls_router, prefix="/api", dependencies=[Depends(verify_token)])
app.include_router(auth_router, prefix="/api")
app.include_router(history_router, prefix="/api", dependencies=[Depends(verify_token)])
app.include_router(eml_new_router, prefix="/api", dependencies=[Depends(verify_token)])

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

