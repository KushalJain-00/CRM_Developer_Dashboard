from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base

def _utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id           = Column(Integer, primary_key=True, index=True)
    email        = Column(String(255), unique=True, index=True, nullable=False)
    name         = Column(String(255))
    provider_uid = Column(String(255), index=True)  # Supabase user.id
    last_login   = Column(DateTime)
    created_at   = Column(DateTime, default=_utcnow)
    sessions     = relationship("SessionData", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
class Company(Base):
    """Company/Organization table"""
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    address = Column(Text)
    city = Column(String(255), index=True)
    pincode = Column(String(20))
    website = Column(String(255))
    industry = Column(String(255))
    product = Column(String(255))
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    contacts = relationship("Contact", back_populates="company", cascade="all, delete-orphan", lazy="selectin")
    call_logs = relationship("CallLog", back_populates="company", cascade="all, delete-orphan", lazy="selectin")


class Contact(Base):
    """Contact persons table"""
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    name = Column(String(255))
    email_primary = Column(String(255), index=True)
    email_secondary = Column(String(255))
    phone_primary = Column(String(50), index=True)
    phone_secondary = Column(String(50))
    phone_country = Column(String(10), default="IN")  # "IN" for Indian, "+1" for US, etc.
    whatsapp = Column(String(50))
    position = Column(String(255))
    files = Column(Text)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    company = relationship("Company", back_populates="contacts", lazy="selectin")
    call_logs = relationship("CallLog", back_populates="contact", cascade="all, delete-orphan", lazy="selectin")


class CallLog(Base):
    """Call logs table - tracks all calls made to contacts"""
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    call_date = Column(DateTime, default=_utcnow)
    duration_minutes = Column(Integer)
    call_type = Column(String(50))  # Incoming, Outgoing, Follow-up
    outcome = Column(String(100))  # Connected, Voicemail, No Answer, Callback Scheduled, etc.
    notes = Column(Text)
    next_action = Column(String(255))
    next_action_date = Column(DateTime)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=_utcnow)

    # Relationships
    contact = relationship("Contact", back_populates="call_logs", lazy="selectin")
    company = relationship("Company", back_populates="call_logs", lazy="selectin")


class SessionData(Base):
    """Store uploaded session data for persistence"""
    __tablename__ = "session_data"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255))
    sheet_name = Column(String(255))
    upload_date = Column(DateTime, default=_utcnow)
    mapping = Column(JSON)  # Store field mapping configuration
    is_active = Column(Boolean, default=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=True)
    total_records = Column(Integer, default=0)
    imported      = Column(Integer, default=0)
    skipped       = Column(Integer, default=0)

    # Relationships
    user = relationship("User", back_populates="sessions", lazy="selectin")
    records = relationship("Record", back_populates="session", cascade="all, delete-orphan", lazy="selectin")


class Record(Base):
    """Individual records from uploaded files"""
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("session_data.id"))
    data = Column(JSON)  # Store all record data as JSON
    created_at = Column(DateTime, default=_utcnow)

    # Relationships
    session = relationship("SessionData", back_populates="records", lazy="selectin")
