import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from .database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "platform"}

    tenant_id = Column(String(36), primary_key=True, default=_new_uuid)
    name = Column(String(200), unique=True, nullable=False)
    display_name = Column(String(200), nullable=False)
    tier = Column(String(50), default="standard")
    region = Column(String(50), default="eastus")
    status = Column(String(50), default="Active")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class RiskEntity(Base):
    __tablename__ = "risk_entities"
    __table_args__ = {"schema": "entities"}

    entity_id = Column(String(36), primary_key=True, default=_new_uuid)
    tenant_id = Column(String(36), ForeignKey("platform.tenants.tenant_id"), nullable=False)
    name = Column(String(200), nullable=False)
    entity_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    # Added via ALTER TABLE migration — not in original SQL script
    primary_key_field = Column(String(200), nullable=True)
    data_owner = Column(String(200), nullable=False)
    compliance_tag = Column(String(50), nullable=True, default="NONE")    # single-value; SQL script has compliance_tags (JSON array)
    data_source_registry_id = Column(String(200), nullable=True)
    status = Column(String(50), default="Draft")
    current_version = Column(Integer, default=1)
    created_by = Column(String(200), default="system")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    attributes = relationship(
        "EntityAttribute",
        back_populates="entity",
        cascade="all, delete-orphan",
        order_by="EntityAttribute.sort_order",
    )


class EntityAttribute(Base):
    __tablename__ = "entity_attributes"
    __table_args__ = {"schema": "entities"}

    attribute_id = Column(String(36), primary_key=True, default=_new_uuid)
    entity_id = Column(
        String(36),
        ForeignKey("entities.risk_entities.entity_id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id = Column(String(36), nullable=False)
    name = Column(String(200), nullable=False)
    data_type = Column(String(50), nullable=False, default="string")
    description = Column(Text, nullable=True)           # added via migration
    required = Column(Boolean, default=False)            # SQL script column name is 'required'
    is_primary_key = Column(Boolean, default=False)      # added via migration
    sensitivity_classification = Column(String(50), nullable=True, default="INTERNAL")  # added via migration
    default_value = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)

    entity = relationship("RiskEntity", back_populates="attributes")


class RiskDefinition(Base):
    __tablename__ = "risk_definitions"
    __table_args__ = {"schema": "definitions"}

    definition_id = Column(String(36), primary_key=True, default=_new_uuid)
    tenant_id = Column(String(36), ForeignKey("platform.tenants.tenant_id"), nullable=False)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=False, default="Operational")
    wcgw_entity_type = Column(String(100), nullable=True)   # added via migration
    severity = Column(String(50), default="High")
    status = Column(String(50), default="Draft")
    version = Column(Integer, default=1)
    created_by = Column(String(200), default="system")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    custom_parameters = relationship(
        "CustomParameter",
        back_populates="definition",
        cascade="all, delete-orphan",
        order_by="CustomParameter.sort_order",
    )


class CustomParameter(Base):
    __tablename__ = "custom_parameters"
    __table_args__ = {"schema": "definitions"}

    parameter_id = Column(String(36), primary_key=True, default=_new_uuid)
    definition_id = Column(
        String(36),
        ForeignKey("definitions.risk_definitions.definition_id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id = Column(String(36), nullable=False)
    name = Column(String(200), nullable=False)       # SQL script column; maps to UI 'key'
    data_type = Column(String(50), nullable=False, default="string")  # required NOT NULL in SQL script
    default_value = Column(Text, nullable=True)       # SQL script column; maps to UI 'value'
    sort_order = Column(Integer, default=0)

    definition = relationship("RiskDefinition", back_populates="custom_parameters")
