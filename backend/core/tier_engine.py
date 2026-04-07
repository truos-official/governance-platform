"""
tier_engine.py — Risk Tier Engine

Two entry points:
  registration_trigger  — uses declared fields only, OTEL dimensions use neutral priors
  recalculation_trigger — called by telemetry ingest, updates OTEL-fed likelihood
                          and applies autonomy validation floor rule

Tier thresholds (spec §6b):
  High       >= 65
  Common     >= 35
  Foundation  < 35

Floor rules (applied after score math, order-independent):
  Rule 1 — Domain floor:     deployment_domain in HIGH_RISK_DOMAINS → minimum High
  Rule 2 — Autonomy floor:   autonomy_level == human_in_the_loop
                             AND observed override_rate < 0.001 → minimum High
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from db.models import Application, TierChangeEvent


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HIGH_RISK_DOMAINS = {
    "asylum",
    "criminal_justice",
    "medical_diagnosis",
    "biometric_id",
}

AUTONOMY_OVERRIDE_THRESHOLD = 0.001  # 0.1%

NEUTRAL_LIKELIHOOD_SCORE = 50  # prior when no OTEL data available


# ---------------------------------------------------------------------------
# Dimension scoring tables
# ---------------------------------------------------------------------------

DEPLOYMENT_DOMAIN_SCORES: dict[str, int] = {
    "asylum":             100,
    "criminal_justice":   100,
    "medical_diagnosis":  100,
    "biometric_id":       100,
    "healthcare":          80,
    "financial":           70,
    "hr":                  60,
    "education":           50,
    "internal_ops":        30,
    "other":               40,
}

DECISION_TYPE_SCORES: dict[str, int] = {
    "binding":       90,
    "advisory":      50,
    "informational": 20,
}

AUTONOMY_LEVEL_SCORES: dict[str, int] = {
    "human_out_of_loop": 100,
    "human_on_loop":      65,
    "human_in_the_loop":  30,
}

POPULATION_BREADTH_SCORES: dict[str, int] = {
    "global":   100,
    "national":  75,
    "regional":  50,
    "local":     25,
}

AFFECTED_POPULATIONS_SCORES: dict[str, int] = {
    "vulnerable": 100,
    "mixed":       60,
    "general":     30,
}


# ---------------------------------------------------------------------------
# Weights (must sum to 1.0)
# ---------------------------------------------------------------------------

WEIGHTS = {
    "deployment_domain":     0.30,
    "decision_type":         0.25,
    "autonomy_level":        0.20,
    "population_breadth":    0.10,
    "affected_populations":  0.10,
    "likelihood":            0.05,
}


# ---------------------------------------------------------------------------
# Tier enum
# ---------------------------------------------------------------------------

class Tier(str, enum.Enum):
    FOUNDATION = "Foundation"
    COMMON     = "Common"
    HIGH       = "High"

    @classmethod
    def from_score(cls, score: float) -> "Tier":
        if score >= 65:
            return cls.HIGH
        if score >= 35:
            return cls.COMMON
        return cls.FOUNDATION

    def __gt__(self, other: "Tier") -> bool:
        order = {Tier.FOUNDATION: 0, Tier.COMMON: 1, Tier.HIGH: 2}
        return order[self] > order[other]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class TierResult:
    raw_score:    float
    final_tier:   Tier
    floor_rule:   Optional[str]  # "domain_floor" | "autonomy_floor" | None
    dimensions:   dict[str, float]  # dimension name → weighted contribution
    calculated_at: datetime


# ---------------------------------------------------------------------------
# Core scoring
# ---------------------------------------------------------------------------

def _score_dimensions(app: Application, likelihood_score: int) -> tuple[float, dict]:
    """Compute weighted score from dimension values. Returns (total, breakdown)."""
    domain_score      = DEPLOYMENT_DOMAIN_SCORES.get(app.domain or "other", 40)
    decision_score    = DECISION_TYPE_SCORES.get(app.decision_type, 50)
    autonomy_score    = AUTONOMY_LEVEL_SCORES.get(app.autonomy_level, 50)
    breadth_score     = POPULATION_BREADTH_SCORES.get(app.population_breadth, 25)
    population_score  = AFFECTED_POPULATIONS_SCORES.get(app.affected_populations, 30)

    breakdown = {
        "deployment_domain":    round(domain_score     * WEIGHTS["deployment_domain"],     2),
        "decision_type":        round(decision_score   * WEIGHTS["decision_type"],         2),
        "autonomy_level":       round(autonomy_score   * WEIGHTS["autonomy_level"],        2),
        "population_breadth":   round(breadth_score    * WEIGHTS["population_breadth"],    2),
        "affected_populations": round(population_score * WEIGHTS["affected_populations"],  2),
        "likelihood":           round(likelihood_score * WEIGHTS["likelihood"],            2),
    }

    total = sum(breakdown.values())
    return round(total, 4), breakdown


def _apply_floor_rules(
    app: Application,
    score_tier: Tier,
    override_rate: Optional[float],
) -> tuple[Tier, Optional[str]]:
    """Apply floor rules after score math. Returns (final_tier, floor_reason)."""
    final_tier  = score_tier
    floor_rule  = None

    # Rule 1 — Domain floor
    if (app.domain or "").lower() in HIGH_RISK_DOMAINS:
        if Tier.HIGH > final_tier:
            final_tier = Tier.HIGH
            floor_rule = "domain_floor"

    # Rule 2 — Autonomy validation floor (recalculation only — requires OTEL data)
    if override_rate is not None:
        if (
            app.autonomy_level == "human_in_the_loop"
            and override_rate < AUTONOMY_OVERRIDE_THRESHOLD
        ):
            if Tier.HIGH > final_tier:
                final_tier = Tier.HIGH
                floor_rule = "autonomy_floor"

    return final_tier, floor_rule


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

async def _persist_tier_result(
    app: Application,
    result: TierResult,
    db: AsyncSession,
) -> None:
    """Write TierChangeEvent and update Application.current_tier."""
    event = TierChangeEvent(
        id             = str(uuid4()),
        application_id = app.id,
        previous_tier  = app.current_tier,
        new_tier       = result.final_tier.value,
        reason         = (
            f"score={result.raw_score:.2f} "
            f"floor={result.floor_rule or 'none'} "
            f"dims={result.dimensions}"
        ),
        changed_at     = result.calculated_at,
    )
    db.add(event)

    await db.execute(
        update(Application)
        .where(Application.id == app.id)
        .values(current_tier=result.final_tier.value)
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

async def registration_trigger(
    app: Application,
    db: AsyncSession,
) -> TierResult:
    """
    Score using declared fields only.
    OTEL likelihood dimension uses neutral prior (50).
    Floor rules: domain floor only (no OTEL data yet for autonomy check).
    """
    raw_score, breakdown = _score_dimensions(app, NEUTRAL_LIKELIHOOD_SCORE)
    score_tier           = Tier.from_score(raw_score)
    final_tier, floor_rule = _apply_floor_rules(app, score_tier, override_rate=None)

    result = TierResult(
        raw_score      = raw_score,
        final_tier     = final_tier,
        floor_rule     = floor_rule,
        dimensions     = breakdown,
        calculated_at  = datetime.utcnow(),
    )

    await _persist_tier_result(app, result, db)
    return result


async def recalculation_trigger(
    app: Application,
    db: AsyncSession,
    otel_error_rate:    float,
    otel_override_rate: float,
    otel_drift_score:   float,
) -> TierResult:
    """
    Score using declared fields + live OTEL signals.
    Likelihood score derived from OTEL inputs.
    Autonomy validation floor rule applied if override_rate data present.
    """
    # Map OTEL signals to likelihood score (0-100, higher = riskier)
    likelihood_score = int(
        (otel_error_rate * 40)
        + (otel_drift_score * 40)
        + ((1 - min(otel_override_rate, 1.0)) * 20)
    )
    likelihood_score = max(0, min(100, likelihood_score))

    raw_score, breakdown = _score_dimensions(app, likelihood_score)
    score_tier           = Tier.from_score(raw_score)
    final_tier, floor_rule = _apply_floor_rules(
        app, score_tier, override_rate=otel_override_rate
    )

    result = TierResult(
        raw_score      = raw_score,
        final_tier     = final_tier,
        floor_rule     = floor_rule,
        dimensions     = breakdown,
        calculated_at  = datetime.utcnow(),
    )

    await _persist_tier_result(app, result, db)
    return result
