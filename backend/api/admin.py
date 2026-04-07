"""
admin.py — Admin-only configuration endpoints

GET  /admin/alignment-weights         — current active config + full history
POST /admin/alignment-weights         — set new weights (admin only, sum must = 1.0)

Weight config is immutable — each POST creates a new row.
Full history retained for audit. Active config = latest is_active=True row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, validator
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AlignmentWeightConfig, TierPeerAggregate, MetricReading, Application
from db.session import get_db_session as get_db

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AlignmentWeightEntry(BaseModel):
    id:                 str
    peer_adoption_rate: float
    regulatory_density: float
    trend_velocity:     float
    set_by:             str
    set_at:             datetime
    reason:             Optional[str]
    is_active:          bool


class AlignmentWeightRequest(BaseModel):
    peer_adoption_rate: float
    regulatory_density: float
    trend_velocity:     float
    set_by:             str
    reason:             Optional[str] = None

    @validator("trend_velocity")
    def weights_must_sum_to_one(cls, trend_velocity, values):
        peer   = values.get("peer_adoption_rate", 0)
        reg    = values.get("regulatory_density", 0)
        total  = round(peer + reg + trend_velocity, 6)
        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"Weights must sum to 1.0 — got {total} "
                f"(peer={peer}, regulatory={reg}, trend={trend_velocity})"
            )
        return trend_velocity

    @validator("peer_adoption_rate", "regulatory_density", "trend_velocity")
    def weight_must_be_positive(cls, v):
        if v < 0 or v > 1:
            raise ValueError(f"Each weight must be between 0.0 and 1.0 — got {v}")
        return v


class AlignmentWeightResponse(BaseModel):
    active:  AlignmentWeightEntry
    history: list[AlignmentWeightEntry]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _to_entry(row: AlignmentWeightConfig) -> AlignmentWeightEntry:
    return AlignmentWeightEntry(
        id=row.id,
        peer_adoption_rate=row.peer_adoption_rate,
        regulatory_density=row.regulatory_density,
        trend_velocity=row.trend_velocity,
        set_by=row.set_by,
        set_at=row.set_at,
        reason=row.reason,
        is_active=row.is_active,
    )


async def get_active_weights(db: AsyncSession) -> AlignmentWeightConfig:
    """Fetch the current active weight config. Used by alignment engine."""
    result = await db.execute(
        select(AlignmentWeightConfig)
        .where(AlignmentWeightConfig.is_active == True)
        .order_by(AlignmentWeightConfig.set_at.desc())
        .limit(1)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            status_code=500,
            detail="No active alignment weight config found — check DB seeding"
        )
    return config


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/admin/alignment-weights", response_model=AlignmentWeightResponse)
async def get_alignment_weights(db: AsyncSession = Depends(get_db)):
    """Return current active weights and full history."""
    active = await get_active_weights(db)

    history_result = await db.execute(
        select(AlignmentWeightConfig)
        .order_by(AlignmentWeightConfig.set_at.desc())
    )
    history = history_result.scalars().all()

    return AlignmentWeightResponse(
        active=_to_entry(active),
        history=[_to_entry(h) for h in history],
    )


@router.post("/admin/alignment-weights",
             response_model=AlignmentWeightEntry,
             status_code=status.HTTP_201_CREATED)
async def set_alignment_weights(
    body: AlignmentWeightRequest,
    db:   AsyncSession = Depends(get_db),
):
    """
    Admin only — set new alignment weights.
    Creates an immutable audit record. Previous config remains in history.
    Deactivates all previous active configs.
    """
    # Deactivate current active config
    current = await db.execute(
        select(AlignmentWeightConfig)
        .where(AlignmentWeightConfig.is_active == True)
    )
    for row in current.scalars().all():
        row.is_active = False

    # Insert new config
    new_config = AlignmentWeightConfig(
        id=str(uuid4()),
        peer_adoption_rate=body.peer_adoption_rate,
        regulatory_density=body.regulatory_density,
        trend_velocity=body.trend_velocity,
        set_by=body.set_by,
        set_at=datetime.utcnow(),
        reason=body.reason,
        is_active=True,
    )
    db.add(new_config)
    await db.commit()
    await db.refresh(new_config)

    return _to_entry(new_config)


@router.post("/admin/refresh-peer-aggregates", status_code=status.HTTP_200_OK)
async def refresh_peer_aggregates(db: AsyncSession = Depends(get_db)):
    """
    Admin only — refresh TierPeerAggregate materialized table.
    Aggregates metric medians per tier from MetricReading table.
    Replaces all existing rows. Call after significant new telemetry is ingested.
    """
    # Delete existing aggregates
    await db.execute(delete(TierPeerAggregate))

    # Get all tiers that have apps
    tiers_result = await db.execute(
        select(Application.current_tier)
        .where(Application.current_tier != None)
        .distinct()
    )
    tiers = [r[0] for r in tiers_result.fetchall()]

    inserted = 0
    for tier in tiers:
        # Get all app IDs in this tier
        apps_result = await db.execute(
            select(Application.id)
            .where(Application.current_tier == tier)
        )
        app_ids = [r[0] for r in apps_result.fetchall()]
        if not app_ids:
            continue

        # Get distinct metric names for this tier
        metrics_result = await db.execute(
            select(MetricReading.metric_name)
            .where(MetricReading.application_id.in_(app_ids))
            .distinct()
        )
        metric_names = [r[0] for r in metrics_result.fetchall()]

        for metric_name in metric_names:
            # Calculate average value across all apps in tier
            avg_result = await db.execute(
                select(func.avg(MetricReading.value))
                .where(
                    MetricReading.application_id.in_(app_ids),
                    MetricReading.metric_name == metric_name,
                )
            )
            avg_value = avg_result.scalar()
            if avg_value is None:
                continue

            aggregate = TierPeerAggregate(
                id=str(uuid4()),
                tier=tier,
                metric_name=metric_name,
                avg_value=round(float(avg_value), 6),
                peer_count=len(app_ids),
                refreshed_at=datetime.utcnow(),
            )
            db.add(aggregate)
            inserted += 1

    await db.commit()
    return {
        "refreshed": True,
        "tiers_processed": len(tiers),
        "aggregates_written": inserted,
        "refreshed_at": datetime.utcnow().isoformat(),
    }
