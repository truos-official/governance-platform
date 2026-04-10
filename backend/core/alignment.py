"""
alignment.py — Alignment Score Engine

Formula (spec §6c):
  control_weight  = (peer_adoption_rate × W1)
                  + (regulatory_density × W2)
                  + (trend_velocity     × W3)

  alignment_score = Σ(adopted_controls  × control_weight)
                  / Σ(applicable_controls × control_weight) × 100

Weights W1/W2/W3 read from alignment_weight_config (admin-configurable).
Score is 0–100, directional, no pass/fail threshold.

Signal sources:
  peer_adoption_rate — fraction of peer apps (same tier) that have adopted
                       each control. Requires N>=3 peers, else uses 0.5 prior.
  regulatory_density — normalised count of requirements linked to each control
                       via control_requirement join table.
  trend_velocity     — quarter-over-quarter adoption change. Returns 0.0 until
                       sufficient historical data exists (Phase 4.8+).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AlignmentWeightConfig,
    Application,
    ControlAssignment,
    ControlRequirement,
)

logger = logging.getLogger(__name__)

PEER_MIN_COHORT   = 3      # minimum peers before using real adoption rate
NEUTRAL_PEER_RATE = 0.5    # prior when cohort < PEER_MIN_COHORT


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ControlWeightDetail:
    control_id:          str
    peer_adoption_rate:  float
    regulatory_density:  float
    trend_velocity:      float
    control_weight:      float
    adopted:             bool


@dataclass
class AlignmentResult:
    application_id:   str
    alignment_score:  float          # 0–100
    calculated_at:    datetime
    weights_config_id: str
    w1_peer:          float
    w2_regulatory:    float
    w3_trend:         float
    peer_cohort_size: int
    controls:         list[ControlWeightDetail]
    commentary:       str


# ---------------------------------------------------------------------------
# Signal calculators
# ---------------------------------------------------------------------------

async def _get_active_weights(db: AsyncSession) -> AlignmentWeightConfig:
    result = await db.execute(
        select(AlignmentWeightConfig)
        .where(AlignmentWeightConfig.is_active.is_(True))
        .order_by(AlignmentWeightConfig.set_at.desc())
        .limit(1)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise RuntimeError("No active alignment weight config — check DB seeding")
    return config


async def _peer_adoption_rates(
    tier:        str,
    control_ids: list[str],
    app_id:      str,
    db:          AsyncSession,
) -> tuple[dict[str, float], int]:
    """
    For each control, calculate the fraction of peer apps (same tier,
    excluding this app) that have adopted it.
    Returns (rates_by_control_id, cohort_size).
    """
    # Count peer apps in same tier (exclude this app)
    peer_count_result = await db.execute(
        select(func.count(Application.id))
        .where(
            Application.current_tier == tier,
            Application.id != app_id,
        )
    )
    peer_count = peer_count_result.scalar() or 0

    if peer_count < PEER_MIN_COHORT:
        # Not enough peers — use neutral prior for all controls
        return {cid: NEUTRAL_PEER_RATE for cid in control_ids}, peer_count

    # Count adopted assignments per control across peers
    rates: dict[str, float] = {}
    for control_id in control_ids:
        adopted_result = await db.execute(
            select(func.count(ControlAssignment.id))
            .join(Application, Application.id == ControlAssignment.application_id)
            .where(
                ControlAssignment.control_id == control_id,
                ControlAssignment.status     == "adopted",
                Application.current_tier     == tier,
                Application.id              != app_id,
            )
        )
        adopted_count = adopted_result.scalar() or 0
        rates[control_id] = adopted_count / peer_count

    return rates, peer_count


async def _regulatory_density_scores(
    control_ids: list[str],
    db:          AsyncSession,
) -> dict[str, float]:
    """
    For each control, count linked requirements via control_requirement.
    Normalize 0–1 against the max count across all controls in the set.
    Returns density score per control_id.
    """
    counts: dict[str, int] = {}
    for control_id in control_ids:
        count_result = await db.execute(
            select(func.count(ControlRequirement.requirement_id))
            .where(ControlRequirement.control_id == control_id)
        )
        counts[control_id] = count_result.scalar() or 0

    max_count = max(counts.values()) if counts else 1
    if max_count == 0:
        return {cid: 0.0 for cid in control_ids}

    return {cid: round(cnt / max_count, 4) for cid, cnt in counts.items()}


def _trend_velocity_scores(control_ids: list[str]) -> dict[str, float]:
    """
    Returns 0.0 for all controls until historical TierPeerAggregate data
    accumulates across quarters. Placeholder for Phase 4.8+.
    """
    return {cid: 0.0 for cid in control_ids}


# ---------------------------------------------------------------------------
# Commentary generator
# ---------------------------------------------------------------------------

def _generate_commentary(
    score:        float,
    controls:     list[ControlWeightDetail],
    peer_cohort:  int,
) -> str:
    adopted   = [c for c in controls if c.adopted]
    unadopted = [c for c in controls if not c.adopted]

    # Find biggest gaps — unadopted controls with highest weight
    top_gaps = sorted(unadopted, key=lambda c: c.control_weight, reverse=True)[:3]

    parts = []

    if score >= 80:
        parts.append(f"Strong alignment at {score:.1f}/100.")
    elif score >= 50:
        parts.append(f"Moderate alignment at {score:.1f}/100.")
    else:
        parts.append(f"Low alignment at {score:.1f}/100.")

    if peer_cohort < PEER_MIN_COHORT:
        parts.append(f"Peer signal uses neutral prior (cohort={peer_cohort}, min={PEER_MIN_COHORT}).")

    if top_gaps:
        gap_ids = ", ".join(c.control_id[:8] + "…" for c in top_gaps)
        parts.append(f"Top adoption gaps: {gap_ids}.")

    parts.append(f"{len(adopted)}/{len(controls)} applicable controls adopted.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def calculate_alignment(
    app:    Application,
    db:     AsyncSession,
) -> AlignmentResult:
    """
    Calculate alignment score for an application.
    Reads active weights from DB. Pull model — call on demand.
    """
    # 1. Load weights
    config = await _get_active_weights(db)
    w1     = config.peer_adoption_rate
    w2     = config.regulatory_density
    w3     = config.trend_velocity

    # 2. Load applicable controls (all assigned, regardless of status)
    assignments_result = await db.execute(
        select(ControlAssignment)
        .where(ControlAssignment.application_id == app.id)
    )
    assignments = assignments_result.scalars().all()

    if not assignments:
        return AlignmentResult(
            application_id=app.id,
            alignment_score=0.0,
            calculated_at=datetime.utcnow(),
            weights_config_id=config.id,
            w1_peer=w1, w2_regulatory=w2, w3_trend=w3,
            peer_cohort_size=0,
            controls=[],
            commentary="No controls assigned to this application.",
        )

    control_ids  = [a.control_id for a in assignments]
    adopted_ids  = {a.control_id for a in assignments if a.status == "adopted"}

    # 3. Calculate signals
    peer_rates, peer_cohort = await _peer_adoption_rates(
        tier=app.current_tier or "Foundation",
        control_ids=control_ids,
        app_id=app.id,
        db=db,
    )
    reg_density  = await _regulatory_density_scores(control_ids, db)
    trend_scores = _trend_velocity_scores(control_ids)

    # 4. Calculate per-control weights and alignment
    control_details: list[ControlWeightDetail] = []
    sum_adopted     = 0.0
    sum_applicable  = 0.0

    for control_id in control_ids:
        pr  = peer_rates.get(control_id, NEUTRAL_PEER_RATE)
        rd  = reg_density.get(control_id, 0.0)
        tv  = trend_scores.get(control_id, 0.0)
        cw  = round((pr * w1) + (rd * w2) + (tv * w3), 6)

        adopted = control_id in adopted_ids
        if adopted:
            sum_adopted += cw
        sum_applicable += cw

        control_details.append(ControlWeightDetail(
            control_id=control_id,
            peer_adoption_rate=pr,
            regulatory_density=rd,
            trend_velocity=tv,
            control_weight=cw,
            adopted=adopted,
        ))

    # 5. Final score
    if sum_applicable > 0:
        score = round((sum_adopted / sum_applicable) * 100, 2)
    else:
        score = 0.0

    commentary = _generate_commentary(score, control_details, peer_cohort)

    return AlignmentResult(
        application_id=app.id,
        alignment_score=score,
        calculated_at=datetime.utcnow(),
        weights_config_id=config.id,
        w1_peer=w1, w2_regulatory=w2, w3_trend=w3,
        peer_cohort_size=peer_cohort,
        controls=control_details,
        commentary=commentary,
    )
