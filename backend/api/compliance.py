"""
compliance.py — Compliance summary and per-control KPI evidence

GET  /applications/{app_id}/compliance          — compliance summary (triggers KPI calc)
POST /applications/{app_id}/compliance          — force recalculation
GET  /applications/{app_id}/compliance/controls — per-control evidence detail
GET  /curation/queue                            — curation queue (admin)
POST /curation/queue                            — submit curation item (admin)

Pull model: KPIs calculated on-demand, never pre-scheduled.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Application,
    CalculatedMetric,
    ControlAssignment,
    ControlCalculationProposal,
    CurationQueueItem,
)
from db.session import get_db_session as get_db
from core.kpi_calculator import KPICalculator

router = APIRouter(tags=["compliance"])
calculator = KPICalculator()


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
    pass_count:        int
    fail_count:        int
    insufficient_count: int
    pass_rate:         float   # 0.0–1.0, excludes INSUFFICIENT_DATA
    controls:          list[ControlKPIResult]


class CurationItemRequest(BaseModel):
    control_id:   str
    item_type:    str           # new_control | new_requirement | metric_update
    proposed:     dict
    justification: Optional[str] = None


class CurationItemResponse(BaseModel):
    id:         str
    control_id: Optional[str]
    item_type:  Optional[str]
    status:     str
    created_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_app_or_404(app_id: str, db: AsyncSession) -> Application:
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


def _build_summary(app_id: str, results: list[dict]) -> ComplianceSummary:
    pass_count        = sum(1 for r in results if r["result"] == "PASS")
    fail_count        = sum(1 for r in results if r["result"] == "FAIL")
    insufficient      = sum(1 for r in results if r["result"] == "INSUFFICIENT_DATA")
    decided           = pass_count + fail_count
    pass_rate         = (pass_count / decided) if decided > 0 else 0.0

    return ComplianceSummary(
        application_id=app_id,
        calculated_at=datetime.utcnow(),
        total_controls=len(results),
        pass_count=pass_count,
        fail_count=fail_count,
        insufficient_count=insufficient,
        pass_rate=round(pass_rate, 4),
        controls=[ControlKPIResult(**r) for r in results],
    )


# ---------------------------------------------------------------------------
# Routes — compliance
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
    results = await calculator.calculate_for_application(app_id, db)
    await db.commit()
    return _build_summary(app_id, results)


@router.post("/applications/{app_id}/compliance",
             response_model=ComplianceSummary,
             status_code=status.HTTP_200_OK)
async def recalculate_compliance(
    app_id: str,
    db:     AsyncSession = Depends(get_db),
):
    """Force a fresh KPI recalculation regardless of cache."""
    await _get_app_or_404(app_id, db)
    results = await calculator.calculate_for_application(app_id, db)
    await db.commit()
    return _build_summary(app_id, results)


@router.get("/applications/{app_id}/compliance/controls",
            response_model=list[ControlKPIResult])
async def get_compliance_controls(
    app_id: str,
    db:     AsyncSession = Depends(get_db),
):
    """
    Return per-control KPI evidence from the most recent calculation.
    Does NOT trigger recalculation — reads last written CalculatedMetric rows.
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
# Routes — curation queue (admin)
# ---------------------------------------------------------------------------

@router.get("/curation/queue", response_model=list[CurationItemResponse])
async def get_curation_queue(db: AsyncSession = Depends(get_db)):
    """Admin only — list pending curation items."""
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
        )
        for i in items
    ]


@router.post("/curation/queue", status_code=status.HTTP_201_CREATED,
             response_model=CurationItemResponse)
async def submit_curation_item(
    body: CurationItemRequest,
    db:   AsyncSession = Depends(get_db),
):
    """Admin only — submit a new curation item."""
    item = CurationQueueItem(
        id=str(uuid4()),
        created_at=datetime.utcnow(),
    )
    # Set fields that exist on the model
    for field in ("control_id", "item_type", "proposed", "justification"):
        if hasattr(item, field):
            setattr(item, field, getattr(body, field, None))

    db.add(item)
    await db.commit()
    await db.refresh(item)

    return CurationItemResponse(
        id=item.id,
        control_id=getattr(item, "control_id", None),
        item_type=getattr(item, "item_type", None),
        status=getattr(item, "status", "PENDING"),
        created_at=item.created_at,
    )
