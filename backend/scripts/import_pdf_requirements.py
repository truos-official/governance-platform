"""
Import additional governance requirements from PDF documents.

Safe-by-default workflow:
  1) Extract requirement-like candidate statements from PDFs.
  2) Semantically map each candidate to existing control/risk/measure context.
  3) Write proposal JSON for review.
  4) Optional --apply inserts only NEW records (non-destructive).

Examples:
  # Propose only (default; no DB writes)
  python scripts/import_pdf_requirements.py --pdf-dir /tmp/pdfs

  # Apply after review (inserts only)
  python scripts/import_pdf_requirements.py --pdf-dir /tmp/pdfs --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


DEFAULT_DB_URL = "postgresql+asyncpg://aigov:localdev@localhost:5432/aigov"


def _discover_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker-compose.yml").exists() or (parent / ".git").exists():
            return parent
    # Container fallback: /app volume may only contain backend folder.
    return here.parents[1]


REPO_ROOT = _discover_repo_root()
DEFAULT_PDF_DIR = REPO_ROOT / ".reference" / "governance-demo-agentic" / "data" / "pdfs"
if not DEFAULT_PDF_DIR.exists():
    DEFAULT_PDF_DIR = Path("/tmp/pdfs")
DEFAULT_OUTPUT_PATH = REPO_ROOT / "data" / "imports" / "pdf_requirement_proposals.json"

REQUIREMENT_MODAL_RE = re.compile(
    r"\b(shall|must|should|required to|is required to|ensure that|ensure|prohibit|shall not|must not)\b",
    re.IGNORECASE,
)

GOVERNANCE_SIGNAL_RE = re.compile(
    r"\b(ai|algorithm|model|data|risk|security|privacy|oversight|audit|transparen|accountab|governance|monitor|incident|safety|human rights)\w*\b",
    re.IGNORECASE,
)

UN_SIGNAL_RE = re.compile(
    r"\b(united nations|general assembly|human rights council|secretary[- ]general|ohchr|a/hrc|a/\d+)\b",
    re.IGNORECASE,
)

CHINA_SIGNAL_RE = re.compile(
    r"\b(china|people'?s republic of china|prc|cyberspace administration of china|cac|national standard of china)\b",
    re.IGNORECASE,
)

UN_DOC_SYMBOL_RE = re.compile(r"\b([A-Z]/[A-Z0-9./-]+\d)\b")

DOMAIN_KEYWORDS: dict[str, set[str]] = {
    "risk management": {"risk", "assessment", "classification", "impact", "harm", "mitigation"},
    "regulatory": {"regulation", "compliance", "law", "legal", "statutory", "obligation"},
    "governance": {"governance", "accountability", "responsibility", "policy", "owner", "oversight"},
    "audit": {"audit", "evidence", "traceability", "record", "log", "assurance"},
    "privacy": {"privacy", "personal data", "pii", "consent", "anonym", "data protection"},
    "security": {"security", "cyber", "attack", "threat", "access control", "vulnerability"},
    "incident management": {"incident", "response", "escalation", "breach", "containment", "recovery"},
    "operations": {"operations", "runbook", "sla", "availability", "uptime", "maintenance"},
    "lifecycle": {"lifecycle", "development", "testing", "deployment", "validation", "drift"},
    "responsible systems": {"fairness", "bias", "explainability", "human oversight", "redress", "ethics"},
    "communication": {"disclosure", "transparency", "notice", "user communication", "documentation"},
    "third party": {"vendor", "supplier", "third party", "outsource", "procurement"},
    "un-specific": {"international cooperation", "capacity building", "global governance"},
}

DOMAIN_TO_GOVERNANCE_CATEGORY = {
    "risk management": "Risk & Compliance",
    "regulatory": "Risk & Compliance",
    "governance": "Corporate Oversight",
    "audit": "Risk & Compliance",
    "privacy": "Risk & Compliance",
    "security": "Security",
    "incident management": "System Performance",
    "operations": "System Performance",
    "lifecycle": "Data Integration",
    "responsible systems": "Solution Design",
    "communication": "Corporate Oversight",
    "third party": "Risk & Compliance",
    "un-specific": "Corporate Oversight",
}


def _governance_category_for_domain(domain: str) -> str:
    return DOMAIN_TO_GOVERNANCE_CATEGORY.get((domain or "").strip().lower(), "Risk & Compliance")
DOMAIN_TO_RISK = {
    "risk management": "Risk classification and mitigation",
    "regulatory": "Regulatory non-compliance",
    "governance": "Governance accountability gap",
    "audit": "Auditability and evidence gap",
    "privacy": "Privacy and data protection exposure",
    "security": "Security and adversarial exposure",
    "incident management": "Operational incident response risk",
    "operations": "Service reliability risk",
    "lifecycle": "Model lifecycle and drift risk",
    "responsible systems": "Responsible AI and oversight risk",
    "communication": "Transparency and disclosure risk",
    "third party": "Third-party dependency risk",
    "un-specific": "Cross-cutting governance risk",
}


@dataclass
class ExistingRequirement:
    code: str
    title: str
    description: str


@dataclass
class ControlContext:
    id: str
    code: str
    title: str
    description: str
    domain: str
    measurement_mode: str
    metric_name: str | None
    formula: str | None


@dataclass
class Candidate:
    source_pdf: str
    jurisdiction: str
    regulation_title: str
    requirement_text: str
    mapped_domain: str
    mapped_control_id: str | None
    mapped_control_code: str | None
    mapped_control_title: str | None
    mapped_risk: str
    mapped_metric_name: str | None
    mapped_formula: str | None
    similarity_to_existing: float
    confidence: float


def _clean_spaces(text_value: str) -> str:
    return re.sub(r"\s+", " ", text_value).strip()


def _norm_text(text_value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text_value.lower()).strip()


def _tokenize(text_value: str) -> set[str]:
    return {tok for tok in _norm_text(text_value).split() if len(tok) > 2}


def _extract_text_from_pdf(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    chunks: list[str] = []
    for page in reader.pages:
        extracted = page.extract_text() or ""
        if extracted.strip():
            chunks.append(extracted)
    return "\n".join(chunks)


def _split_candidate_sentences(text_blob: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text_blob)
    rough_parts = re.split(r"(?<=[.!?])\s+|;\s+", normalized)
    candidates: list[str] = []
    seen: set[str] = set()
    for part in rough_parts:
        statement = _clean_spaces(part)
        if len(statement) < 70 or len(statement) > 480:
            continue
        if not REQUIREMENT_MODAL_RE.search(statement):
            continue
        if not GOVERNANCE_SIGNAL_RE.search(statement):
            continue
        norm = _norm_text(statement)
        if norm in seen:
            continue
        seen.add(norm)
        candidates.append(statement)
    return candidates


def _infer_jurisdiction(pdf_name: str, pdf_text: str) -> str:
    haystack = f"{pdf_name}\n{pdf_text[:8000]}"
    if CHINA_SIGNAL_RE.search(haystack):
        return "China"
    if UN_SIGNAL_RE.search(haystack):
        return "United Nations"
    if pdf_name.lower().startswith("n") or pdf_name.lower().startswith("g"):
        return "United Nations"
    return "International"


def _infer_regulation_title(pdf_name: str, jurisdiction: str, pdf_text: str) -> str:
    prefix = "UN" if jurisdiction == "United Nations" else "China" if jurisdiction == "China" else "International"
    symbol = Path(pdf_name).stem.upper()

    match = UN_DOC_SYMBOL_RE.search(pdf_text[:4000])
    if match:
        symbol = match.group(1)

    return f"{prefix} AI Governance Source - {symbol}"


def _infer_domain(requirement_text: str) -> str:
    low = requirement_text.lower()
    best_domain = "risk management"
    best_score = -1
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in low:
                score += 1
        if score > best_score:
            best_domain = domain
            best_score = score
    return best_domain


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm_text(a), _norm_text(b)).ratio()


def _best_existing_similarity(statement: str, existing: list[ExistingRequirement]) -> float:
    best = 0.0
    for item in existing:
        score_title = _similarity(statement, item.title)
        score_desc = _similarity(statement, item.description or "")
        best = max(best, score_title, score_desc)
    return best


def _match_control(statement: str, domain: str, controls: list[ControlContext]) -> tuple[ControlContext | None, float]:
    sentence_tokens = _tokenize(statement)
    if not sentence_tokens:
        return None, 0.0

    best_control: ControlContext | None = None
    best_score = -1.0

    for control in controls:
        score = 0.0
        if (control.domain or "").lower() == domain:
            score += 2.25
        control_tokens = _tokenize(f"{control.title} {control.description} {control.domain}")
        overlap = len(sentence_tokens.intersection(control_tokens))
        score += overlap * 0.35
        if control.metric_name:
            score += 0.25
        if score > best_score:
            best_score = score
            best_control = control

    if best_control is None:
        return None, 0.0

    confidence = min(0.99, max(0.1, best_score / 6.0))
    return best_control, confidence


def _ensure_output_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


async def _load_existing_requirements(conn) -> list[ExistingRequirement]:
    result = await conn.execute(
        text(
            """
            SELECT code, title, COALESCE(description, '') AS description
            FROM requirement
            """
        )
    )
    return [
        ExistingRequirement(code=row.code, title=row.title or "", description=row.description or "")
        for row in result.mappings().all()
    ]


def _parse_threshold_formula(raw_threshold: Any) -> str | None:
    if raw_threshold is None:
        return None
    if isinstance(raw_threshold, str):
        try:
            raw_threshold = json.loads(raw_threshold)
        except Exception:
            return None
    if isinstance(raw_threshold, dict):
        return raw_threshold.get("formula")
    return None


async def _load_control_context(conn) -> list[ControlContext]:
    result = await conn.execute(
        text(
            """
            SELECT
                c.id::text AS id,
                c.code AS code,
                c.title AS title,
                COALESCE(c.description, '') AS description,
                COALESCE(c.domain, 'risk management') AS domain,
                COALESCE(c.measurement_mode::text, '') AS measurement_mode,
                cmd.metric_name AS metric_name,
                cmd.threshold AS threshold
            FROM control c
            LEFT JOIN LATERAL (
                SELECT cmd.metric_name, cmd.threshold
                FROM control_metric_definition cmd
                WHERE cmd.control_id = c.id
                ORDER BY cmd.is_manual ASC, cmd.metric_name ASC
                LIMIT 1
            ) cmd ON TRUE
            ORDER BY c.code
            """
        )
    )

    controls: list[ControlContext] = []
    for row in result.mappings().all():
        controls.append(
            ControlContext(
                id=row["id"],
                code=row["code"],
                title=row["title"] or row["code"],
                description=row["description"] or "",
                domain=(row["domain"] or "risk management").lower(),
                measurement_mode=(row["measurement_mode"] or "").lower(),
                metric_name=row.get("metric_name"),
                formula=_parse_threshold_formula(row.get("threshold")),
            )
        )
    return controls


async def _load_existing_codes(conn) -> set[str]:
    result = await conn.execute(text("SELECT code FROM requirement"))
    return {str(code) for code in result.scalars().all() if code}


def _next_code(prefix: str, occupied: set[str]) -> str:
    n = 1
    while True:
        code = f"{prefix}-{n:03d}"
        if code not in occupied:
            occupied.add(code)
            return code
        n += 1


def _code_prefix_for_jurisdiction(jurisdiction: str) -> str:
    if jurisdiction == "United Nations":
        return "UNX"
    if jurisdiction == "China":
        return "CHN"
    return "INT"


async def _upsert_regulation(conn, title: str, jurisdiction: str) -> str:
    find_result = await conn.execute(
        text(
            """
            SELECT id::text AS id
            FROM regulation
            WHERE LOWER(TRIM(title)) = LOWER(TRIM(:title))
              AND LOWER(TRIM(COALESCE(jurisdiction, ''))) = LOWER(TRIM(COALESCE(:jurisdiction, '')))
            LIMIT 1
            """
        ),
        {"title": title, "jurisdiction": jurisdiction},
    )
    existing = find_result.mappings().first()
    if existing:
        return existing["id"]

    regulation_id = str(uuid.uuid4())
    await conn.execute(
        text(
            """
            INSERT INTO regulation (id, title, jurisdiction, created_at)
            VALUES (:id, :title, :jurisdiction, :created_at)
            """
        ),
        {
            "id": regulation_id,
            "title": title,
            "jurisdiction": jurisdiction,
            "created_at": datetime.utcnow(),
        },
    )
    return regulation_id


async def _insert_proposals(
    conn,
    proposals: list[Candidate],
    occupied_codes: set[str],
) -> dict[str, int]:
    inserted_requirements = 0
    inserted_links = 0
    inserted_interpretations = 0

    for item in proposals:
        prefix = _code_prefix_for_jurisdiction(item.jurisdiction)
        req_code = _next_code(prefix, occupied_codes)
        regulation_id = await _upsert_regulation(conn, item.regulation_title, item.jurisdiction)
        requirement_id = str(uuid.uuid4())

        await conn.execute(
            text(
                """
                INSERT INTO requirement (id, regulation_id, code, title, description, category)
                VALUES (:id, :regulation_id, :code, :title, :description, :category)
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {
                "id": requirement_id,
                "regulation_id": regulation_id,
                "code": req_code,
                "title": item.requirement_text,
                "description": f"Imported from PDF source: {item.source_pdf}",
                "category": _governance_category_for_domain(item.mapped_domain),
            },
        )
        inserted_requirements += 1

        if item.mapped_control_id:
            await conn.execute(
                text(
                    """
                    INSERT INTO control_requirement (control_id, requirement_id)
                    VALUES (:control_id, :requirement_id)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"control_id": item.mapped_control_id, "requirement_id": requirement_id},
            )
            inserted_links += 1

        interpretation_text = (
            f"Source interpretation imported from {item.source_pdf}. "
            f"Mapped risk: {item.mapped_risk}. "
            f"Mapped measure: {item.mapped_metric_name or 'N/A'}."
        )
        await conn.execute(
            text(
                """
                INSERT INTO risk_interpretation (id, requirement_id, layer, content, version, created_at)
                VALUES (:id, :requirement_id, :layer, :content, :version, :created_at)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "requirement_id": requirement_id,
                "layer": "SOURCE",
                "content": interpretation_text,
                "version": 1,
                "created_at": datetime.utcnow(),
            },
        )
        inserted_interpretations += 1

    return {
        "inserted_requirements": inserted_requirements,
        "inserted_control_requirement_links": inserted_links,
        "inserted_interpretations": inserted_interpretations,
    }


async def run_import(
    pdf_dir: Path,
    output_path: Path,
    apply: bool,
    max_new: int,
    min_confidence: float,
    max_similarity: float,
    require_measure: bool,
) -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    engine = create_async_engine(db_url, echo=False)

    pdf_paths = sorted([p for p in pdf_dir.glob("*.pdf")] + [p for p in pdf_dir.glob("*.PDF")])
    if not pdf_paths:
        raise FileNotFoundError(f"No PDF files found under {pdf_dir}")

    async with engine.begin() as conn:
        existing_requirements = await _load_existing_requirements(conn)
        controls = await _load_control_context(conn)
        occupied_codes = await _load_existing_codes(conn)

        candidates: list[Candidate] = []
        for pdf_path in pdf_paths:
            text_blob = _extract_text_from_pdf(pdf_path)
            if not text_blob.strip():
                continue
            jurisdiction = _infer_jurisdiction(pdf_path.name, text_blob)
            regulation_title = _infer_regulation_title(pdf_path.name, jurisdiction, text_blob)
            statements = _split_candidate_sentences(text_blob)

            for statement in statements:
                sim_existing = _best_existing_similarity(statement, existing_requirements)
                if sim_existing >= max_similarity:
                    continue

                domain = _infer_domain(statement)
                matched_control, confidence = _match_control(statement, domain, controls)
                risk_label = DOMAIN_TO_RISK.get(domain, DOMAIN_TO_RISK["risk management"])

                if confidence < min_confidence:
                    continue
                if require_measure and (matched_control is None or not matched_control.metric_name):
                    continue

                candidates.append(
                    Candidate(
                        source_pdf=pdf_path.name,
                        jurisdiction=jurisdiction,
                        regulation_title=regulation_title,
                        requirement_text=statement,
                        mapped_domain=domain,
                        mapped_control_id=matched_control.id if matched_control else None,
                        mapped_control_code=matched_control.code if matched_control else None,
                        mapped_control_title=matched_control.title if matched_control else None,
                        mapped_risk=risk_label,
                        mapped_metric_name=matched_control.metric_name if matched_control else None,
                        mapped_formula=matched_control.formula if matched_control else None,
                        similarity_to_existing=round(sim_existing, 4),
                        confidence=round(confidence, 4),
                    )
                )

        # De-duplicate near-duplicate proposal lines.
        deduped: list[Candidate] = []
        seen_norm: set[str] = set()
        for item in sorted(candidates, key=lambda x: x.confidence, reverse=True):
            norm = _norm_text(item.requirement_text)
            if norm in seen_norm:
                continue
            seen_norm.add(norm)
            deduped.append(item)

        final_proposals = deduped[:max_new]

        proposal_payload = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "pdf_dir": str(pdf_dir),
            "apply_mode": apply,
            "thresholds": {
                "min_confidence": min_confidence,
                "max_similarity": max_similarity,
                "max_new": max_new,
                "require_measure": require_measure,
            },
            "summary": {
                "source_pdfs": len(pdf_paths),
                "candidate_rows": len(candidates),
                "proposals": len(final_proposals),
                "by_jurisdiction": {
                    "United Nations": len([p for p in final_proposals if p.jurisdiction == "United Nations"]),
                    "China": len([p for p in final_proposals if p.jurisdiction == "China"]),
                    "International": len([p for p in final_proposals if p.jurisdiction == "International"]),
                },
            },
            "items": [item.__dict__ for item in final_proposals],
        }

        _ensure_output_parent(output_path)
        output_path.write_text(json.dumps(proposal_payload, indent=2), encoding="utf-8")
        print(f"Wrote proposal file: {output_path}")
        print(json.dumps(proposal_payload["summary"], indent=2))

        if apply and final_proposals:
            apply_counts = await _insert_proposals(conn, final_proposals, occupied_codes)
            print("Apply summary:")
            print(json.dumps(apply_counts, indent=2))
        elif apply:
            print("Apply mode requested but no proposals passed filters; no DB changes made.")
        else:
            print("Proposal mode only: no DB changes made.")

    await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import governance requirements from PDFs.")
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Directory containing source PDFs.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Output JSON proposal file.")
    parser.add_argument("--apply", action="store_true", help="Apply proposals to DB (insert-only).")
    parser.add_argument("--max-new", type=int, default=30, help="Maximum new requirement proposals to keep/apply.")
    parser.add_argument("--min-confidence", type=float, default=0.4, help="Minimum control-mapping confidence.")
    parser.add_argument("--max-similarity", type=float, default=0.92, help="Skip candidates too similar to existing requirements.")
    parser.add_argument(
        "--allow-missing-measure",
        action="store_true",
        help="Allow candidates without mapped metric/formula (default keeps only complete records).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        run_import(
            pdf_dir=args.pdf_dir,
            output_path=args.output,
            apply=args.apply,
            max_new=args.max_new,
            min_confidence=args.min_confidence,
            max_similarity=args.max_similarity,
            require_measure=not args.allow_missing_measure,
        )
    )

