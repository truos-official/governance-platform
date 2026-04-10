"""
admin.py — Admin-only configuration endpoints

GET  /admin/alignment-weights         — current active config + full history
POST /admin/alignment-weights         — set new weights (admin only, sum must = 1.0)

Weight config is immutable — each POST creates a new row.
Full history retained for audit. Active config = latest is_active=True row.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, validator, Field
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.llm.factory import get_llm_adapter
from db.models import (
    AlignmentWeightConfig,
    TierPeerAggregate,
    MetricReading,
    Application,
    Control,
    ControlRequirement,
    Requirement,
    ApplicationRequirement,
    ControlLifecycleTag,
    ApprovedSystemAttribute,
)
from db.session import get_db_session as get_db

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AlignmentWeightEntry(BaseModel):
    id:                 str
    peer_adoption_rate: float
    regulatory_density: float
    trend_velocity:     float
    set_by:             str
    set_at:             datetime
    reason:             Optional[str]
    is_active:          bool


class AlignmentWeightRequest(BaseModel):
    peer_adoption_rate: float
    regulatory_density: float
    trend_velocity:     float
    set_by:             str
    reason:             Optional[str] = None

    @validator("trend_velocity")
    def weights_must_sum_to_one(cls, trend_velocity, values):
        peer   = values.get("peer_adoption_rate", 0)
        reg    = values.get("regulatory_density", 0)
        total  = round(peer + reg + trend_velocity, 6)
        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"Weights must sum to 1.0 — got {total} "
                f"(peer={peer}, regulatory={reg}, trend={trend_velocity})"
            )
        return trend_velocity

    @validator("peer_adoption_rate", "regulatory_density", "trend_velocity")
    def weight_must_be_positive(cls, v):
        if v < 0 or v > 1:
            raise ValueError(f"Each weight must be between 0.0 and 1.0 — got {v}")
        return v


class AlignmentWeightResponse(BaseModel):
    active:  AlignmentWeightEntry
    history: list[AlignmentWeightEntry]


class TagSuggestion(BaseModel):
    tag: str
    confidence: float


class TagControlResponse(BaseModel):
    control_id: str
    suggestions: list[TagSuggestion]
    suggested_by: str
    created_at: datetime


class PendingTagItem(BaseModel):
    id: str
    control_id: str
    control_code: Optional[str]
    control_title: Optional[str]
    tag: str
    confidence_score: Optional[float]
    suggested_by: Optional[str]
    created_at: datetime
    approved: bool
    reviewed_by: Optional[str]
    review_state: str


class TagReviewRequest(BaseModel):
    approved: bool
    reviewed_by: str
    tag: Optional[str] = None


class SystemAttributeItem(BaseModel):
    id: str
    attribute_name: str
    source: str
    description: Optional[str]
    data_type: str
    unit: Optional[str]
    example_value: Optional[str]
    is_active: bool
    added_by: Optional[str]
    added_at: datetime


class FormulaValidationRequest(BaseModel):
    field_picker: str
    operator: str
    window: str
    aggregation: str
    threshold: dict = Field(default_factory=dict)


class FormulaValidationResponse(BaseModel):
    valid: bool
    expression_preview: str
    normalized_threshold: dict
    warnings: list[str] = Field(default_factory=list)


class DefaultRequirementsRequest(BaseModel):
    requirement_ids: list[str] = Field(default_factory=list)
    set_by: str


class DefaultRequirementItem(BaseModel):
    requirement_id: str
    code: Optional[str]
    title: Optional[str]
    regulation_title: Optional[str]
    jurisdiction: Optional[str]
    coverage_apps: int
    total_apps: int
    fully_applied: bool


class DefaultRequirementsResponse(BaseModel):
    total_apps: int
    defaults: list[DefaultRequirementItem]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _to_entry(row: AlignmentWeightConfig) -> AlignmentWeightEntry:
    return AlignmentWeightEntry(
        id=row.id,
        peer_adoption_rate=row.peer_adoption_rate,
        regulatory_density=row.regulatory_density,
        trend_velocity=row.trend_velocity,
        set_by=row.set_by,
        set_at=row.set_at,
        reason=row.reason,
        is_active=row.is_active,
    )


async def get_active_weights(db: AsyncSession) -> AlignmentWeightConfig:
    """Fetch the current active weight config. Used by alignment engine."""
    result = await db.execute(
        select(AlignmentWeightConfig)
        .where(AlignmentWeightConfig.is_active.is_(True))
        .order_by(AlignmentWeightConfig.set_at.desc())
        .limit(1)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            status_code=500,
            detail="No active alignment weight config found — check DB seeding"
        )
    return config


ALLOWED_LIFECYCLE_TAGS = {
    "Corporate Oversight",
    "Risk & Compliance",
    "Technical Architecture",
    "Data Readiness",
    "Data Integration",
    "Security",
    "Infrastructure",
    "Solution Design",
    "System Performance",
}
MAX_TAG_SUGGESTIONS = 3

ALLOWED_OPERATORS = {"lte", "gte", "lt", "gt", "eq", "between"}
ALLOWED_WINDOWS = {"realtime", "1h", "24h", "7d", "30d"}
ALLOWED_AGGREGATIONS = {"latest", "mean", "p50", "p95", "sum", "count", "rate", "delta"}

DOMAIN_TO_TAG = {
    "governance": "Corporate Oversight",
    "audit": "Corporate Oversight",
    "communication": "Corporate Oversight",
    "risk": "Risk & Compliance",
    "regulatory": "Risk & Compliance",
    "privacy": "Risk & Compliance",
    "architecture": "Technical Architecture",
    "lifecycle": "Technical Architecture",
    "data": "Data Readiness",
    "integration": "Data Integration",
    "third party": "Data Integration",
    "security": "Security",
    "infrastructure": "Infrastructure",
    "responsible": "Solution Design",
    "design": "Solution Design",
    "operations": "System Performance",
    "incident": "System Performance",
    "performance": "System Performance",
}


def _extract_json_payload(text: str) -> Optional[Any]:
    if not text:
        return None
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # Try object payload first, then array payload.
    fence_match = re.search(r"\{[\s\S]*\}", stripped)
    if fence_match:
        try:
            return json.loads(fence_match.group(0))
        except json.JSONDecodeError:
            pass
    array_match = re.search(r"\[[\s\S]*\]", stripped)
    if array_match:
        try:
            return json.loads(array_match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _parse_llm_tag_suggestions(raw_text: str) -> list[TagSuggestion]:
    parsed = _extract_json_payload(raw_text or "")
    candidates: list[dict[str, Any]] = []
    if isinstance(parsed, dict):
        if isinstance(parsed.get("tags"), list):
            candidates = [x for x in parsed["tags"] if isinstance(x, dict)]
        elif isinstance(parsed.get("lifecycle_tags"), list):
            candidates = [x for x in parsed["lifecycle_tags"] if isinstance(x, dict)]
    elif isinstance(parsed, list):
        candidates = [x for x in parsed if isinstance(x, dict)]

    dedup: dict[str, TagSuggestion] = {}
    for item in candidates:
        tag = str(item.get("tag", "")).strip()
        if tag not in ALLOWED_LIFECYCLE_TAGS:
            continue
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        suggestion = TagSuggestion(
            tag=tag,
            confidence=max(0.0, min(1.0, confidence)),
        )
        existing = dedup.get(tag)
        if existing is None or suggestion.confidence > existing.confidence:
            dedup[tag] = suggestion

    ordered = sorted(
        dedup.values(),
        key=lambda s: (-s.confidence, s.tag),
    )
    return ordered[:MAX_TAG_SUGGESTIONS]


def _heuristic_tags(control: Control) -> list[TagSuggestion]:
    low = f"{control.title or ''} {control.description or ''} {control.domain or ''}".lower()
    picked: list[TagSuggestion] = []
    for keyword, tag in DOMAIN_TO_TAG.items():
        if keyword in low:
            picked.append(TagSuggestion(tag=tag, confidence=0.62))
    if not picked:
        picked.append(TagSuggestion(tag="Risk & Compliance", confidence=0.40))
    dedup: dict[str, TagSuggestion] = {}
    for item in picked:
        if item.tag not in dedup or item.confidence > dedup[item.tag].confidence:
            dedup[item.tag] = item
    return list(dedup.values())


def _validate_formula_payload(body: FormulaValidationRequest) -> FormulaValidationResponse:
    if body.operator not in ALLOWED_OPERATORS:
        raise HTTPException(status_code=422, detail=f"operator must be one of {sorted(ALLOWED_OPERATORS)}")
    if body.window not in ALLOWED_WINDOWS:
        raise HTTPException(status_code=422, detail=f"window must be one of {sorted(ALLOWED_WINDOWS)}")
    if body.aggregation not in ALLOWED_AGGREGATIONS:
        raise HTTPException(status_code=422, detail=f"aggregation must be one of {sorted(ALLOWED_AGGREGATIONS)}")

    threshold = dict(body.threshold or {})
    warnings: list[str] = []

    if body.operator == "between":
        if "min_value" not in threshold or "max_value" not in threshold:
            raise HTTPException(
                status_code=422,
                detail="between operator requires threshold.min_value and threshold.max_value",
            )
        try:
            min_v = float(threshold["min_value"])
            max_v = float(threshold["max_value"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="between threshold values must be numeric")
        if min_v > max_v:
            raise HTTPException(status_code=422, detail="between threshold min_value must be <= max_value")
        threshold["min_value"] = min_v
        threshold["max_value"] = max_v
        expression = f"{body.aggregation}({body.field_picker}, window={body.window}) between {min_v} and {max_v}"
    else:
        if "value" not in threshold:
            raise HTTPException(status_code=422, detail="threshold.value is required")
        try:
            val = float(threshold["value"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="threshold.value must be numeric")
        threshold["value"] = val
        expression = f"{body.aggregation}({body.field_picker}, window={body.window}) {body.operator} {val}"

    if body.window == "realtime" and body.aggregation not in {"latest", "delta"}:
        warnings.append("realtime window is usually paired with latest or delta aggregation")

    return FormulaValidationResponse(
        valid=True,
        expression_preview=expression,
        normalized_threshold=threshold,
        warnings=warnings,
    )


def _tag_review_state(tag_row: ControlLifecycleTag) -> str:
    if tag_row.approved:
        return "approved"
    if tag_row.reviewed_by:
        return "rejected"
    return "pending"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/admin/alignment-weights", response_model=AlignmentWeightResponse)
async def get_alignment_weights(db: AsyncSession = Depends(get_db)):
    """Return current active weights and full history."""
    active = await get_active_weights(db)

    history_result = await db.execute(
        select(AlignmentWeightConfig)
        .order_by(AlignmentWeightConfig.set_at.desc())
    )
    history = history_result.scalars().all()

    return AlignmentWeightResponse(
        active=_to_entry(active),
        history=[_to_entry(h) for h in history],
    )


@router.post("/admin/alignment-weights",
             response_model=AlignmentWeightEntry,
             status_code=status.HTTP_201_CREATED)
async def set_alignment_weights(
    body: AlignmentWeightRequest,
    db:   AsyncSession = Depends(get_db),
):
    """
    Admin only — set new alignment weights.
    Creates an immutable audit record. Previous config remains in history.
    Deactivates all previous active configs.
    """
    # Deactivate current active config
    current = await db.execute(
        select(AlignmentWeightConfig)
        .where(AlignmentWeightConfig.is_active.is_(True))
    )
    for row in current.scalars().all():
        row.is_active = False

    # Insert new config
    new_config = AlignmentWeightConfig(
        id=str(uuid4()),
        peer_adoption_rate=body.peer_adoption_rate,
        regulatory_density=body.regulatory_density,
        trend_velocity=body.trend_velocity,
        set_by=body.set_by,
        set_at=datetime.utcnow(),
        reason=body.reason,
        is_active=True,
    )
    db.add(new_config)
    await db.commit()
    await db.refresh(new_config)

    return _to_entry(new_config)


@router.post("/admin/refresh-peer-aggregates", status_code=status.HTTP_200_OK)
async def refresh_peer_aggregates(db: AsyncSession = Depends(get_db)):
    """
    Admin only — refresh TierPeerAggregate materialized table.
    Aggregates metric medians per tier from MetricReading table.
    Replaces all existing rows. Call after significant new telemetry is ingested.
    """
    # Delete existing aggregates
    await db.execute(delete(TierPeerAggregate))

    # Get all tiers that have apps
    tiers_result = await db.execute(
        select(Application.current_tier)
        .where(Application.current_tier.is_not(None))
        .distinct()
    )
    tiers = [r[0] for r in tiers_result.fetchall()]

    inserted = 0
    for tier in tiers:
        # Get all app IDs in this tier
        apps_result = await db.execute(
            select(Application.id)
            .where(Application.current_tier == tier)
        )
        app_ids = [r[0] for r in apps_result.fetchall()]
        if not app_ids:
            continue

        # Get distinct metric names for this tier
        metrics_result = await db.execute(
            select(MetricReading.metric_name)
            .where(MetricReading.application_id.in_(app_ids))
            .distinct()
        )
        metric_names = [r[0] for r in metrics_result.fetchall()]

        for metric_name in metric_names:
            # Calculate average value across all apps in tier
            avg_result = await db.execute(
                select(func.avg(MetricReading.value))
                .where(
                    MetricReading.application_id.in_(app_ids),
                    MetricReading.metric_name == metric_name,
                )
            )
            avg_value = avg_result.scalar()
            if avg_value is None:
                continue

            aggregate = TierPeerAggregate(
                id=str(uuid4()),
                tier=tier,
                metric_name=metric_name,
                avg_value=round(float(avg_value), 6),
                peer_count=len(app_ids),
                refreshed_at=datetime.utcnow(),
            )
            db.add(aggregate)
            inserted += 1

    await db.commit()
    return {
        "refreshed": True,
        "tiers_processed": len(tiers),
        "aggregates_written": inserted,
        "refreshed_at": datetime.utcnow().isoformat(),
    }


@router.post("/admin/tag-control/{control_id}", response_model=TagControlResponse)
async def tag_control(control_id: str, db: AsyncSession = Depends(get_db)):
    control = await db.get(Control, control_id)
    if not control:
        raise HTTPException(status_code=404, detail="Control not found")

    req_rows = await db.execute(
        select(Requirement.code, Requirement.title, Requirement.description)
        .join(ControlRequirement, ControlRequirement.requirement_id == Requirement.id)
        .where(ControlRequirement.control_id == control_id)
        .order_by(Requirement.code)
        .limit(20)
    )
    req_context = "\n".join(
        f"- {row.code}: {row.title} | {row.description or ''}"
        for row in req_rows.all()
    )
    allowed_tags = sorted(ALLOWED_LIFECYCLE_TAGS)
    prompt = (
        "Classify this governance control into lifecycle tags.\n"
        f"Allowed tags only: {allowed_tags}\n"
        "Return STRICT JSON only with this exact schema:\n"
        '{"tags":[{"tag":"<allowed_tag>","confidence":0.0}]}\n'
        f"Rules: max {MAX_TAG_SUGGESTIONS} tags, no markdown, no prose, "
        "confidence must be numeric in [0,1].\n\n"
        f"Control code: {control.code}\n"
        f"Control title: {control.title}\n"
        f"Control domain: {control.domain}\n"
        f"Control description: {control.description or ''}\n"
        f"Linked requirements:\n{req_context}"
    )
    system = (
        "You are a governance taxonomy classifier. "
        "Follow the JSON schema exactly and never include extra keys or commentary."
    )

    suggestions: list[TagSuggestion] = []
    suggested_by = "llm"
    try:
        llm = get_llm_adapter()
        try:
            raw = await llm.complete(prompt=prompt, system=system, max_tokens=300, use_mini=True)  # type: ignore[arg-type]
        except TypeError:
            raw = await llm.complete(prompt=prompt, system=system, max_tokens=300)
        suggestions = _parse_llm_tag_suggestions(raw or "")
    except Exception:
        suggestions = []

    if not suggestions:
        suggestions = _heuristic_tags(control)
        suggested_by = "heuristic"

    now = datetime.utcnow()
    for suggestion in suggestions:
        existing = await db.scalar(
            select(ControlLifecycleTag).where(
                ControlLifecycleTag.control_id == control_id,
                ControlLifecycleTag.tag == suggestion.tag,
            )
        )
        if existing:
            existing.confidence_score = suggestion.confidence
            existing.suggested_by = suggested_by
            existing.approved = False
            existing.reviewed_by = None
            existing.created_at = now
        else:
            db.add(
                ControlLifecycleTag(
                    id=str(uuid4()),
                    control_id=control_id,
                    tag=suggestion.tag,
                    confidence_score=suggestion.confidence,
                    suggested_by=suggested_by,
                    approved=False,
                    created_at=now,
                )
            )

    await db.commit()
    return TagControlResponse(
        control_id=control_id,
        suggestions=suggestions,
        suggested_by=suggested_by,
        created_at=now,
    )


@router.get("/admin/pending-tags", response_model=list[PendingTagItem])
async def get_pending_tags(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            ControlLifecycleTag,
            Control.code.label("control_code"),
            Control.title.label("control_title"),
        )
        .join(Control, Control.id == ControlLifecycleTag.control_id, isouter=True)
        .where(ControlLifecycleTag.approved.is_(False))
        .where(ControlLifecycleTag.reviewed_by.is_(None))
        .order_by(ControlLifecycleTag.created_at.desc())
    )

    return [
        PendingTagItem(
            id=str(row[0].id),
            control_id=str(row[0].control_id),
            control_code=row.control_code,
            control_title=row.control_title,
            tag=row[0].tag,
            confidence_score=row[0].confidence_score,
            suggested_by=row[0].suggested_by,
            created_at=row[0].created_at,
            approved=row[0].approved,
            reviewed_by=row[0].reviewed_by,
            review_state=_tag_review_state(row[0]),
        )
        for row in result.all()
    ]


@router.patch("/admin/tags/{tag_id}", response_model=PendingTagItem)
async def review_tag(tag_id: str, body: TagReviewRequest, db: AsyncSession = Depends(get_db)):
    entity = await db.get(ControlLifecycleTag, tag_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Tag suggestion not found")

    reviewer = (body.reviewed_by or "").strip()
    if not reviewer:
        raise HTTPException(status_code=422, detail="reviewed_by is required")

    if body.tag is not None and not body.approved:
        raise HTTPException(
            status_code=422,
            detail="Tag edits are only allowed when approving a suggestion",
        )

    if body.tag is not None:
        normalized = body.tag.strip()
        if normalized not in ALLOWED_LIFECYCLE_TAGS:
            raise HTTPException(
                status_code=422,
                detail=f"tag must be one of {sorted(ALLOWED_LIFECYCLE_TAGS)}",
            )
        entity.tag = normalized

    entity.approved = body.approved
    entity.reviewed_by = reviewer
    await db.commit()
    await db.refresh(entity)

    control = await db.get(Control, entity.control_id)
    return PendingTagItem(
        id=str(entity.id),
        control_id=str(entity.control_id),
        control_code=control.code if control else None,
        control_title=control.title if control else None,
        tag=entity.tag,
        confidence_score=entity.confidence_score,
        suggested_by=entity.suggested_by,
        created_at=entity.created_at,
        approved=entity.approved,
        reviewed_by=entity.reviewed_by,
        review_state=_tag_review_state(entity),
    )


@router.get("/admin/system-attributes", response_model=list[SystemAttributeItem])
async def list_system_attributes(
    source: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(ApprovedSystemAttribute).order_by(ApprovedSystemAttribute.attribute_name)
    if source:
        query = query.where(ApprovedSystemAttribute.source == source)
    if is_active is not None:
        query = query.where(ApprovedSystemAttribute.is_active == is_active)
    result = await db.execute(query)
    rows = result.scalars().all()
    return [
        SystemAttributeItem(
            id=str(row.id),
            attribute_name=row.attribute_name,
            source=str(row.source),
            description=row.description,
            data_type=str(row.data_type),
            unit=row.unit,
            example_value=row.example_value,
            is_active=row.is_active,
            added_by=row.added_by,
            added_at=row.added_at,
        )
        for row in rows
    ]


@router.post("/admin/validate-formula", response_model=FormulaValidationResponse)
async def validate_formula(body: FormulaValidationRequest, db: AsyncSession = Depends(get_db)):
    attr = await db.scalar(
        select(ApprovedSystemAttribute).where(
            ApprovedSystemAttribute.attribute_name == body.field_picker,
            ApprovedSystemAttribute.is_active.is_(True),
        )
    )
    if not attr:
        raise HTTPException(
            status_code=422,
            detail="field_picker is not present in approved_system_attributes",
        )
    return _validate_formula_payload(body)


@router.get("/admin/default-requirements", response_model=DefaultRequirementsResponse)
async def get_default_requirements(db: AsyncSession = Depends(get_db)):
    total_apps = int(await db.scalar(select(func.count()).select_from(Application)) or 0)
    rows = await db.execute(
        select(
            ApplicationRequirement.requirement_id,
            Requirement.code,
            Requirement.title,
            Requirement.regulation_id,
            func.count(func.distinct(ApplicationRequirement.application_id)).label("coverage_apps"),
        )
        .join(Requirement, Requirement.id == ApplicationRequirement.requirement_id, isouter=True)
        .where(ApplicationRequirement.is_default.is_(True))
        .group_by(
            ApplicationRequirement.requirement_id,
            Requirement.code,
            Requirement.title,
            Requirement.regulation_id,
        )
        .order_by(Requirement.code)
    )
    requirement_rows = rows.all()
    regulation_ids = [row.regulation_id for row in requirement_rows if row.regulation_id]
    regulation_meta = {}
    if regulation_ids:
        from db.models import Regulation
        reg_meta_rows = await db.execute(
            select(Regulation.id, Regulation.title, Regulation.jurisdiction)
            .where(Regulation.id.in_(regulation_ids))
        )
        regulation_meta = {
            str(r.id): {"title": r.title, "jurisdiction": r.jurisdiction}
            for r in reg_meta_rows.all()
        }

    defaults = []
    for row in requirement_rows:
        reg = regulation_meta.get(str(row.regulation_id), {})
        coverage = int(row.coverage_apps or 0)
        defaults.append(
            DefaultRequirementItem(
                requirement_id=str(row.requirement_id),
                code=row.code,
                title=row.title,
                regulation_title=reg.get("title"),
                jurisdiction=reg.get("jurisdiction"),
                coverage_apps=coverage,
                total_apps=total_apps,
                fully_applied=(total_apps > 0 and coverage == total_apps),
            )
        )

    return DefaultRequirementsResponse(total_apps=total_apps, defaults=defaults)


@router.post("/admin/default-requirements", response_model=DefaultRequirementsResponse)
async def set_default_requirements(
    body: DefaultRequirementsRequest,
    db: AsyncSession = Depends(get_db),
):
    normalized_ids = [(rid or "").strip() for rid in body.requirement_ids if (rid or "").strip()]
    # strict UUID validation
    import uuid as _uuid
    parsed_ids: list[str] = []
    invalid_ids: list[str] = []
    for rid in normalized_ids:
        try:
            parsed_ids.append(str(_uuid.UUID(rid)))
        except ValueError:
            invalid_ids.append(rid)
    if invalid_ids:
        raise HTTPException(status_code=422, detail=f"Invalid requirement UUID(s): {', '.join(invalid_ids[:5])}")
    parsed_ids = sorted(set(parsed_ids))

    if parsed_ids:
        existing_req_rows = await db.execute(
            select(Requirement.id).where(Requirement.id.in_(parsed_ids))
        )
        existing_req_ids = {str(x) for x in existing_req_rows.scalars().all()}
        missing = [rid for rid in parsed_ids if rid not in existing_req_ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"Requirement not found: {', '.join(missing[:5])}")

    app_rows = await db.execute(select(Application.id))
    app_ids = [str(row[0]) for row in app_rows.fetchall()]
    now = datetime.utcnow()

    await db.execute(
        delete(ApplicationRequirement).where(
            ApplicationRequirement.is_default.is_(True),
            ApplicationRequirement.application_id.in_(app_ids or [""]),
            ApplicationRequirement.requirement_id.notin_(parsed_ids or [""]),
        )
    )

    for app_id in app_ids:
        for req_id in parsed_ids:
            existing = await db.scalar(
                select(ApplicationRequirement).where(
                    ApplicationRequirement.application_id == app_id,
                    ApplicationRequirement.requirement_id == req_id,
                )
            )
            if existing:
                existing.is_default = True
                existing.added_by = body.set_by
                existing.added_at = now
                continue
            db.add(
                ApplicationRequirement(
                    id=str(uuid4()),
                    application_id=app_id,
                    requirement_id=req_id,
                    selected_at=now,
                    is_default=True,
                    added_by=body.set_by,
                    added_at=now,
                )
            )

    await db.commit()
    return await get_default_requirements(db)
