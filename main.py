from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from api.parse import router as parse_router
from api.export_pdf import router as pdf_router

app = FastAPI(title="CRM Intelligence API", version="1.0.0", docs_url=None, redoc_url=None)

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

@app.get("/health")
async def health():
    return {"status": "ok"}
