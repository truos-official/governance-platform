"""
Generate requirement re-link suggestions for admin review.

This script is the parallel data pass for:
  - mapping existing requirements to real regulations
  - assigning industry categories

Default behavior:
  - heuristic suggestions
  - writes JSON output for review

Future behavior:
  - optional LLM call for higher-quality mapping suggestions
  - enqueue suggestions into curation_queue_item
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DEFAULT_DB_URL = "postgresql+asyncpg://aigov:localdev@localhost:5432/aigov"
DEFAULT_OUTPUT = Path(__file__).parents[2] / "data" / "relink_suggestions.json"

REGULATIONS = [
    {"id": "REG-001", "title": "EU AI Act (2024)", "jurisdiction": "EU", "category": "enterprise"},
    {"id": "REG-002", "title": "NIST AI RMF 1.0", "jurisdiction": "US", "category": "enterprise"},
    {"id": "REG-003", "title": "ISO/IEC 42001:2023", "jurisdiction": "International", "category": "enterprise"},
    {"id": "REG-004", "title": "UN Secretary-General AI Strategy", "jurisdiction": "International", "category": "enterprise"},
    {"id": "REG-005", "title": "HIPAA + HHS AI Guidance", "jurisdiction": "US", "category": "healthcare"},
    {"id": "REG-006", "title": "FDA Software as Medical Device (SaMD)", "jurisdiction": "US", "category": "healthcare"},
    {"id": "REG-007", "title": "EU Medical Device Regulation (MDR)", "jurisdiction": "EU", "category": "healthcare"},
    {"id": "REG-008", "title": "Basel III / SR 11-7 Model Risk", "jurisdiction": "International", "category": "financial"},
    {"id": "REG-009", "title": "FINRA AI Guidance", "jurisdiction": "US", "category": "financial"},
    {"id": "REG-010", "title": "EEOC Algorithmic Hiring Guidance", "jurisdiction": "US", "category": "hr"},
    {"id": "REG-011", "title": "FERPA + ED AI Guidance", "jurisdiction": "US", "category": "education"},
    {"id": "REG-012", "title": "UNHCR AI in Refugee Operations", "jurisdiction": "International", "category": "humanitarian"},
    {"id": "REG-013", "title": "UN DPKO AI Ethics Framework", "jurisdiction": "International", "category": "government"},
    {"id": "REG-014", "title": "Colorado AI Act (SB 205)", "jurisdiction": "US", "category": "enterprise"},
    {"id": "REG-015", "title": "UK AI Code of Practice", "jurisdiction": "UK", "category": "government"},
]

KEYWORDS = {
    "healthcare": {"health", "medical", "diagnosis", "patient", "hospital", "biometric"},
    "financial": {"finance", "bank", "credit", "fraud", "loan", "trading"},
    "criminal_justice": {"criminal", "justice", "law enforcement", "policing", "sentencing"},
    "hr": {"hiring", "employment", "workforce", "recruit", "candidate"},
    "education": {"education", "student", "school", "learning", "ferpa"},
    "humanitarian": {"refugee", "humanitarian", "aid", "displacement", "asylum"},
    "government": {"public sector", "government", "civic", "policy", "defence", "defense"},
}


def _heuristic_category(text_blob: str) -> str:
    low = text_blob.lower()
    for category, words in KEYWORDS.items():
        if any(w in low for w in words):
            return category
    return "enterprise"


def _pick_regulation_for_category(category: str) -> dict:
    for reg in REGULATIONS:
        if reg["category"] == category:
            return reg
    return REGULATIONS[0]


async def _load_requirements(conn) -> list[dict]:
    result = await conn.execute(
        text(
            """
            SELECT
                r.id::text AS requirement_id,
                r.code,
                r.title,
                COALESCE(r.description, '') AS description
            FROM requirement r
            ORDER BY r.code
            """
        )
    )
    return [dict(row) for row in result.mappings().all()]


def _build_suggestion(req: dict) -> dict:
    text_blob = f"{req.get('title', '')} {req.get('description', '')}"
    category = _heuristic_category(text_blob)
    regulation = _pick_regulation_for_category(category)
    return {
        "requirement_id": req["requirement_id"],
        "requirement_code": req.get("code"),
        "requirement_title": req.get("title"),
        "suggested_regulation_id": regulation["id"],
        "suggested_regulation_title": regulation["title"],
        "suggested_category": category,
        "confidence": 0.55,
        "suggested_by": "heuristic_fallback",
        "review_status": "pending_admin_review",
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    output_path = Path(args.output)

    engine = create_async_engine(db_url, future=True)
    try:
        async with engine.begin() as conn:
            requirements = await _load_requirements(conn)
    finally:
        await engine.dispose()

    suggestions = [_build_suggestion(req) for req in requirements]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"suggestions": suggestions}, indent=2), encoding="utf-8")
    print(f"Wrote {len(suggestions)} requirement re-link suggestions to: {output_path}")
    print("Next step: replace heuristic scoring with aigov-gpt41-mini + curation queue submit flow.")


if __name__ == "__main__":
    asyncio.run(main())
