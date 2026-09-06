from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Uuid, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base
import uuid


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EmlJob(Base):
    """Tracks an EML processing job (batch of .eml files)."""
    __tablename__ = "eml_jobs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_name = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    # pending | processing | completed | failed | cancelled
    total_files = Column(Integer, nullable=False, default=0)
    processed = Column(Integer, nullable=False, default=0)
    succeeded = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
    ai_enriched = Column(Integer, nullable=False, default=0)
    ocr_used = Column(Integer, nullable=False, default=0)
    ai_chain = Column(JSON, nullable=True)  # Client's AI provider chain for enrichment
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    files = relationship("EmlJobFile", back_populates="job", cascade="all, delete-orphan")


class EmlJobFile(Base):
    """Tracks processing status for a single .eml file within a job."""
    __tablename__ = "eml_job_files"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(Uuid, ForeignKey("eml_jobs.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(String(500), nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    # pending | parsing | signature | ai | ocr | done | failed
    attempts = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    extraction_method = Column(String(50), nullable=True)
    # deterministic | heuristic | ai_validate | ai_extract | ocr
    confidence = Column(Integer, default=0)
    extracted_data = Column(JSON, nullable=True)  # Full extracted contact data
    processing_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    job = relationship("EmlJob", back_populates="files")
