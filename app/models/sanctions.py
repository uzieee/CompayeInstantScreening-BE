import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.database import Base


class SanctionedEntity(Base):
    __tablename__ = "sanctioned_entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(20), nullable=False, index=True)   # OFAC, EU, UN, UK, CA, AU
    source_id = Column(String(100), nullable=True)            # original list ID
    entity_type = Column(String(20), nullable=False, index=True)  # individual / entity / vessel / aircraft

    # Primary name (normalised for matching)
    name = Column(String(500), nullable=False, index=True)
    name_original = Column(String(500), nullable=False)

    # Aliases stored as PostgreSQL array for fast lookups
    aliases = Column(ARRAY(String), nullable=True, default=[])

    nationality = Column(String(200), nullable=True)
    country = Column(String(200), nullable=True)
    date_of_birth = Column(String(50), nullable=True)
    place_of_birth = Column(String(200), nullable=True)
    passport_number = Column(String(100), nullable=True)
    national_id = Column(String(100), nullable=True)

    # Vessel-specific
    vessel_flag = Column(String(50), nullable=True)
    vessel_imo = Column(String(50), nullable=True)
    vessel_type = Column(String(100), nullable=True)

    program = Column(String(500), nullable=True)   # sanction programme name
    reason = Column(Text, nullable=True)
    listed_on = Column(String(50), nullable=True)
    last_updated = Column(String(50), nullable=True)

    raw_data = Column(Text, nullable=True)  # JSON snapshot of original record

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_sanctioned_name_source", "name", "source"),
    )
