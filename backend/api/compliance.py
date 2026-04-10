"""
compliance.py â€” Compliance summary and per-control KPI evidence

GET  /applications/{app_id}/compliance          â€” compliance summary (triggers KPI calc)
POST /applications/{app_id}/compliance          â€” force recalculation
GET  /applications/{app_id}/compliance/controls â€” per-control evidence detail
GET  /curation/queue                            â€” curation queue (admin)
POST /curation/queue                            â€” submit curation item (admin)

Pull model: KPIs calculated on-demand, never pre-scheduled.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Application,
    ApplicationRequirement,
    CalculatedMetric,
    ControlAssignment,
    ControlRequirement,
    CurationQueueItem,
    ApprovedSystemAttribute,
)
from db.session import get_db_session as get_db
from core.kpi_calculator import KPICalculator

router = APIRouter(tags=["compliance"])
calculator = KPICalculator()
ALLOWED_CURATION_ITEM_TYPES = {"regulation", "requirement", "control", "measure", "interpretation"}
LEGACY_CURATION_ITEM_MAP = {
    "new_control": "control",
    "new_requirement": "requirement",
    "metric_update": "measure",
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ControlKPIResult(BaseModel):
    control_id:  str
    metric_name: str
    result:      str        # PASS | FAIL | INSUFFICIENT_DATA
    value:       Optional[float]
    threshold:   Optional[dict]
    evidence_ts: Optional[str]
    is_manual:   bool


class ComplianceSummary(BaseModel):
    application_id:    str
    calculated_at:     datetime
    total_controls:    int
    scope_active:      bool
    scoped_controls:   int
    total_adopted_controls: int
    pass_count:        int
    fail_count:        int
    insufficient_count: int
    pass_rate:         float   # 0.0â€“1.0, excludes INSUFFICIENT_DATA
    controls:          list[ControlKPIResult]


class CurationItemRequest(BaseModel):
    item_type: str
    proposed_by: str
    control_id: Optional[str] = None
    justification: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    parent_chain: Optional[dict] = None
    proposed: Optional[dict] = None  # legacy alias

    class Config:
        extra = "forbid"


class CurationItemResponse(BaseModel):
    id: str
    control_id: Optional[str]
    item_type: Optional[str]
    status: str
    created_at: datetime
    proposed_by: Optional[str]
    justification: Optional[str]
    parent_chain: Optional[dict]
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None


class CurationReviewRequest(BaseModel):
    status: str = Field(..., description="APPROVED | REJECTED | NEEDS_REVISION")
    reviewed_by: str
    reviewer_notes: Optional[str] = None

    class Config:
        extra = "forbid"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_app_or_404(app_id: str, db: AsyncSession) -> Application:
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


def _build_summary(
    app_id: str,
    results: list[dict],
    *,
    scope_active: bool,
    scoped_controls: int,
    total_adopted_controls: int,
) -> ComplianceSummary:
    pass_count        = sum(1 for r in results if r["result"] == "PASS")
    fail_count        = sum(1 for r in results if r["result"] == "FAIL")
    insufficient      = sum(1 for r in results if r["result"] == "INSUFFICIENT_DATA")
    decided           = pass_count + fail_count
    pass_rate         = (pass_count / decided) if decided > 0 else 0.0

    return ComplianceSummary(
        application_id=app_id,
        calculated_at=datetime.utcnow(),
        total_controls=len(results),
        scope_active=scope_active,
        scoped_controls=scoped_controls,
        total_adopted_controls=total_adopted_controls,
        pass_count=pass_count,
        fail_count=fail_count,
        insufficient_count=insufficient,
        pass_rate=round(pass_rate, 4),
        controls=[ControlKPIResult(**r) for r in results],
    )


async def _get_scoped_control_ids(app_id: str, db: AsyncSession) -> tuple[set[str], bool]:
    """Return (scoped_control_ids, scope_active) for this app."""
    selected_count = await db.scalar(
        select(func.count())
        .select_from(ApplicationRequirement)
        .where(ApplicationRequirement.application_id == app_id)
    )
    if not selected_count:
        return set(), False

    result = await db.execute(
        select(ControlRequirement.control_id)
        .join(
            ApplicationRequirement,
            ApplicationRequirement.requirement_id == ControlRequirement.requirement_id,
        )
        .where(ApplicationRequirement.application_id == app_id)
        .distinct()
    )
    return {str(control_id) for control_id in result.scalars().all()}, True


async def _get_adopted_control_ids(app_id: str, db: AsyncSession) -> set[str]:
    result = await db.execute(
        select(ControlAssignment.control_id)
        .where(
            ControlAssignment.application_id == app_id,
            ControlAssignment.status == "adopted",
        )
        .distinct()
    )
    return {str(control_id) for control_id in result.scalars().all()}


def _normalize_item_type(item_type: str) -> str:
    low = (item_type or "").strip().lower()
    return LEGACY_CURATION_ITEM_MAP.get(low, low)


def _extract_formula_fields(payload: dict) -> set[str]:
    fields: set[str] = set()
    formula = payload.get("formula_definition")
    if isinstance(formula, dict):
        picker = formula.get("field_picker")
        if isinstance(picker, str) and picker.strip():
            fields.add(picker.strip())
        raw_fields = formula.get("fields")
        if isinstance(raw_fields, list):
            for value in raw_fields:
                if isinstance(value, str) and value.strip():
                    fields.add(value.strip())
    elif isinstance(formula, str):
        for match in re.findall(r"[a-zA-Z_][a-zA-Z0-9_.]*", formula):
            if "." in match:
                fields.add(match)

    approved_list = payload.get("approved_system_attributes")
    if isinstance(approved_list, list):
        for value in approved_list:
            if isinstance(value, str) and value.strip():
                fields.add(value.strip())
    return fields


async def _validate_measure_curation_payload(
    payload: dict,
    parent_chain: dict,
    db: AsyncSession,
) -> None:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="payload must be an object")
    if not isinstance(parent_chain, dict):
        raise HTTPException(status_code=422, detail="parent_chain is required for measure proposals")

    errors: list[str] = []
    if not (parent_chain.get("regulation_id") or parent_chain.get("regulation_title_new")):
        errors.append("parent_chain requires regulation_id or regulation_title_new")
    if not parent_chain.get("requirement_text"):
        errors.append("parent_chain.requirement_text is required")
    if not parent_chain.get("control_name"):
        errors.append("parent_chain.control_name is required")
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    required_payload = ["measure_name", "formula_definition", "threshold"]
    missing_payload = [k for k in required_payload if payload.get(k) in (None, "")]
    if missing_payload:
        raise HTTPException(
            status_code=422,
            detail=f"measure payload missing required fields: {', '.join(missing_payload)}",
        )

    formula_fields = _extract_formula_fields(payload)
    if not formula_fields:
        raise HTTPException(
            status_code=422,
            detail="measure payload must include formula fields via formula_definition or approved_system_attributes",
        )

    result = await db.execute(
        select(ApprovedSystemAttribute.attribute_name).where(
            ApprovedSystemAttribute.attribute_name.in_(sorted(formula_fields)),
            ApprovedSystemAttribute.is_active.is_(True),
        )
    )
    existing = {row[0] for row in result.fetchall()}
    missing_fields = sorted(formula_fields - existing)
    if missing_fields:
        raise HTTPException(
            status_code=422,
            detail=(
                "formula fields are not approved_system_attributes: "
                + ", ".join(missing_fields[:10])
            ),
        )


# ---------------------------------------------------------------------------
# Routes â€” compliance
# ---------------------------------------------------------------------------

@router.get("/applications/{app_id}/compliance",
            response_model=ComplianceSummary)
async def get_compliance(
    app_id: str,
    db:     AsyncSession = Depends(get_db),
):
    """
    Return compliance summary for the application.
    Triggers KPI calculation on demand (pull model).
    """
    await _get_app_or_404(app_id, db)
    scoped_control_ids, scope_active = await _get_scoped_control_ids(app_id, db)
    adopted_control_ids = await _get_adopted_control_ids(app_id, db)
    effective_scope = scoped_control_ids & adopted_control_ids if scope_active else set()
    if scope_active and not effective_scope:
        results = []
    else:
        results = await calculator.calculate_for_application(
            app_id,
            db,
            scoped_control_ids=effective_scope or None,
        )
    await db.commit()
    return _build_summary(
        app_id,
        results,
        scope_active=scope_active,
        scoped_controls=len(effective_scope),
        total_adopted_controls=len(adopted_control_ids),
    )


@router.post("/applications/{app_id}/compliance",
             response_model=ComplianceSummary,
             status_code=status.HTTP_200_OK)
async def recalculate_compliance(
    app_id: str,
    db:     AsyncSession = Depends(get_db),
):
    """Force a fresh KPI recalculation regardless of cache."""
    await _get_app_or_404(app_id, db)
    scoped_control_ids, scope_active = await _get_scoped_control_ids(app_id, db)
    adopted_control_ids = await _get_adopted_control_ids(app_id, db)
    effective_scope = scoped_control_ids & adopted_control_ids if scope_active else set()
    if scope_active and not effective_scope:
        results = []
    else:
        results = await calculator.calculate_for_application(
            app_id,
            db,
            scoped_control_ids=effective_scope or None,
        )
    await db.commit()
    return _build_summary(
        app_id,
        results,
        scope_active=scope_active,
        scoped_controls=len(effective_scope),
        total_adopted_controls=len(adopted_control_ids),
    )


@router.get("/applications/{app_id}/compliance/controls",
            response_model=list[ControlKPIResult])
async def get_compliance_controls(
    app_id: str,
    db:     AsyncSession = Depends(get_db),
):
    """
    Return per-control KPI evidence from the most recent calculation.
    Does NOT trigger recalculation â€” reads last written CalculatedMetric rows.
    """
    await _get_app_or_404(app_id, db)

    # Get most recent calculated_at timestamp for this app
    latest_ts = await db.scalar(
        select(func.max(CalculatedMetric.calculated_at))
        .where(CalculatedMetric.application_id == app_id)
    )

    if not latest_ts:
        return []

    result = await db.execute(
        select(CalculatedMetric)
        .where(
            CalculatedMetric.application_id == app_id,
            CalculatedMetric.calculated_at  == latest_ts,
        )
    )
    rows = result.scalars().all()

    scoped_control_ids, scope_active = await _get_scoped_control_ids(app_id, db)
    if scope_active:
        rows = [r for r in rows if str(r.control_id) in scoped_control_ids]

    return [
        ControlKPIResult(
            control_id=r.control_id,
            metric_name=r.metric_name,
            result=r.result,
            value=r.value,
            threshold=None,     # threshold stored on ControlMetricDefinition, not CalculatedMetric
            evidence_ts=r.calculated_at.isoformat(),
            is_manual=False,    # would need join to ControlMetricDefinition for accurate value
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Routes â€” curation queue (admin)
# ---------------------------------------------------------------------------

@router.get("/curation/queue", response_model=list[CurationItemResponse])
async def get_curation_queue(db: AsyncSession = Depends(get_db)):
    """Admin only â€” list pending curation items."""
    result = await db.execute(
        select(CurationQueueItem)
        .order_by(CurationQueueItem.created_at.desc())
    )
    items = result.scalars().all()
    return [
        CurationItemResponse(
            id=i.id,
            control_id=getattr(i, "control_id", None),
            item_type=getattr(i, "item_type", None),
            status=getattr(i, "status", "PENDING"),
            created_at=i.created_at,
            proposed_by=getattr(i, "proposed_by", None),
            justification=getattr(i, "justification", None),
            parent_chain=getattr(i, "parent_chain", None),
            reviewed_by=getattr(i, "reviewed_by", None),
            reviewed_at=getattr(i, "reviewed_at", None),
            reviewer_notes=getattr(i, "reviewer_notes", None),
        )
        for i in items
    ]


@router.post("/curation/queue", status_code=status.HTTP_201_CREATED,
             response_model=CurationItemResponse)
async def submit_curation_item(
    body: CurationItemRequest,
    db:   AsyncSession = Depends(get_db),
):
    """Admin only â€” submit a new curation item."""
    item_type = _normalize_item_type(body.item_type)
    if item_type not in ALLOWED_CURATION_ITEM_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"item_type must be one of {sorted(ALLOWED_CURATION_ITEM_TYPES)}",
        )

    payload = body.payload or body.proposed or {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="payload must be an object")

    parent_chain = body.parent_chain or {}
    if item_type == "measure":
        await _validate_measure_curation_payload(payload, parent_chain, db)

    item = CurationQueueItem(
        id=str(uuid4()),
        created_at=datetime.utcnow(),
        proposed_at=datetime.utcnow(),
        submitted_at=datetime.utcnow(),
    )
    for field, value in (
        ("entity_type", item_type),
        ("entity_id", body.control_id or str(uuid4())),
        ("action", "propose"),
        ("control_id", body.control_id),
        ("item_type", item_type),
        ("proposed", payload),
        ("payload", payload),
        ("justification", body.justification),
        ("parent_chain", parent_chain),
        ("proposed_by", body.proposed_by),
    ):
        if hasattr(item, field):
            setattr(item, field, value)

    db.add(item)
    await db.commit()
    await db.refresh(item)

    return CurationItemResponse(
        id=item.id,
        control_id=getattr(item, "control_id", None),
        item_type=getattr(item, "item_type", None),
        status=getattr(item, "status", "PENDING"),
        created_at=item.created_at,
        proposed_by=getattr(item, "proposed_by", None),
        justification=getattr(item, "justification", None),
        parent_chain=getattr(item, "parent_chain", None),
        reviewed_by=getattr(item, "reviewed_by", None),
        reviewed_at=getattr(item, "reviewed_at", None),
        reviewer_notes=getattr(item, "reviewer_notes", None),
    )


@router.patch("/curation/queue/{item_id}", response_model=CurationItemResponse)
async def review_curation_item(
    item_id: str,
    body: CurationReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """Admin review decision for a curation queue item."""
    next_status = (body.status or "").strip().upper()
    if next_status not in {"APPROVED", "REJECTED", "NEEDS_REVISION"}:
        raise HTTPException(
            status_code=422,
            detail="status must be one of APPROVED, REJECTED, NEEDS_REVISION",
        )

    item = await db.get(CurationQueueItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Curation item not found")

    item.status = next_status
    item.reviewed_by = body.reviewed_by
    item.reviewed_at = datetime.utcnow()
    item.reviewer_notes = body.reviewer_notes

    await db.commit()
    await db.refresh(item)

    return CurationItemResponse(
        id=item.id,
        control_id=getattr(item, "control_id", None),
        item_type=getattr(item, "item_type", None),
        status=getattr(item, "status", "PENDING"),
        created_at=item.created_at,
        proposed_by=getattr(item, "proposed_by", None),
        justification=getattr(item, "justification", None),
        parent_chain=getattr(item, "parent_chain", None),
        reviewed_by=getattr(item, "reviewed_by", None),
        reviewed_at=getattr(item, "reviewed_at", None),
        reviewer_notes=getattr(item, "reviewer_notes", None),
    )

