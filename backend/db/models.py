"""
SQLAlchemy ORM models — aigov-db (PostgreSQL 16, East US 2, Standard_B2s).
Phase 2.1: run Alembic migrations to create all tables.
Phase 2.2: enable pgvector + TimescaleDB extensions.

TimescaleDB hypertable: metric_reading (partitioned by collected_at).
pgvector: embedding columns on control and requirement.
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Boolean, DateTime, Integer,
    ForeignKey, JSON, Text, UniqueConstraint, Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from pgvector.sqlalchemy import Vector


def _uuid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Regulatory catalog
# ---------------------------------------------------------------------------

class Regulation(Base):
    __tablename__ = "regulation"
    id          = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    title       = Column(String, nullable=False)
    jurisdiction = Column(String)
    source_url  = Column(String)
    effective_date = Column(DateTime)
    created_at  = Column(DateTime, default=datetime.utcnow)
    embedding   = Column(Vector(3072), nullable=True)
    requirements = relationship("Requirement", back_populates="regulation")


class Requirement(Base):
    __tablename__ = "requirement"
    id              = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    regulation_id   = Column(UUID(as_uuid=False), ForeignKey("regulation.id"), nullable=False)
    code            = Column(String, nullable=False)
    title           = Column(String, nullable=False)
    description     = Column(Text)
    category        = Column(String)
    # pgvector column added via Alembic in Phase 2.2
    regulation      = relationship("Regulation", back_populates="requirements")
    controls        = relationship("ControlRequirement", back_populates="requirement")


class Control(Base):
    __tablename__ = "control"
    id          = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    code        = Column(String, unique=True, nullable=False)   # e.g. RM-0
    title       = Column(String, nullable=False)
    description = Column(Text)
    domain      = Column(String, nullable=False)
    tier        = Column(SAEnum("FOUNDATION", "COMMON", "SPECIALIZED", name="control_tier"))
    is_foundation = Column(Boolean, default=False)              # auto-applied to every app
    # pgvector column added via Alembic in Phase 2.2
    requirements = relationship("ControlRequirement", back_populates="control")
    tags        = relationship("ControlTag", back_populates="control")
    metric_definitions = relationship("ControlMetricDefinition", back_populates="control")


class ControlRequirement(Base):
    __tablename__ = "control_requirement"
    control_id     = Column(UUID(as_uuid=False), ForeignKey("control.id"), primary_key=True)
    requirement_id = Column(UUID(as_uuid=False), ForeignKey("requirement.id"), primary_key=True)
    control        = relationship("Control", back_populates="requirements")
    requirement    = relationship("Requirement", back_populates="controls")


class ControlTag(Base):
    __tablename__ = "control_tags"
    id         = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    control_id = Column(UUID(as_uuid=False), ForeignKey("control.id"), nullable=False)
    dimension  = Column(String, nullable=False)   # risk_universality | ai_system_type | deployment_domain | governance_category
    value      = Column(String, nullable=False)
    control    = relationship("Control", back_populates="tags")


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

class TaxonomyTerm(Base):
    __tablename__ = "taxonomy_term"
    id        = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    term      = Column(String, unique=True, nullable=False)
    parent_id = Column(UUID(as_uuid=False), ForeignKey("taxonomy_term.id"), nullable=True)


# ---------------------------------------------------------------------------
# Applications + risk
# ---------------------------------------------------------------------------

class Application(Base):
    __tablename__ = "application"
    id          = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name        = Column(String, nullable=False)
    description = Column(Text)
    division_id = Column(UUID(as_uuid=False), ForeignKey("division.id"), nullable=True)
    domain      = Column(String)                # healthcare | criminal_justice | financial | …
    ai_system_type      = Column(String, nullable=False)
    # GEN | RAG | AUTO | DECISION | OTHER

    decision_type       = Column(String, nullable=False)
    # binding | advisory | informational

    autonomy_level      = Column(String, nullable=False)
    # human_in_the_loop | human_on_loop | human_out_of_loop

    population_breadth  = Column(String, nullable=False)
    # local | regional | national | global

    affected_populations = Column(String, nullable=False)
    # general | vulnerable | mixed

    consent_scope       = Column(String, nullable=False, server_default="tier_aggregate")
    # none | tier_aggregate | full

    owner_email         = Column(String, nullable=True)

    current_tier        = Column(String, nullable=True)
    # Foundation | Common | High — denormalized cache, source of truth is tier_change_event

    registered_at = Column(DateTime, default=datetime.utcnow)
    tier_events   = relationship("TierChangeEvent", back_populates="application")
    metric_readings = relationship("MetricReading", back_populates="application")
    control_assignments = relationship("ControlAssignment", backref="application")


class ControlAssignment(Base):
    """Explicit record of a control assigned to an application.
    Foundation controls are auto-assigned on registration.
    Common/Specialized controls are adopted by the Application Owner.
    """
    __tablename__ = "control_assignment"
    id             = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    application_id = Column(UUID(as_uuid=False), ForeignKey("application.id"), nullable=False)
    control_id     = Column(UUID(as_uuid=False), ForeignKey("control.id"),     nullable=False)
    status         = Column(String, nullable=False, default="pending")
    # adopted | pending | rejected
    assigned_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("application_id", "control_id"),)


class Division(Base):
    __tablename__ = "division"
    id   = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String, unique=True, nullable=False)


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------

class RiskDefinition(Base):
    __tablename__ = "risk_definition"
    id          = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    code        = Column(String, unique=True, nullable=False)
    description = Column(Text)
    tier_floor  = Column(String)


class CanonicalRiskConcept(Base):
    __tablename__ = "canonical_risk_concept"
    id      = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    concept = Column(String, unique=True, nullable=False)


class TierChangeEvent(Base):
    """Immutable audit log of every tier change."""
    __tablename__ = "tier_change_event"
    id             = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    application_id = Column(UUID(as_uuid=False), ForeignKey("application.id"), nullable=False)
    previous_tier  = Column(String)
    new_tier       = Column(String, nullable=False)
    reason         = Column(Text)
    changed_at     = Column(DateTime, default=datetime.utcnow, nullable=False)
    application    = relationship("Application", back_populates="tier_events")


class TierPeerAggregate(Base):
    """Materialised — refreshed on demand (pull model)."""
    __tablename__ = "tier_peer_aggregate"
    id              = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tier            = Column(String, nullable=False)
    metric_name     = Column(String, nullable=False)
    avg_value       = Column(Float)
    peer_count      = Column(Integer)
    refreshed_at    = Column(DateTime, default=datetime.utcnow)
    __table_args__  = (UniqueConstraint("tier", "metric_name"),)


# ---------------------------------------------------------------------------
# Telemetry / KPI
# ---------------------------------------------------------------------------

class MetricReading(Base):
    """
    TimescaleDB hypertable — partitioned by collected_at.
    Phase 2.2: convert to hypertable via Alembic migration.
    Only production-environment readings are stored (filtered at ingest).
    """
    __tablename__ = "metric_reading"
    id             = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    collected_at   = Column(DateTime(timezone=True), primary_key=True, nullable=False)  # hypertable partition key
    application_id = Column(UUID(as_uuid=False), ForeignKey("application.id"), nullable=False)
    metric_name    = Column(Text, nullable=False)        # e.g. ai.model.error_rate
    value          = Column(Float, nullable=False)
    attributes     = Column(JSON)                        # full OTEL resource attributes
    application    = relationship("Application", back_populates="metric_readings")


class ControlMetricDefinition(Base):
    """KPI binding contract: links Control → metric name + threshold."""
    __tablename__ = "control_metric_definition"
    id          = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    control_id  = Column(UUID(as_uuid=False), ForeignKey("control.id"), nullable=False)
    metric_name = Column(String, nullable=False)
    threshold   = Column(JSON, nullable=False)          # {operator, value, unit}
    is_manual   = Column(Boolean, default=False)
    control     = relationship("Control", back_populates="metric_definitions")


class MetricSource(Base):
    __tablename__ = "metric_source"
    id          = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name        = Column(String, nullable=False)
    adapter     = Column(String)                        # OTEL | manual | computed


class CalculatedMetric(Base):
    __tablename__ = "calculated_metric"
    id                      = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    application_id          = Column(UUID(as_uuid=False), ForeignKey("application.id"), nullable=False)
    control_id              = Column(UUID(as_uuid=False), ForeignKey("control.id"), nullable=False)
    metric_name             = Column(String, nullable=False)
    result                  = Column(SAEnum("PASS", "FAIL", "INSUFFICIENT_DATA", name="kpi_result"))
    value                   = Column(Float)
    calculated_at           = Column(DateTime, default=datetime.utcnow)


class ControlCalculationProposal(Base):
    """Created for manual controls that need human review."""
    __tablename__ = "control_calculation_proposal"
    id             = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    control_id     = Column(UUID(as_uuid=False), ForeignKey("control.id"), nullable=False)
    application_id = Column(UUID(as_uuid=False), ForeignKey("application.id"), nullable=False)
    proposed_value = Column(JSON)
    status         = Column(SAEnum("PENDING", "APPROVED", "REJECTED", name="proposal_status"), default="PENDING")
    created_at     = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Interpretations + curation
# ---------------------------------------------------------------------------

class RiskInterpretation(Base):
    """3-layer: Source / System / User."""
    __tablename__ = "risk_interpretation"
    id           = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    requirement_id = Column(UUID(as_uuid=False), ForeignKey("requirement.id"), nullable=False)
    layer        = Column(SAEnum("SOURCE", "SYSTEM", "USER", name="interpretation_layer"))
    content      = Column(Text, nullable=False)
    version      = Column(Integer, default=1)
    created_at   = Column(DateTime, default=datetime.utcnow)


class InterpretationDivergenceSignal(Base):
    __tablename__ = "interpretation_divergence_signal"
    id                = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    interpretation_id = Column(UUID(as_uuid=False), ForeignKey("risk_interpretation.id"), nullable=False)
    signal_type       = Column(String)
    detected_at       = Column(DateTime, default=datetime.utcnow)


class CurationQueueItem(Base):
    __tablename__ = "curation_queue_item"
    id          = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    entity_type = Column(String, nullable=False)  # control | requirement | interpretation
    entity_id   = Column(UUID(as_uuid=False), nullable=False)
    action      = Column(String, nullable=False)
    payload     = Column(JSON)
    status      = Column(SAEnum("PENDING", "APPROVED", "REJECTED", name="curation_status"), default="PENDING")
    submitted_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Users / roles
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "user"
    id          = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    entra_oid   = Column(String, unique=True, nullable=False)   # Azure Entra object ID
    email       = Column(String, unique=True, nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow)
    roles       = relationship("RoleAssignment", back_populates="user")


class RoleAssignment(Base):
    __tablename__ = "role_assignment"
    id          = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id     = Column(UUID(as_uuid=False), ForeignKey("user.id"), nullable=False)
    role        = Column(String, nullable=False)    # admin | analyst | viewer
    scope       = Column(String)                    # optional: division or application scope
    user        = relationship("User", back_populates="roles")
