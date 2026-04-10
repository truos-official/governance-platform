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
OTEL_FINOPS_COST_KEY   = "ai.resources.compute_cost"
OTEL_FINOPS_TOKEN_KEY  = "ai.resources.token_usage"
OTEL_FINOPS_USERS_KEY  = "ai.resources.active_users"
OTEL_FINOPS_COST_PER_TOKEN_KEY = "ai.resources.cost_per_token"
OTEL_FRONTIER_MODEL_COUNT_KEY  = "ai.resources.frontier_model_count"

TOKEN_METRIC_NAME_ALIASES = {
    OTEL_FINOPS_TOKEN_KEY,
    "gen_ai.usage.total_tokens",
    "llm.total_tokens",
    "openai.total_tokens",
    "total_tokens",
}
TOKEN_ATTRIBUTE_TOTAL_KEYS = [
    "total_tokens",
    "usage.total_tokens",
    "gen_ai.usage.total_tokens",
    "token_usage",
]
TOKEN_ATTRIBUTE_PROMPT_KEYS = ["prompt_tokens", "usage.prompt_tokens"]
TOKEN_ATTRIBUTE_COMPLETION_KEYS = ["completion_tokens", "usage.completion_tokens"]

COST_METRIC_NAME_ALIASES = {
    OTEL_FINOPS_COST_KEY,
    "gen_ai.usage.cost_usd",
    "llm.total_cost_usd",
    "openai.cost_usd",
    "total_cost_usd",
}
COST_ATTRIBUTE_KEYS = [
    "total_cost_usd",
    "cost_usd",
    "usage.cost_usd",
    "gen_ai.usage.cost_usd",
    "llm_cost_usd",
]

ACTIVE_USERS_METRIC_NAME_ALIASES = {
    OTEL_FINOPS_USERS_KEY,
    "app.active_users",
    "gen_ai.usage.active_users",
}
ACTIVE_USERS_ATTRIBUTE_KEYS = ["active_users", "user_count", "distinct_users"]
ACTIVE_USER_ID_ATTRIBUTE_KEYS = [
    "user_id",
    "enduser.id",
    "user.email",
    "session.user_id",
]

FRONTIER_COUNT_METRIC_NAME_ALIASES = {
    OTEL_FRONTIER_MODEL_COUNT_KEY,
    "gen_ai.usage.frontier_model_count",
    "ai.model.frontier_count",
}
FRONTIER_COUNT_ATTRIBUTE_KEYS = [
    "frontier_model_count",
    "frontier_count",
]
FRONTIER_FLAG_ATTRIBUTE_KEYS = [
    "is_frontier_model",
    "model.is_frontier",
    "frontier_model",
]
MODEL_NAME_ATTRIBUTE_KEYS = [
    "model.name",
    "model_name",
    "gen_ai.model.name",
    "llm.model",
]
KNOWN_FRONTIER_MODEL_TOKENS = [
    "gpt-5",
    "gpt-4.1",
    "gpt-4o",
    "claude-opus",
    "claude-3.7",
    "gemini-1.5-pro",
    "gemini-2.0",
]


def _extract_attr_typed(attributes: list[dict], key: str) -> Any:
    for attr in attributes:
        if attr.get("key") != key:
            continue
        val = attr.get("value", {})
        if "doubleValue" in val:
            return float(val["doubleValue"])
        if "intValue" in val:
            return float(val["intValue"])
        if "boolValue" in val:
            return bool(val["boolValue"])
        if "stringValue" in val:
            return val["stringValue"]
        return None
    return None


def _extract_datapoint(metric: dict) -> dict | None:
    for metric_type in ("gauge", "sum", "histogram"):
        if metric_type in metric:
            datapoints = metric[metric_type].get("dataPoints", [])
            if datapoints:
                return datapoints[0]
    return None


def _datapoint_attributes(metric: dict) -> dict[str, Any]:
    dp = _extract_datapoint(metric)
    if not dp:
        return {}
    attrs = dp.get("attributes", []) or []
    parsed: dict[str, Any] = {}
    for attr in attrs:
        key = attr.get("key")
        if not key:
            continue
        value = attr.get("value", {})
        if "doubleValue" in value:
            parsed[key] = float(value["doubleValue"])
        elif "intValue" in value:
            parsed[key] = float(value["intValue"])
        elif "boolValue" in value:
            parsed[key] = bool(value["boolValue"])
        elif "stringValue" in value:
            parsed[key] = value["stringValue"]
    return parsed


def _first_numeric_value(values: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        raw = values.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return None


def _extract_model_name(attrs: dict[str, Any]) -> str | None:
    for key in MODEL_NAME_ATTRIBUTE_KEYS:
        raw = attrs.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return None


def _looks_like_frontier_model(model_name: str | None) -> bool:
    if not model_name:
        return False
    lower = model_name.strip().lower()
    return any(token in lower for token in KNOWN_FRONTIER_MODEL_TOKENS)


def _derive_finops_metrics(metric_name: str, value: float, attrs: dict[str, Any]) -> dict[str, float]:
    derived: dict[str, float] = {}

    if metric_name in TOKEN_METRIC_NAME_ALIASES:
        derived[OTEL_FINOPS_TOKEN_KEY] = float(value)
    if metric_name in COST_METRIC_NAME_ALIASES:
        derived[OTEL_FINOPS_COST_KEY] = float(value)
    if metric_name in ACTIVE_USERS_METRIC_NAME_ALIASES:
        derived[OTEL_FINOPS_USERS_KEY] = float(value)

    total_tokens = _first_numeric_value(attrs, TOKEN_ATTRIBUTE_TOTAL_KEYS)
    if total_tokens is not None:
        derived[OTEL_FINOPS_TOKEN_KEY] = total_tokens
    else:
        prompt_tokens = _first_numeric_value(attrs, TOKEN_ATTRIBUTE_PROMPT_KEYS)
        completion_tokens = _first_numeric_value(attrs, TOKEN_ATTRIBUTE_COMPLETION_KEYS)
        if prompt_tokens is not None and completion_tokens is not None:
            derived[OTEL_FINOPS_TOKEN_KEY] = prompt_tokens + completion_tokens

    cost_value = _first_numeric_value(attrs, COST_ATTRIBUTE_KEYS)
    if cost_value is not None:
        derived[OTEL_FINOPS_COST_KEY] = cost_value

    active_users = _first_numeric_value(attrs, ACTIVE_USERS_ATTRIBUTE_KEYS)
    if active_users is not None:
        derived[OTEL_FINOPS_USERS_KEY] = active_users
    else:
        user_id = next((attrs.get(k) for k in ACTIVE_USER_ID_ATTRIBUTE_KEYS if attrs.get(k)), None)
        if user_id:
            # Per-event user identity fallback (treated as one active user signal).
            derived[OTEL_FINOPS_USERS_KEY] = 1.0

    return derived


def _build_metric_attributes(base_attrs: dict[str, Any], *, derived_from: str | None = None) -> dict[str, Any]:
    attrs = {"source": "otel_collector"}
    attrs.update(base_attrs or {})
    if derived_from:
        attrs["derived_from"] = derived_from
    return attrs


def _new_metric_reading(
    *,
    app_id: str,
    metric_name: str,
    value: float,
    collected_at: datetime,
    attributes: dict[str, Any],
) -> MetricReading:
    return MetricReading(
        id=str(uuid4()),
        application_id=app_id,
        metric_name=metric_name,
        value=float(value),
        collected_at=collected_at,
        attributes=attributes,
    )


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

        # --- Collect metric values for recalculation + batch-level FinOps derivations ---
        recalc_signals: dict[str, float] = {}
        batch_cost_value: float | None = None
        batch_token_value: float | None = None
        batch_latest_collected_at: datetime | None = None
        batch_frontier_models: set[str] = set()
        batch_frontier_count_value: float | None = None

        for scope_metrics in rm.get("scopeMetrics", []):
            for metric in scope_metrics.get("metrics", []):
                name  = metric.get("name", "")
                value = _extract_datapoint_value(metric)
                if value is None:
                    continue

                collected_at = _extract_datapoint_time(metric)
                dp_attrs = _datapoint_attributes(metric)

                reading = _new_metric_reading(
                    app_id=app_id,
                    metric_name=name,
                    value=value,
                    collected_at=collected_at,
                    attributes=_build_metric_attributes(dp_attrs),
                )
                db.add(reading)
                stored_count += 1

                finops_values = _derive_finops_metrics(name, value, dp_attrs)
                for finops_metric_name, finops_value in finops_values.items():
                    if finops_metric_name == name:
                        continue
                    derived_reading = _new_metric_reading(
                        app_id=app_id,
                        metric_name=finops_metric_name,
                        value=finops_value,
                        collected_at=collected_at,
                        attributes=_build_metric_attributes(dp_attrs, derived_from=name),
                    )
                    db.add(derived_reading)
                    stored_count += 1
                    if finops_metric_name == OTEL_FINOPS_COST_KEY:
                        batch_cost_value = finops_value
                    elif finops_metric_name == OTEL_FINOPS_TOKEN_KEY:
                        batch_token_value = finops_value

                if name == OTEL_FINOPS_COST_KEY:
                    batch_cost_value = float(value)
                elif name == OTEL_FINOPS_TOKEN_KEY:
                    batch_token_value = float(value)

                frontier_count_from_attrs = _first_numeric_value(dp_attrs, FRONTIER_COUNT_ATTRIBUTE_KEYS)
                if name in FRONTIER_COUNT_METRIC_NAME_ALIASES:
                    batch_frontier_count_value = float(value)
                elif frontier_count_from_attrs is not None:
                    batch_frontier_count_value = float(frontier_count_from_attrs)

                model_name = _extract_model_name(dp_attrs)
                frontier_flag = next(
                    (_coerce_bool(dp_attrs.get(key)) for key in FRONTIER_FLAG_ATTRIBUTE_KEYS if key in dp_attrs),
                    None,
                )
                if (frontier_flag is True) or _looks_like_frontier_model(model_name):
                    batch_frontier_models.add(model_name or "frontier-model")

                if batch_latest_collected_at is None or collected_at > batch_latest_collected_at:
                    batch_latest_collected_at = collected_at

                # Capture signals needed for tier recalculation
                if name == OTEL_ERROR_RATE_KEY:
                    recalc_signals["error_rate"] = value
                elif name == OTEL_OVERRIDE_RATE_KEY:
                    recalc_signals["override_rate"] = value
                elif name == OTEL_DRIFT_SCORE_KEY:
                    recalc_signals["drift_score"] = value

        if batch_latest_collected_at is None:
            batch_latest_collected_at = datetime.utcnow()

        if batch_cost_value is not None and batch_token_value is not None and batch_token_value > 0:
            cost_per_token = batch_cost_value / batch_token_value
            db.add(
                _new_metric_reading(
                    app_id=app_id,
                    metric_name=OTEL_FINOPS_COST_PER_TOKEN_KEY,
                    value=cost_per_token,
                    collected_at=batch_latest_collected_at,
                    attributes=_build_metric_attributes(
                        {
                            "derived_from": f"{OTEL_FINOPS_COST_KEY},{OTEL_FINOPS_TOKEN_KEY}",
                            "source": "otel_collector",
                        }
                    ),
                )
            )
            stored_count += 1

        derived_frontier_count: float | None = None
        if batch_frontier_count_value is not None:
            derived_frontier_count = max(0.0, float(batch_frontier_count_value))
        elif batch_frontier_models:
            derived_frontier_count = float(len(batch_frontier_models))

        if derived_frontier_count is not None:
            db.add(
                _new_metric_reading(
                    app_id=app_id,
                    metric_name=OTEL_FRONTIER_MODEL_COUNT_KEY,
                    value=derived_frontier_count,
                    collected_at=batch_latest_collected_at,
                    attributes=_build_metric_attributes(
                        {
                            "source": "otel_collector",
                            "derived_from": "frontier_model_attributes",
                        }
                    ),
                )
            )
            stored_count += 1

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
