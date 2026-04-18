from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from api.auth    import router as auth_router
from api.history import router as history_router
import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from api.parse import router as parse_router
from api.export_pdf import router as pdf_router
from api.contacts import router as contacts_router
from api.calls import router as calls_router
from db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup"""
    init_db()
    yield


app = FastAPI(
    title="CRM Intelligence API",
    version="2.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(parse_router, prefix="/api")
app.include_router(pdf_router, prefix="/api")
app.include_router(contacts_router, prefix="/api")
app.include_router(calls_router, prefix="/api")
app.include_router(auth_router,    prefix="/api")
app.include_router(history_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
