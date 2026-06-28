import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, Integer, Boolean, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class ScreeningStatus(str, enum.Enum):
    pending   = "pending"
    completed = "completed"
    failed    = "failed"


class MatchResult(str, enum.Enum):
    clear          = "clear"
    possible_match = "possible_match"
    hit            = "hit"


class ScreeningSession(Base):
    """One screening job (may have multiple results for batch)."""
    __tablename__ = "screening_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id   = Column(UUID(as_uuid=True), ForeignKey("users.id",   ondelete="SET NULL"), nullable=True)

    mode = Column(String(20), default="single")  # single / batch
    query_name = Column(String(500), nullable=False)
    query_country = Column(String(200), nullable=True)
    query_type = Column(String(30), nullable=True)     # individual / entity / vessel
    query_dob  = Column(String(50),  nullable=True)

    status = Column(Enum(ScreeningStatus), default=ScreeningStatus.pending, nullable=False)
    total_results = Column(Integer, default=0)
    hit_count     = Column(Integer, default=0)
    possible_count= Column(Integer, default=0)

    sources_checked = Column(JSONB, nullable=True)  # ["OFAC","EU","UN",...]
    completed_at = Column(DateTime, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    results  = relationship("ScreeningResult",  back_populates="session", cascade="all, delete-orphan")
    reports  = relationship("ComplianceReport", back_populates="session", cascade="all, delete-orphan")


class ScreeningResult(Base):
    """Each matched entity for a session."""
    __tablename__ = "screening_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("screening_sessions.id", ondelete="CASCADE"), nullable=False, index=True)

    matched_entity_id = Column(UUID(as_uuid=True), ForeignKey("sanctioned_entities.id"), nullable=True)
    match_result = Column(Enum(MatchResult), nullable=False)
    score = Column(Float, nullable=False)          # 0-100

    matched_name    = Column(String(500), nullable=True)
    matched_source  = Column(String(20),  nullable=True)
    matched_type    = Column(String(20),  nullable=True)
    matched_country = Column(String(200), nullable=True)
    matched_program = Column(String(500), nullable=True)
    match_detail    = Column(JSONB, nullable=True)  # full entity snapshot

    created_at = Column(DateTime, default=datetime.utcnow)
    session = relationship("ScreeningSession", back_populates="results")


class ComplianceReport(Base):
    __tablename__ = "compliance_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("screening_sessions.id", ondelete="CASCADE"), nullable=False)
    tenant_id  = Column(UUID(as_uuid=True), ForeignKey("tenants.id",  ondelete="CASCADE"), nullable=False)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id",    ondelete="SET NULL"), nullable=True)

    reference  = Column(String(50), nullable=False, unique=True)
    status     = Column(String(20), default="generated")
    file_path  = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    session = relationship("ScreeningSession", back_populates="reports")
