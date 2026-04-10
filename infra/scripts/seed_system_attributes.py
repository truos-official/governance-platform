"""
Seed approved_system_attributes with initial field picker values.

Groups:
  A) OTEL metrics discovered from control_metric_definition + metric_reading
  B) application table fields
  C) derived/calculated system attributes

Run:
  python infra/scripts/seed_system_attributes.py
"""
from __future__ import annotations

import asyncio
import os
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DEFAULT_DB_URL = "postgresql+asyncpg://aigov:localdev@localhost:5432/aigov"


def _new_id() -> str:
    return str(uuid.uuid4())


def _infer_metric_data_type(metric_name: str) -> str:
    low = metric_name.lower()
    if "rate" in low or "score" in low:
        return "ratio"
    if "percent" in low or low.endswith("_pct"):
        return "percentage"
    if "count" in low or "total" in low:
        return "integer"
    return "float"


def _infer_metric_unit(metric_name: str, data_type: str) -> str:
    low = metric_name.lower()
    if "latency" in low:
        return "ms"
    if "cost" in low:
        return "USD"
    if data_type == "ratio":
        return "ratio 0-1"
    if data_type == "percentage":
        return "percentage 0-100"
    return ""


APPLICATION_FIELDS = [
    ("ai_system_type", "application_field", "string", "", "RAG"),
    ("domain", "application_field", "string", "", "healthcare"),
    ("decision_type", "application_field", "string", "", "binding"),
    ("autonomy_level", "application_field", "string", "", "human_in_the_loop"),
    ("population_breadth", "application_field", "string", "", "regional"),
    ("affected_populations", "application_field", "string", "", "adults"),
    ("consent_scope", "application_field", "string", "", "explicit"),
    ("current_tier", "application_field", "string", "", "High"),
    ("registered_at", "application_field", "string", "datetime", "2026-04-09T12:00:00Z"),
    ("status", "application_field", "string", "", "active"),
]

DERIVED_FIELDS = [
    ("peer_adoption_rate", "calculated", "ratio", "ratio 0-1", "0.62"),
    ("regulatory_density", "calculated", "float", "", "0.74"),
    ("alignment_score", "calculated", "float", "0-100", "71.2"),
    ("tier_raw_score", "calculated", "float", "0-100", "66.5"),
    ("compliance_pass_rate", "calculated", "ratio", "ratio 0-1", "0.81"),
    ("days_since_registered", "calculated", "integer", "days", "45"),
]


UPSERT_SQL = text(
    """
    INSERT INTO approved_system_attributes (
        id,
        attribute_name,
        source,
        description,
        data_type,
        unit,
        example_value,
        is_active,
        added_by,
        added_at
    )
    VALUES (
        :id,
        :attribute_name,
        :source,
        :description,
        :data_type,
        :unit,
        :example_value,
        true,
        :added_by,
        now()
    )
    ON CONFLICT (attribute_name) DO UPDATE
    SET
        source = EXCLUDED.source,
        description = EXCLUDED.description,
        data_type = EXCLUDED.data_type,
        unit = EXCLUDED.unit,
        example_value = EXCLUDED.example_value,
        is_active = true,
        added_by = EXCLUDED.added_by
    """
)


async def _seed_otel_metrics(conn) -> int:
    result = await conn.execute(
        text(
            """
            SELECT DISTINCT metric_name
            FROM (
                SELECT metric_name FROM control_metric_definition
                UNION
                SELECT metric_name FROM metric_reading
            ) m
            WHERE metric_name IS NOT NULL
            ORDER BY metric_name
            """
        )
    )
    metrics = [row[0] for row in result.fetchall() if row[0]]
    count = 0
    for metric_name in metrics:
        data_type = _infer_metric_data_type(metric_name)
        unit = _infer_metric_unit(metric_name, data_type)
        await conn.execute(
            UPSERT_SQL,
            {
                "id": _new_id(),
                "attribute_name": metric_name,
                "source": "otel_metric",
                "description": f"OTEL metric '{metric_name}' used for governance calculations.",
                "data_type": data_type,
                "unit": unit,
                "example_value": "0.05",
                "added_by": "system_seed",
            },
        )
        count += 1
    return count


async def _seed_static_group(conn, rows: list[tuple[str, str, str, str, str]], description_prefix: str) -> int:
    count = 0
    for attribute_name, source, data_type, unit, example in rows:
        await conn.execute(
            UPSERT_SQL,
            {
                "id": _new_id(),
                "attribute_name": attribute_name,
                "source": source,
                "description": f"{description_prefix}: {attribute_name}",
                "data_type": data_type,
                "unit": unit,
                "example_value": example,
                "added_by": "system_seed",
            },
        )
        count += 1
    return count


async def main() -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    engine = create_async_engine(db_url, future=True)
    try:
        async with engine.begin() as conn:
            metric_count = await _seed_otel_metrics(conn)
            app_count = await _seed_static_group(
                conn,
                APPLICATION_FIELDS,
                "Application registration field",
            )
            derived_count = await _seed_static_group(
                conn,
                DERIVED_FIELDS,
                "Derived system attribute",
            )
            print(
                f"Seeded approved_system_attributes: "
                f"otel_metrics={metric_count}, application_fields={app_count}, derived={derived_count}"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
