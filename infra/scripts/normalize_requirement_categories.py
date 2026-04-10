"""
Normalize requirement.category values to the 9 standard governance categories.

Usage:
  python infra/scripts/normalize_requirement_categories.py           # dry run
  python infra/scripts/normalize_requirement_categories.py --apply   # write updates
"""
from __future__ import annotations

import argparse
import os
from collections import Counter
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DEFAULT_DB_URL = "postgresql+asyncpg://aigov:localdev@localhost:5432/aigov"

GOVERNANCE_CATEGORIES = [
    "Corporate Oversight",
    "Risk & Compliance",
    "Technical Architecture",
    "Data Readiness",
    "Data Integration",
    "Security",
    "Infrastructure",
    "Solution Design",
    "System Performance",
]

LEGACY_CATEGORY_MAP = {
    "all": "Risk & Compliance",
    "risk management": "Risk & Compliance",
    "regulatory": "Risk & Compliance",
    "privacy": "Risk & Compliance",
    "governance": "Corporate Oversight",
    "security": "Security",
    "operation": "System Performance",
    "operations": "System Performance",
    "incident management": "System Performance",
    "development": "Technical Architecture",
    "deployment": "Infrastructure",
    "design": "Solution Design",
    "lifecycle": "Data Integration",
    "responsible systems": "Solution Design",
    "communication": "Corporate Oversight",
    "audit": "Risk & Compliance",
    "third party": "Risk & Compliance",
    "un-specific": "Corporate Oversight",
}

CONTROL_DOMAIN_MAP = {
    "risk management": "Risk & Compliance",
    "regulatory": "Risk & Compliance",
    "privacy": "Risk & Compliance",
    "audit": "Risk & Compliance",
    "governance": "Corporate Oversight",
    "security": "Security",
    "operations": "System Performance",
    "operation": "System Performance",
    "incident management": "System Performance",
    "lifecycle": "Data Integration",
    "responsible systems": "Solution Design",
    "communication": "Corporate Oversight",
    "third party": "Risk & Compliance",
    "un-specific": "Corporate Oversight",
}

KEYWORDS_BY_CATEGORY = {
    "Corporate Oversight": {
        "governance", "oversight", "accountability", "owner", "ownership", "policy", "board", "secretariat",
    },
    "Risk & Compliance": {
        "risk", "compliance", "regulatory", "law", "legal", "audit", "privacy", "consent", "obligation",
    },
    "Technical Architecture": {
        "architecture", "model", "system design", "component", "rag", "retrieval", "embedding", "inference",
    },
    "Data Readiness": {
        "data quality", "dataset", "training data", "label", "bias", "representative", "provenance", "lineage",
    },
    "Data Integration": {
        "integration", "pipeline", "ingest", "etl", "lifecycle", "interoperability", "connector", "sync",
    },
    "Security": {
        "security", "encryption", "access control", "authentication", "authorization", "threat", "attack", "vulnerability", "pii",
    },
    "Infrastructure": {
        "infrastructure", "compute", "scaling", "deployment", "latency", "throughput", "capacity", "cost",
    },
    "Solution Design": {
        "human oversight", "fairness", "explainability", "transparency", "responsible", "ethic", "redress",
    },
    "System Performance": {
        "monitor", "monitoring", "incident", "alert", "drift", "uptime", "reliability", "performance", "sla",
    },
}


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _iter_domains(raw_domains: Iterable[str] | None) -> list[str]:
    if not raw_domains:
        return []
    result = []
    for item in raw_domains:
        normalized = _norm(str(item))
        if normalized:
            result.append(normalized)
    return result


def infer_category(
    title: str | None,
    description: str | None,
    legacy_category: str | None,
    control_domains: list[str],
) -> str:
    score = {name: 0.0 for name in GOVERNANCE_CATEGORIES}

    legacy = _norm(legacy_category)
    if legacy in LEGACY_CATEGORY_MAP:
        score[LEGACY_CATEGORY_MAP[legacy]] += 2.0

    for domain in control_domains:
        mapped = CONTROL_DOMAIN_MAP.get(domain)
        if mapped:
            score[mapped] += 4.0

    haystack = f"{title or ''} {description or ''}".lower()
    for category, keywords in KEYWORDS_BY_CATEGORY.items():
        for keyword in keywords:
            if keyword in haystack:
                score[category] += 1.0

    best = max(score.items(), key=lambda item: item[1])[0]
    if score[best] <= 0:
        return "Risk & Compliance"
    return best


async def run(apply: bool) -> None:
    engine = create_async_engine(os.getenv("DATABASE_URL", DEFAULT_DB_URL), echo=False)

    query = text(
        """
        SELECT
            r.id::text AS id,
            r.code AS code,
            r.title AS title,
            COALESCE(r.description, '') AS description,
            COALESCE(r.category, '') AS category,
            COALESCE(
                ARRAY_AGG(DISTINCT LOWER(TRIM(c.domain)))
                FILTER (WHERE c.domain IS NOT NULL AND TRIM(c.domain) <> ''),
                ARRAY[]::text[]
            ) AS domains
        FROM requirement r
        LEFT JOIN control_requirement cr ON cr.requirement_id = r.id
        LEFT JOIN control c ON c.id = cr.control_id
        GROUP BY r.id, r.code, r.title, r.description, r.category
        ORDER BY r.code
        """
    )

    updates: list[tuple[str, str, str, str]] = []
    before_counter = Counter()
    after_counter = Counter()

    async with engine.begin() as conn:
        rows = (await conn.execute(query)).mappings().all()

        for row in rows:
            before = (row.get("category") or "").strip()
            before_counter[before or "<empty>"] += 1

            after = infer_category(
                title=row.get("title"),
                description=row.get("description"),
                legacy_category=row.get("category"),
                control_domains=_iter_domains(row.get("domains")),
            )
            after_counter[after] += 1

            if before != after:
                updates.append((row["id"], row.get("code") or "", before, after))

        if apply and updates:
            for requirement_id, _, _, normalized in updates:
                await conn.execute(
                    text("UPDATE requirement SET category = :category WHERE id::text = :id"),
                    {"category": normalized, "id": requirement_id},
                )

    await engine.dispose()

    print("Category normalization summary")
    print(f"  Total requirements: {sum(before_counter.values())}")
    print(f"  Rows needing updates: {len(updates)}")
    print(f"  Mode: {'APPLY' if apply else 'DRY RUN'}")

    print("\nBefore (top categories):")
    for name, count in before_counter.most_common(20):
        print(f"  {name}: {count}")

    print("\nAfter (normalized categories):")
    for name in GOVERNANCE_CATEGORIES:
        print(f"  {name}: {after_counter.get(name, 0)}")

    if updates:
        print("\nSample updates (first 20):")
        for _, code, old, new in updates[:20]:
            print(f"  {code}: '{old or '<empty>'}' -> '{new}'")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize requirement categories to standard governance categories.")
    parser.add_argument("--apply", action="store_true", help="Write updates to database (default is dry run).")
    return parser.parse_args()


if __name__ == "__main__":
    import asyncio

    args = parse_args()
    asyncio.run(run(apply=args.apply))
