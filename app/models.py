from datetime import datetime
from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class Enquiry(Base):
    __tablename__='enquiries'
    id: Mapped[str]=mapped_column(String(20),primary_key=True); from_raw: Mapped[str]=mapped_column(Text); subject: Mapped[str]=mapped_column(Text); body: Mapped[str]=mapped_column(Text); attachment: Mapped[str|None]=mapped_column(String(255),nullable=True); attachment_text: Mapped[str|None]=mapped_column(Text,nullable=True)
    status: Mapped[str]=mapped_column(String(40),default='received'); category: Mapped[str|None]=mapped_column(String(64),nullable=True); confidence: Mapped[float|None]=mapped_column(Float,nullable=True); recommended_action: Mapped[str|None]=mapped_column(String(64),nullable=True); assigned_staff: Mapped[str|None]=mapped_column(String(100),nullable=True); requires_human_approval: Mapped[bool]=mapped_column(default=True)
    extracted: Mapped[dict|None]=mapped_column(JSON,nullable=True); missing_information: Mapped[list|None]=mapped_column(JSON,nullable=True); uncertainties: Mapped[list|None]=mapped_column(JSON,nullable=True); draft_response: Mapped[str|None]=mapped_column(Text,nullable=True); analysis_error: Mapped[str|None]=mapped_column(Text,nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime,server_default=func.now()); updated_at: Mapped[datetime]=mapped_column(DateTime,server_default=func.now(),onupdate=func.now())
class CRMSource(Base):
    __tablename__='crm_source_records'
    id: Mapped[str]=mapped_column(String(20),primary_key=True); raw_row: Mapped[str]=mapped_column(Text); data: Mapped[dict]=mapped_column(JSON)
class Candidate(Base):
    __tablename__='candidates'
    id: Mapped[int]=mapped_column(Integer,primary_key=True); enquiry_id: Mapped[str]=mapped_column(String(20),index=True); kind: Mapped[str]=mapped_column(String(12)); target_id: Mapped[str]=mapped_column(String(20)); score: Mapped[float]=mapped_column(Float); level: Mapped[str]=mapped_column(String(32)); reasons: Mapped[list]=mapped_column(JSON)
class AuditEvent(Base):
    __tablename__='audit_events'
    id: Mapped[int]=mapped_column(Integer,primary_key=True); input_id: Mapped[str|None]=mapped_column(String(20),nullable=True,index=True); event_type: Mapped[str]=mapped_column(String(64)); actor: Mapped[str]=mapped_column(String(64),default='system'); details: Mapped[dict|None]=mapped_column(JSON,nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
class ImportWarning(Base):
    __tablename__='import_warnings'
    id: Mapped[int]=mapped_column(Integer,primary_key=True); record_id: Mapped[str]=mapped_column(String(20)); type: Mapped[str]=mapped_column(String(64)); severity: Mapped[str]=mapped_column(String(20)); message: Mapped[str]=mapped_column(Text); raw_row: Mapped[str]=mapped_column(Text)
