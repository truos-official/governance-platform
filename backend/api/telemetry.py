"""
telemetry.py — OTEL metric ingest and pipeline health

POST /telemetry/ingest  — receives OTLP JSON from otel-collector
                          filters production-only (collector pre-filters,
                          backend double-checks)
                          stores MetricReading rows
                          triggers tier recalculation if override_rate present
GET  /telemetry/status  — ingest pipeline health

OTEL wire format (OTLP JSON):
  { "resourceMetrics": [ {
      "resource": { "attributes": [ {"key": "...", "value": {"stringValue": "..."}} ] },
      "scopeMetrics": [ {
          "metrics": [ {
              "name": "ai.core.error_rate",
              "gauge": { "dataPoints": [ {"asDouble": 0.02, "timeUnixNano": "..."} ] }
          } ]
      } ]
  } ] }
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Application, MetricReading
from db.session import get_db_session as get_db
from core.tier_engine import recalculation_trigger

logger = logging.getLogger(__name__)
router = APIRouter(tags=["telemetry"])


# ---------------------------------------------------------------------------
# OTLP parsing helpers
# ---------------------------------------------------------------------------

def _extract_attr(attributes: list[dict], key: str) -> str | None:
    """Extract a string value from OTLP attribute list."""
    for attr in attributes:
        if attr.get("key") == key:
            val = attr.get("value", {})
            return (
                val.get("stringValue")
                or val.get("intValue")
                or val.get("doubleValue")
            )
    return None


def _extract_datapoint_value(metric: dict) -> float | None:
    """Extract the first numeric value from a metric regardless of type."""
    for metric_type in ("gauge", "sum", "histogram"):
        if metric_type in metric:
            datapoints = metric[metric_type].get("dataPoints", [])
            if datapoints:
                dp = datapoints[0]
                if "asDouble" in dp:
                    return float(dp["asDouble"])
                if "asInt" in dp:
                    return float(dp["asInt"])
                # histogram: use sum/count as rate
                if "sum" in dp and "count" in dp and dp["count"]:
                    return float(dp["sum"]) / float(dp["count"])
    return None


def _extract_datapoint_time(metric: dict) -> datetime:
    """Extract timestamp from first datapoint, fallback to utcnow."""
    for metric_type in ("gauge", "sum", "histogram"):
        if metric_type in metric:
            datapoints = metric[metric_type].get("dataPoints", [])
            if datapoints:
                nano = datapoints[0].get("timeUnixNano")
                if nano:
                    return datetime.utcfromtimestamp(int(nano) / 1e9)
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# OTEL governance metric names we care about for recalculation
# ---------------------------------------------------------------------------

OTEL_ERROR_RATE_KEY    = "ai.core.error_rate"
OTEL_OVERRIDE_RATE_KEY = "ai.oversight.override_rate"
OTEL_DRIFT_SCORE_KEY   = "ai.core.drift_score"


# ---------------------------------------------------------------------------
# Ingest endpoint
# ---------------------------------------------------------------------------

@router.post("/telemetry/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Receive OTLP JSON from otel-collector.
    Store MetricReading rows for production metrics only.
    Trigger tier recalculation when enough OTEL signals are present.
    """
    try:
        body: dict = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    resource_metrics = body.get("resourceMetrics", [])
    stored_count     = 0
    skipped_count    = 0
    recalc_triggered = []

    for rm in resource_metrics:
        resource_attrs = rm.get("resource", {}).get("attributes", [])

        # --- Double-check production filter (collector pre-filters, we verify) ---
        environment = _extract_attr(resource_attrs, "deployment.environment")
        if environment != "production":
            skipped_count += 1
            continue

        # --- Extract mandatory governance attributes ---
        app_id   = _extract_attr(resource_attrs, "governance.application_id")
        division = _extract_attr(resource_attrs, "governance.division")

        if not app_id or not division:
            logger.warning("Dropping metric batch — missing governance resource attributes")
            skipped_count += 1
            continue

        # --- Verify application is registered ---
        app = await db.get(Application, app_id)
        if not app:
            logger.warning(f"Dropping metric batch — unknown application_id: {app_id}")
            skipped_count += 1
            continue

        if app.status != "active":
            logger.warning(f"Dropping metrics for {app.status} application: {app_id}")
            skipped_count += 1
            continue

        # --- Collect metric values for recalculation signals ---
        recalc_signals: dict[str, float] = {}

        for scope_metrics in rm.get("scopeMetrics", []):
            for metric in scope_metrics.get("metrics", []):
                name  = metric.get("name", "")
                value = _extract_datapoint_value(metric)
                if value is None:
                    continue

                collected_at = _extract_datapoint_time(metric)

                reading = MetricReading(
                    id             = str(uuid4()),
                    application_id = app_id,
                    metric_name    = name,
                    value          = value,
                    collected_at   = collected_at,
                    attributes     = {"source": "otel_collector"},
                )
                db.add(reading)
                stored_count += 1

                # Capture signals needed for tier recalculation
                if name == OTEL_ERROR_RATE_KEY:
                    recalc_signals["error_rate"] = value
                elif name == OTEL_OVERRIDE_RATE_KEY:
                    recalc_signals["override_rate"] = value
                elif name == OTEL_DRIFT_SCORE_KEY:
                    recalc_signals["drift_score"] = value

        await db.flush()

        # --- Trigger recalculation if we have override_rate (autonomy validation requires it) ---
        if "override_rate" in recalc_signals:
            try:
                await recalculation_trigger(
                    app=app,
                    db=db,
                    otel_error_rate=recalc_signals.get("error_rate", 0.0),
                    otel_override_rate=recalc_signals["override_rate"],
                    otel_drift_score=recalc_signals.get("drift_score", 0.0),
                )
                recalc_triggered.append(app_id)
            except Exception as e:
                logger.error(f"Tier recalculation failed for {app_id}: {e}")

    await db.commit()

    return {
        "accepted":           True,
        "stored_readings":    stored_count,
        "skipped_batches":    skipped_count,
        "recalc_triggered":   recalc_triggered,
    }


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

@router.get("/telemetry/status")
async def telemetry_status(db: AsyncSession = Depends(get_db)):
    """Pipeline health — reading counts and latest ingest timestamp."""
    total = await db.scalar(select(func.count()).select_from(MetricReading))
    latest = await db.scalar(
        select(func.max(MetricReading.collected_at))
    )
    return {
        "status":          "ok",
        "total_readings":  total or 0,
        "latest_reading":  latest.isoformat() if latest else None,
        "production_only": True,
    }
