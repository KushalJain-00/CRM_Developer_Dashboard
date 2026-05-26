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
from api.parse_signature import router as sig_router
from api.parse import router as parse_router
from api.export_pdf import router as pdf_router
from api.contacts import router as contacts_router
from api.calls import router as calls_router
from db.database import init_db


import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup"""
    logger.info("Starting database initialization...")
    try:
        # Wrap in a 10 second timeout so we don't hang forever
        await asyncio.wait_for(init_db(), timeout=10.0)
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

origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles

@app.get("/health")
async def health_check():
    """Health check endpoint for Render to verify the app is running."""
    return {"status": "ok"}

app.include_router(parse_router, prefix="/api")
app.include_router(pdf_router, prefix="/api")
app.include_router(contacts_router, prefix="/api")
app.include_router(calls_router, prefix="/api")
app.include_router(auth_router,    prefix="/api")
app.include_router(history_router, prefix="/api")
app.include_router(sig_router, prefix="/api")

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


@app.get("/health")
async def health():
    return {"status": "ok"}
