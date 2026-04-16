from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import get_db
from db.models import Company, Contact, CallLog, SessionData, Record
from core.auth import verify_api_key

router = APIRouter()


# ============== Company Endpoints ==============

class CompanyCreate(BaseModel):
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    product: Optional[str] = None


class CompanyResponse(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    product: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post("/companies", response_model=CompanyResponse, dependencies=[Depends(verify_api_key)])
def create_company(company: CompanyCreate, db: Session = Depends(get_db)):
    db_company = Company(**company.model_dump())
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    return db_company


@router.get("/companies", response_model=List[CompanyResponse], dependencies=[Depends(verify_api_key)])
def get_companies(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    companies = db.query(Company).offset(skip).limit(limit).all()
    return companies


@router.get("/companies/{company_id}", response_model=CompanyResponse, dependencies=[Depends(verify_api_key)])
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.put("/companies/{company_id}", response_model=CompanyResponse, dependencies=[Depends(verify_api_key)])
def update_company(company_id: int, company: CompanyCreate, db: Session = Depends(get_db)):
    db_company = db.query(Company).filter(Company.id == company_id).first()
    if not db_company:
        raise HTTPException(status_code=404, detail="Company not found")
    for key, value in company.model_dump().items():
        setattr(db_company, key, value)
    db.commit()
    db.refresh(db_company)
    return db_company


@router.delete("/companies/{company_id}", dependencies=[Depends(verify_api_key)])
def delete_company(company_id: int, db: Session = Depends(get_db)):
    db_company = db.query(Company).filter(Company.id == company_id).first()
    if not db_company:
        raise HTTPException(status_code=404, detail="Company not found")
    db.delete(db_company)
    db.commit()
    return {"message": "Company deleted successfully"}


# ============== Contact Endpoints ==============

class ContactCreate(BaseModel):
    company_id: Optional[int] = None
    name: Optional[str] = None
    email_primary: Optional[str] = None
    email_secondary: Optional[str] = None
    phone_primary: Optional[str] = None
    phone_secondary: Optional[str] = None
    whatsapp: Optional[str] = None
    position: Optional[str] = None


class ContactResponse(BaseModel):
    id: int
    company_id: Optional[int] = None
    name: Optional[str] = None
    email_primary: Optional[str] = None
    email_secondary: Optional[str] = None
    phone_primary: Optional[str] = None
    phone_secondary: Optional[str] = None
    whatsapp: Optional[str] = None
    position: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post("/contacts", response_model=ContactResponse, dependencies=[Depends(verify_api_key)])
def create_contact(contact: ContactCreate, db: Session = Depends(get_db)):
    db_contact = Contact(**contact.model_dump())
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact


@router.get("/contacts", response_model=List[ContactResponse], dependencies=[Depends(verify_api_key)])
def get_contacts(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    contacts = db.query(Contact).offset(skip).limit(limit).all()
    return contacts


@router.get("/contacts/{contact_id}", response_model=ContactResponse, dependencies=[Depends(verify_api_key)])
def get_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.put("/contacts/{contact_id}", response_model=ContactResponse, dependencies=[Depends(verify_api_key)])
def update_contact(contact_id: int, contact: ContactCreate, db: Session = Depends(get_db)):
    db_contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not db_contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    for key, value in contact.model_dump().items():
        setattr(db_contact, key, value)
    db.commit()
    db.refresh(db_contact)
    return db_contact


@router.delete("/contacts/{contact_id}", dependencies=[Depends(verify_api_key)])
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    db_contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not db_contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(db_contact)
    db.commit()
    return {"message": "Contact deleted successfully"}


# ============== Call Log Endpoints ==============

class CallLogCreate(BaseModel):
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    duration_minutes: Optional[int] = None
    call_type: Optional[str] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[datetime] = None
    created_by: Optional[str] = None


class CallLogResponse(BaseModel):
    id: int
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    call_date: datetime
    duration_minutes: Optional[int] = None
    call_type: Optional[str] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[datetime] = None
    created_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/call-logs", response_model=CallLogResponse, dependencies=[Depends(verify_api_key)])
def create_call_log(call_log: CallLogCreate, db: Session = Depends(get_db)):
    db_call_log = CallLog(**call_log.model_dump())
    db.add(db_call_log)
    db.commit()
    db.refresh(db_call_log)
    return db_call_log


@router.get("/call-logs", response_model=List[CallLogResponse], dependencies=[Depends(verify_api_key)])
def get_call_logs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    call_logs = db.query(CallLog).offset(skip).limit(limit).all()
    return call_logs


@router.get("/call-logs/contact/{contact_id}", response_model=List[CallLogResponse], dependencies=[Depends(verify_api_key)])
def get_call_logs_by_contact(contact_id: int, db: Session = Depends(get_db)):
    call_logs = db.query(CallLog).filter(CallLog.contact_id == contact_id).order_by(CallLog.call_date.desc()).all()
    return call_logs


@router.get("/call-logs/company/{company_id}", response_model=List[CallLogResponse], dependencies=[Depends(verify_api_key)])
def get_call_logs_by_company(company_id: int, db: Session = Depends(get_db)):
    call_logs = db.query(CallLog).filter(CallLog.company_id == company_id).order_by(CallLog.call_date.desc()).all()
    return call_logs


@router.delete("/call-logs/{call_log_id}", dependencies=[Depends(verify_api_key)])
def delete_call_log(call_log_id: int, db: Session = Depends(get_db)):
    db_call_log = db.query(CallLog).filter(CallLog.id == call_log_id).first()
    if not db_call_log:
        raise HTTPException(status_code=404, detail="Call log not found")
    db.delete(db_call_log)
    db.commit()
    return {"message": "Call log deleted successfully"}
