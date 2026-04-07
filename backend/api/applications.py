"""
applications.py — Application registration and governance endpoints

Phase 4.1: CRUD (register, list, get, update)
Phase 4.3: Tier endpoints (current tier, tier history)
Phase 4.6: Alignment score          — NotImplementedError (next phase)
Phase 4.7: Benchmarks/recommendations — NotImplementedError (next phase)

Auth: Azure Entra ID Bearer token (enforced at middleware layer).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Application, TierChangeEvent
from db.session import get_db_session as get_db
from core.tier_engine import registration_trigger, TierResult, Tier

router = APIRouter(tags=["applications"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ApplicationRegisterRequest(BaseModel):
    name:                 str
    description:          Optional[str]   = None
    division_id:          Optional[str]   = None
    domain:               str             = Field(..., description="healthcare | criminal_justice | financial | hr | education | internal_ops | asylum | biometric_id | other")
    ai_system_type:       str             = Field(..., description="GEN | RAG | AUTO | DECISION | OTHER")
    decision_type:        str             = Field(..., description="binding | advisory | informational")
    autonomy_level:       str             = Field(..., description="human_in_the_loop | human_on_loop | human_out_of_loop")
    population_breadth:   str             = Field(..., description="local | regional | national | global")
    affected_populations: str             = Field(..., description="general | vulnerable | mixed")
    consent_scope:        str             = Field("tier_aggregate", description="none | tier_aggregate | full")
    owner_email:          Optional[str]   = None


class ApplicationUpdateRequest(BaseModel):
    name:                 Optional[str]   = None
    description:          Optional[str]   = None
    owner_email:          Optional[str]   = None
    consent_scope:        Optional[str]   = None


class TierDimensionBreakdown(BaseModel):
    deployment_domain:    float
    decision_type:        float
    autonomy_level:       float
    population_breadth:   float
    affected_populations: float
    likelihood:           float


class TierResponse(BaseModel):
    application_id: str
    current_tier:   str
    raw_score:      float
    floor_rule:     Optional[str]
    dimensions:     TierDimensionBreakdown
    calculated_at:  datetime


class TierHistoryEntry(BaseModel):
    id:             str
    previous_tier:  Optional[str]
    new_tier:       str
    reason:         Optional[str]
    changed_at:     datetime


class ApplicationResponse(BaseModel):
    id:                   str
    name:                 str
    description:          Optional[str]
    division_id:          Optional[str]
    domain:               Optional[str]
    ai_system_type:       str
    decision_type:        str
    autonomy_level:       str
    population_breadth:   str
    affected_populations: str
    consent_scope:        str
    owner_email:          Optional[str]
    current_tier:         Optional[str]
    registered_at:        datetime


class RegisterApplicationResponse(BaseModel):
    application:          ApplicationResponse
    tier:                 TierResponse
    otel_config:          dict
    missing_metric_groups: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

METRIC_GROUPS_BY_SYSTEM_TYPE: dict[str, list[str]] = {
    "RAG":      ["core", "rag", "security"],
    "GEN":      ["core", "security"],
    "AUTO":     ["core", "security", "risk", "incident"],
    "DECISION": ["core", "risk", "incident", "appeals"],
    "OTHER":    ["core"],
}

METRIC_GROUPS_BY_TIER: dict[str, list[str]] = {
    "High":       ["risk", "incident"],
    "Common":     ["risk", "incident"],
    "Foundation": [],
}


def _required_metric_groups(app: Application) -> list[str]:
    groups = set(METRIC_GROUPS_BY_SYSTEM_TYPE.get(app.ai_system_type, ["core"]))
    groups.update(METRIC_GROUPS_BY_TIER.get(app.current_tier or "Foundation", []))
    return sorted(groups)


def _otel_config(app: Application) -> dict:
    return {
        "service_name":                 app.id,
        "required_resource_attributes": {
            "service.name":                    app.id,
            "service.version":                 "<your-semver>",
            "deployment.environment":          "production",
            "governance.application_id":       app.id,
            "governance.division":             app.division_id or "unassigned",
        },
        "required_metric_groups": _required_metric_groups(app),
        "collector_endpoint":     "https://<governance-api-host>/telemetry/ingest",
    }


def _app_to_response(app: Application) -> ApplicationResponse:
    return ApplicationResponse(
        id=app.id,
        name=app.name,
        description=app.description,
        division_id=app.division_id,
        domain=app.domain,
        ai_system_type=app.ai_system_type,
        decision_type=app.decision_type,
        autonomy_level=app.autonomy_level,
        population_breadth=app.population_breadth,
        affected_populations=app.affected_populations,
        consent_scope=app.consent_scope,
        owner_email=app.owner_email,
        current_tier=app.current_tier,
        registered_at=app.registered_at,
    )


def _tier_result_to_response(app_id: str, result: TierResult) -> TierResponse:
    return TierResponse(
        application_id=app_id,
        current_tier=result.final_tier.value,
        raw_score=result.raw_score,
        floor_rule=result.floor_rule,
        dimensions=TierDimensionBreakdown(**result.dimensions),
        calculated_at=result.calculated_at,
    )


# ---------------------------------------------------------------------------
# Routes — Phase 4.1: CRUD
# ---------------------------------------------------------------------------

@router.post("/applications", status_code=status.HTTP_201_CREATED,
             response_model=RegisterApplicationResponse)
async def register_application(
    body: ApplicationRegisterRequest,
    db:   AsyncSession = Depends(get_db),
):
    app = Application(
        id=str(uuid4()),
        name=body.name,
        description=body.description,
        division_id=body.division_id,
        domain=body.domain,
        ai_system_type=body.ai_system_type,
        decision_type=body.decision_type,
        autonomy_level=body.autonomy_level,
        population_breadth=body.population_breadth,
        affected_populations=body.affected_populations,
        consent_scope=body.consent_scope,
        owner_email=body.owner_email,
        registered_at=datetime.utcnow(),
    )
    db.add(app)
    await db.flush()  # assign id before tier engine runs

    tier_result = await registration_trigger(app, db)

    # Refresh to pick up current_tier written by tier engine
    await db.refresh(app)

    missing = [g for g in _required_metric_groups(app)
               if g not in METRIC_GROUPS_BY_SYSTEM_TYPE.get(app.ai_system_type, [])]

    return RegisterApplicationResponse(
        application=_app_to_response(app),
        tier=_tier_result_to_response(app.id, tier_result),
        otel_config=_otel_config(app),
        missing_metric_groups=missing,
    )


@router.get("/applications", response_model=list[ApplicationResponse])
async def list_applications(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Application).order_by(Application.registered_at.desc()))
    return [_app_to_response(a) for a in result.scalars().all()]


@router.get("/applications/{app_id}", response_model=ApplicationResponse)
async def get_application(app_id: str, db: AsyncSession = Depends(get_db)):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return _app_to_response(app)


@router.patch("/applications/{app_id}", response_model=ApplicationResponse)
async def update_application(
    app_id: str,
    body:   ApplicationUpdateRequest,
    db:     AsyncSession = Depends(get_db),
):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if body.name is not None:
        app.name = body.name
    if body.description is not None:
        app.description = body.description
    if body.owner_email is not None:
        app.owner_email = body.owner_email
    if body.consent_scope is not None:
        app.consent_scope = body.consent_scope

    await db.commit()
    await db.refresh(app)
    return _app_to_response(app)


# ---------------------------------------------------------------------------
# Routes — Phase 4.3: Tier
# ---------------------------------------------------------------------------

@router.get("/applications/{app_id}/tier", response_model=TierResponse)
async def get_tier(app_id: str, db: AsyncSession = Depends(get_db)):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Fetch the most recent TierChangeEvent for full breakdown
    result = await db.execute(
        select(TierChangeEvent)
        .where(TierChangeEvent.application_id == app_id)
        .order_by(TierChangeEvent.changed_at.desc())
        .limit(1)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="No tier calculated yet")

    # Parse stored reason string back to structured response
    # Reason format: "score=XX.XX floor=none|rule dims={...}"
    import ast, re
    score_match = re.search(r"score=([\d.]+)", event.reason or "")
    floor_match = re.search(r"floor=(\S+)", event.reason or "")
    dims_match  = re.search(r"dims=(\{.*\})", event.reason or "")

    raw_score  = float(score_match.group(1)) if score_match else 0.0
    floor_rule = floor_match.group(1) if floor_match else None
    if floor_rule == "none":
        floor_rule = None
    dims_dict  = ast.literal_eval(dims_match.group(1)) if dims_match else {}

    return TierResponse(
        application_id=app_id,
        current_tier=event.new_tier,
        raw_score=raw_score,
        floor_rule=floor_rule,
        dimensions=TierDimensionBreakdown(**dims_dict) if dims_dict else TierDimensionBreakdown(
            deployment_domain=0, decision_type=0, autonomy_level=0,
            population_breadth=0, affected_populations=0, likelihood=0,
        ),
        calculated_at=event.changed_at,
    )


@router.get("/applications/{app_id}/tier/history",
            response_model=list[TierHistoryEntry])
async def get_tier_history(app_id: str, db: AsyncSession = Depends(get_db)):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    result = await db.execute(
        select(TierChangeEvent)
        .where(TierChangeEvent.application_id == app_id)
        .order_by(TierChangeEvent.changed_at.desc())
    )
    return [
        TierHistoryEntry(
            id=e.id,
            previous_tier=e.previous_tier,
            new_tier=e.new_tier,
            reason=e.reason,
            changed_at=e.changed_at,
        )
        for e in result.scalars().all()
    ]


# ---------------------------------------------------------------------------
# Routes — Phase 4.6 / 4.7 (not yet implemented)
# ---------------------------------------------------------------------------

@router.get("/applications/{app_id}/alignment")
async def get_alignment(app_id: str):
    raise NotImplementedError("Phase 4.6")


@router.get("/applications/{app_id}/benchmarks")
async def get_benchmarks(app_id: str):
    raise NotImplementedError("Phase 4.7")


@router.get("/applications/{app_id}/recommendations")
async def get_recommendations(app_id: str):
    raise NotImplementedError("Phase 4.7")
