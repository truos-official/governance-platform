"""
kpi_calculator.py — KPI Calculator

Pull model: calculated on-demand when dashboard loads. Never pre-scheduled.

For each adopted control assigned to an application:
  1. Find linked ControlMetricDefinition rows
  2. Pull latest MetricReading from TimescaleDB hypertable
  3. Evaluate threshold → PASS / FAIL / INSUFFICIENT_DATA
  4. Write CalculatedMetric row
  5. If is_manual=True → create ControlCalculationProposal (PENDING)

Threshold JSON schema (stored in control_metric_definition.threshold):
  { "operator": "lte" | "gte" | "lt" | "gt" | "eq", "value": <float> }
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Application,
    CalculatedMetric,
    ControlAssignment,
    ControlCalculationProposal,
    ControlMetricDefinition,
    MetricReading,
)

logger = logging.getLogger(__name__)

PASS              = "PASS"
FAIL              = "FAIL"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Threshold evaluation
# ---------------------------------------------------------------------------

def _evaluate_threshold(value: float, threshold: dict) -> str:
    """
    Evaluate a metric value against a threshold definition.

    Threshold format: {"operator": "lte", "value": 0.05}
    Operators: lte, gte, lt, gt, eq
    Returns PASS or FAIL.
    """
    operator      = threshold.get("operator", "lte")
    target: float = float(threshold.get("value", 0))

    ops = {
        "lte": value <= target,
        "gte": value >= target,
        "lt":  value <  target,
        "gt":  value >  target,
        "eq":  abs(value - target) < 1e-9,
    }

    result = ops.get(operator)
    if result is None:
        logger.warning(f"Unknown threshold operator: {operator} — defaulting to FAIL")
        return FAIL

    return PASS if result else FAIL


# ---------------------------------------------------------------------------
# Main calculator
# ---------------------------------------------------------------------------

class KPICalculator:

    PASS              = PASS
    FAIL              = FAIL
    INSUFFICIENT_DATA = INSUFFICIENT_DATA

    async def calculate_for_application(
        self,
        app_id: str,
        db:     AsyncSession,
    ) -> list[dict]:
        """
        Calculate KPIs for all adopted controls assigned to the application.

        Returns list of:
          {
            control_id, metric_name, result,
            value, threshold, evidence_ts, is_manual
          }
        """
        # 1. Load adopted control assignments
        assignments_result = await db.execute(
            select(ControlAssignment)
            .where(
                ControlAssignment.application_id == app_id,
                ControlAssignment.status == "adopted",
            )
        )
        assignments = assignments_result.scalars().all()

        if not assignments:
            logger.info(f"No adopted controls for application {app_id}")
            return []

        control_ids = [a.control_id for a in assignments]

        # 2. Load all metric definitions for these controls
        defs_result = await db.execute(
            select(ControlMetricDefinition)
            .where(ControlMetricDefinition.control_id.in_(control_ids))
        )
        metric_defs = defs_result.scalars().all()

        results = []

        for mdef in metric_defs:
            result_entry = await self._calculate_single(
                app_id=app_id,
                mdef=mdef,
                db=db,
            )
            results.append(result_entry)

        return results

    async def _calculate_single(
        self,
        app_id: str,
        mdef:   ControlMetricDefinition,
        db:     AsyncSession,
    ) -> dict:
        """Calculate KPI for a single ControlMetricDefinition."""

        # 3. Pull latest MetricReading for this app + metric_name
        reading_result = await db.execute(
            select(MetricReading)
            .where(
                MetricReading.application_id == app_id,
                MetricReading.metric_name    == mdef.metric_name,
            )
            .order_by(desc(MetricReading.collected_at))
            .limit(1)
        )
        reading: Optional[MetricReading] = reading_result.scalar_one_or_none()

        # 4. Evaluate threshold
        if reading is None:
            kpi_result = INSUFFICIENT_DATA
            value      = None
            evidence_ts = None
        else:
            value       = reading.value
            evidence_ts = reading.collected_at
            if mdef.is_manual:
                # Manual controls — reading exists but needs human confirmation
                kpi_result = INSUFFICIENT_DATA
            else:
                kpi_result = _evaluate_threshold(value, mdef.threshold or {})

        # 5. Write CalculatedMetric row
        calculated = CalculatedMetric(
            id             = str(uuid4()),
            application_id = app_id,
            control_id     = mdef.control_id,
            metric_name    = mdef.metric_name,
            result         = kpi_result,
            value          = value,
            calculated_at  = datetime.utcnow(),
        )
        db.add(calculated)

        # 6. Create ControlCalculationProposal for manual controls
        if mdef.is_manual and value is not None:
            proposal = ControlCalculationProposal(
                id             = str(uuid4()),
                control_id     = mdef.control_id,
                application_id = app_id,
                proposed_value = {
                    "metric_name": mdef.metric_name,
                    "value":       value,
                    "threshold":   mdef.threshold,
                    "evidence_ts": evidence_ts.isoformat() if evidence_ts else None,
                },
                status     = "PENDING",
                created_at = datetime.utcnow(),
            )
            db.add(proposal)

        await db.flush()

        return {
            "control_id":   mdef.control_id,
            "metric_name":  mdef.metric_name,
            "result":       kpi_result,
            "value":        value,
            "threshold":    mdef.threshold,
            "evidence_ts":  evidence_ts.isoformat() if evidence_ts else None,
            "is_manual":    mdef.is_manual,
        }

    def _evaluate_metric(self, metric_name: str, value: float, threshold: dict) -> str:
        """Public wrapper — kept for interface compatibility with stub."""
        return _evaluate_threshold(value, threshold)
