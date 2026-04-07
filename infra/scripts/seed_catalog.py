"""
Seed the AI Governance Platform database from the Excel dataset.

Loads: data/UN_AI_Governance_Dataset_v2.xlsx
Seeds:
  1. Controls sheet        → control table
  2. Requirements (Flat)   → requirement table
  3. Control Metrics sheet → control_metric_definition table

Run:
  python infra/scripts/seed_catalog.py

Env:
  DATABASE_URL  (default: postgresql+asyncpg://aigov:localdev@localhost:5432/aigov)

Notes:
  - Idempotent: re-running skips rows that already exist (ON CONFLICT DO NOTHING).
  - requirement.regulation_id is NOT NULL in the schema. All seeded requirements are
    parked under a placeholder Regulation ("Unlinked — Phase 3") and re-linked in Phase 3.
  - control.measurement_mode does not exist in the current schema and is skipped.
"""
import asyncio
import json
import os
import uuid
from pathlib import Path

import openpyxl
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATASET_PATH = Path(__file__).parents[2] / "data" / "UN_AI_Governance_Dataset_v2.xlsx"
DEFAULT_DB_URL = "postgresql+asyncpg://aigov:localdev@localhost:5432/aigov"

TIER_MAP = {
    "Foundation": "FOUNDATION",
    "Common": "COMMON",
    "Specialized": "SPECIALIZED",
}

# Placeholder regulation ID — all seeded requirements park here until Phase 3 re-links them
PLACEHOLDER_REG_ID = "00000000-0000-0000-0000-000000000001"


def _new_id() -> str:
    return str(uuid.uuid4())


def _load_workbook() -> openpyxl.Workbook:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")
    return openpyxl.load_workbook(DATASET_PATH, read_only=True, data_only=True)


def _sheet_rows(ws) -> list[dict]:
    """Return all rows as dicts keyed by header, skipping the header row itself."""
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip() if h is not None else None for h in rows[0]]
    return [dict(zip(headers, row)) for row in rows[1:]]


# ---------------------------------------------------------------------------
# Sheet loaders
# ---------------------------------------------------------------------------

async def seed_controls(conn) -> int:
    wb = _load_workbook()
    ws = wb["Controls"]
    rows = _sheet_rows(ws)
    count = 0

    for row in rows:
        code = row.get("Control ID")
        if not code or str(code).startswith("──"):
            continue

        tier_raw = row.get("Tier") or ""
        tier = TIER_MAP.get(tier_raw, tier_raw.upper() if tier_raw else None)
        is_foundation = tier_raw == "Foundation"
        domain = (row.get("Domain") or "").lower()

        mode_raw = str(row.get("Measurement Mode") or "").strip().lower()
        measurement_mode = mode_raw if mode_raw in ("system_calculated", "hybrid", "manual") else None

        await conn.execute(
            text("""
                INSERT INTO control (id, code, title, description, domain, tier, is_foundation, measurement_mode)
                VALUES (:id, :code, :title, :description, :domain, :tier, :is_foundation, :measurement_mode)
                ON CONFLICT (code) DO NOTHING
            """),
            {
                "id": _new_id(),
                "code": str(code).strip(),
                "title": str(row.get("Control Name") or "").strip(),
                "description": str(row.get("Description") or "").strip() or None,
                "domain": domain or None,
                "tier": tier,
                "is_foundation": is_foundation,
                "measurement_mode": measurement_mode,
            },
        )
        count += 1

    print(f"  Controls processed: {count} rows (skipped existing via ON CONFLICT DO NOTHING)")
    return count


async def seed_requirements(conn) -> int:
    # Ensure placeholder regulation exists
    await conn.execute(
        text("""
            INSERT INTO regulation (id, title, jurisdiction)
            VALUES (:id, :title, :jurisdiction)
            ON CONFLICT DO NOTHING
        """),
        {
            "id": PLACEHOLDER_REG_ID,
            "title": "Unlinked — Phase 3",
            "jurisdiction": "PLACEHOLDER",
        },
    )

    wb = _load_workbook()
    ws = wb["Requirements (Flat)"]
    rows = _sheet_rows(ws)
    count = 0

    for row in rows:
        code = row.get("Requirement ID")
        if not code:
            continue

        await conn.execute(
            text("""
                INSERT INTO requirement (id, regulation_id, code, title, description, category)
                VALUES (:id, :regulation_id, :code, :title, :description, :category)
                ON CONFLICT DO NOTHING
            """),
            {
                "id": _new_id(),
                "regulation_id": PLACEHOLDER_REG_ID,
                "code": str(code).strip(),
                "title": str(row.get("Requirement Text") or "").strip() or None,
                "description": str(row.get("Source Ref") or "").strip() or None,
                "category": str(row.get("Source") or "").strip() or None,
            },
        )
        count += 1

    print(f"  Requirements processed: {count} rows (parked under placeholder regulation)")
    return count


async def seed_metric_definitions(conn) -> int:
    # Build control code → id lookup
    result = await conn.execute(text("SELECT id, code FROM control"))
    control_by_code = {row.code: row.id for row in result}

    wb = _load_workbook()
    ws = wb["Control Metrics"]
    rows = _sheet_rows(ws)
    count = 0

    for row in rows:
        control_code = row.get("Control ID")
        metric_key = row.get("Metric Key (OTEL)")
        if not control_code or not metric_key:
            continue

        control_id = control_by_code.get(str(control_code).strip())
        if not control_id:
            print(f"  WARNING: control '{control_code}' not found — skipping metric '{metric_key}'")
            continue

        threshold = {
            "compliant": row.get("Threshold: Compliant"),
            "warning": row.get("Threshold: Warning"),
            "breach": row.get("Threshold: Breach"),
            "direction": row.get("Direction"),
            "unit": row.get("Unit"),
        }
        is_manual = str(row.get("Measurement Mode") or "").strip().lower() == "manual"

        await conn.execute(
            text("""
                INSERT INTO control_metric_definition (id, control_id, metric_name, threshold, is_manual)
                VALUES (:id, :control_id, :metric_name, :threshold, :is_manual)
                ON CONFLICT DO NOTHING
            """),
            {
                "id": _new_id(),
                "control_id": control_id,
                "metric_name": str(metric_key).strip(),
                "threshold": json.dumps(threshold),
                "is_manual": is_manual,
            },
        )
        count += 1

    print(f"  Metric definitions processed: {count} rows")
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    engine = create_async_engine(db_url, echo=False)

    n_controls = n_requirements = n_metrics = 0

    async with engine.begin() as conn:
        print("\n── Sheet 1: Controls ──")
        try:
            n_controls = await seed_controls(conn)
        except Exception as exc:
            print(f"  ERROR seeding controls: {exc}")

        print("\n── Sheet 2: Requirements (Flat) ──")
        try:
            n_requirements = await seed_requirements(conn)
        except Exception as exc:
            print(f"  ERROR seeding requirements: {exc}")

        print("\n── Sheet 3: Control Metrics ──")
        try:
            n_metrics = await seed_metric_definitions(conn)
        except Exception as exc:
            print(f"  ERROR seeding metric definitions: {exc}")

    await engine.dispose()
    print(f"\nSeeded: {n_controls} controls, {n_requirements} requirements, {n_metrics} metric definitions")


if __name__ == "__main__":
    asyncio.run(main())
