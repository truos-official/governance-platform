"""
GET    /catalog/controls                  — list controls (59 pre-seeded)
GET    /catalog/controls/{id}             — control detail
GET    /catalog/requirements              — list requirements (140 pre-seeded)
GET    /catalog/requirements/{id}         — requirement detail
GET    /catalog/interpretations           — 3-layer interpretation tree
POST   /catalog/interpretations           — submit interpretation (admin)

Domains: 13 (RM, RO, LC, SE, OM, AA, GL, CO, etc.)
Three-tier structure: Foundation / Common / Specialized.
FOUNDATION controls auto-applied to every application:
  RM-0, RM-1, RM-2, RO-2, LC-1, SE-1, OM-1, AA-1, GL-1, CO-1

Phase 3 implementation. MCP server (mcp/server.py) exposes these via 5 catalog tools.
"""
import os
from typing import Literal
from uuid import UUID, uuid4
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, Path, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.search.factory import get_search_adapter
from db.session import get_db_session

router = APIRouter(tags=["catalog"])


class ControlListItem(BaseModel):
    id: str
    code: str
    title: str
    description: str | None
    domain: str
    tier: str | None
    is_foundation: bool | None
    measurement_mode: str | None


class ControlListResponse(BaseModel):
    items: list[ControlListItem]
    total: int
    skip: int
    limit: int


class RequirementListItem(BaseModel):
    id: str
    regulation_id: str
    regulation_title: str | None
    jurisdiction: str | None
    code: str
    title: str
    description: str | None
    category: str | None


class RequirementListResponse(BaseModel):
    items: list[RequirementListItem]
    total: int
    skip: int
    limit: int


class RegulationListItem(BaseModel):
    id: str
    title: str
    jurisdiction: str | None
    requirement_count: int


class RegulationListResponse(BaseModel):
    items: list[RegulationListItem]
    total: int
    skip: int
    limit: int


class CatalogOverviewStatsResponse(BaseModel):
    total_requirements: int
    distinct_rules: int
    rules_with_controls: int
    rules_with_measures: int
    total_controls: int
    controls_with_measures: int
    distinct_control_domains: int
    total_control_requirement_links: int
    total_measure_definitions: int
    distinct_measure_metrics: int
    peer_benchmarked_metrics: int
    risk_compliance_controls: int
    risk_compliance_measurable_controls: int
    risk_compliance_domains_present: int
    total_regulations: int
    total_jurisdictions: int
    total_interpretations: int


class SearchResultItem(BaseModel):
    id: str
    code: str | None = None
    title: str | None = None
    description: str | None = None
    type: str | None = None
    domain: str | None = None
    tier: str | None = None
    measurement_mode: str | None = None
    source: str | None = None
    jurisdiction: str | None = None
    score: float | None = None


class UnifiedSearchResponse(BaseModel):
    items: list[SearchResultItem]
    total: int
    skip: int
    limit: int
    facets: dict[str, dict[str, int]]


class AutocompleteItem(BaseModel):
    id: str
    label: str
    type: str | None = None
    code: str | None = None


class AutocompleteResponse(BaseModel):
    items: list[AutocompleteItem]
    total: int
    skip: int
    limit: int


class InterpretationItem(BaseModel):
    id: str
    requirement_id: str
    layer: str | None
    content: str
    version: int | None
    created_at: datetime | None


class InterpretationListResponse(BaseModel):
    items: list[InterpretationItem]
    total: int
    skip: int
    limit: int


class InterpretationVersionItem(BaseModel):
    id: str
    version: int | None
    content: str
    created_at: datetime | None


class InterpretationLayerNode(BaseModel):
    layer: str
    versions: list[InterpretationVersionItem]


class InterpretationRequirementNode(BaseModel):
    requirement_id: str
    layers: list[InterpretationLayerNode]


class InterpretationTreeResponse(BaseModel):
    items: list[InterpretationRequirementNode]
    total_requirements: int
    skip: int
    limit: int


class InterpretationCreateRequest(BaseModel):
    requirement_id: UUID
    layer: Literal["SOURCE", "SYSTEM", "USER"]
    content: str = Field(..., min_length=1, description="Interpretation text")

    @field_validator("content")
    @classmethod
    def _content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Interpretation content must not be blank")
        return value


CONTROL_BASE_SELECT = """
SELECT
    c.id::text AS id,
    c.code AS code,
    c.title AS title,
    c.description AS description,
    c.domain AS domain,
    c.tier::text AS tier,
    c.is_foundation AS is_foundation,
    c.measurement_mode::text AS measurement_mode
FROM control c
"""


REQUIREMENT_BASE_SELECT = """
SELECT
    r.id::text AS id,
    r.regulation_id::text AS regulation_id,
    reg.title AS regulation_title,
    reg.jurisdiction AS jurisdiction,
    r.code AS code,
    r.title AS title,
    r.description AS description,
    r.category AS category
FROM requirement r
LEFT JOIN regulation reg ON reg.id = r.regulation_id
"""


def _control_filters(domain: str | None, tier: str | None) -> tuple[str, dict]:
    clauses: list[str] = []
    params: dict[str, str] = {}
    if domain:
        clauses.append("LOWER(c.domain) = :domain")
        params["domain"] = domain.lower()
    if tier:
        clauses.append("c.tier::text = :tier")
        params["tier"] = tier
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_clause, params


def _requirement_filters(control_id: UUID | None) -> tuple[str, str, dict]:
    joins = ""
    clauses: list[str] = []
    params: dict[str, str] = {}
    if control_id:
        joins = "JOIN control_requirement cr ON cr.requirement_id = r.id"
        clauses.append("cr.control_id::text = :control_id")
        params["control_id"] = str(control_id)
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return joins, where_clause, params


def _build_facets(rows: list[dict], fields: list[str]) -> dict[str, dict[str, int]]:
    facets: dict[str, dict[str, int]] = {field: {} for field in fields}
    for row in rows:
        for field in fields:
            value = row.get(field)
            if value is None or value == "":
                continue
            bucket = str(value)
            facets[field][bucket] = facets[field].get(bucket, 0) + 1
    return facets


def _build_autocomplete_candidates(rows: list[dict]) -> list[AutocompleteItem]:
    items: list[AutocompleteItem] = []
    seen: set[tuple[str, str | None]] = set()
    for row in rows:
        label = str(row.get("title") or row.get("code") or row.get("id") or "").strip()
        if not label:
            continue
        item_type = row.get("type")
        key = (label.lower(), item_type)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            AutocompleteItem(
                id=str(row.get("id") or ""),
                label=label,
                type=item_type,
                code=row.get("code"),
            )
        )
    return items


def _search_order_by(sort: Literal["relevance", "code", "title"]) -> list[str] | None:
    if sort == "code":
        return ["code asc", "title asc"]
    if sort == "title":
        return ["title asc", "code asc"]
    return None


def _interpretation_filters(
    requirement_id: UUID | None,
    layer: Literal["SOURCE", "SYSTEM", "USER"] | None,
) -> tuple[str, dict]:
    clauses: list[str] = []
    params: dict[str, str] = {}
    if requirement_id:
        clauses.append("ri.requirement_id::text = :requirement_id")
        params["requirement_id"] = str(requirement_id)
    if layer:
        clauses.append("ri.layer::text = :layer")
        params["layer"] = layer
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_clause, params


def _build_interpretation_tree(rows: list[dict]) -> list[InterpretationRequirementNode]:
    grouped: dict[str, dict[str, list[InterpretationVersionItem]]] = {}

    for row in rows:
        requirement_id = row["requirement_id"]
        layer = row.get("layer") or "UNKNOWN"
        grouped.setdefault(requirement_id, {})
        grouped[requirement_id].setdefault(layer, [])
        grouped[requirement_id][layer].append(
            InterpretationVersionItem(
                id=row["id"],
                version=row.get("version"),
                content=row["content"],
                created_at=row.get("created_at"),
            )
        )

    tree: list[InterpretationRequirementNode] = []
    for requirement_id, layers_map in grouped.items():
        layers = [
            InterpretationLayerNode(layer=layer, versions=versions)
            for layer, versions in layers_map.items()
        ]
        tree.append(InterpretationRequirementNode(requirement_id=requirement_id, layers=layers))
    return tree


def _is_admin_scope_check_enabled() -> bool:
    raw = os.getenv("ENFORCE_ADMIN_SCOPE_CHECK", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


async def require_governance_admin_scope(
    x_governance_scopes: str | None = Header(default=None),
) -> None:
    """Placeholder scope guard.

    Enforcement is controlled by ENFORCE_ADMIN_SCOPE_CHECK.
    If enabled, request header X-Governance-Scopes must include governance.admin.
    """
    if not _is_admin_scope_check_enabled():
        return

    scopes = {
        token.strip()
        for token in (x_governance_scopes or "").replace(",", " ").split()
        if token.strip()
    }
    if "governance.admin" not in scopes:
        raise HTTPException(status_code=403, detail="governance.admin scope required")


@router.get("/catalog/controls", response_model=ControlListResponse)
async def list_controls(
    domain: str | None = Query(default=None, min_length=1, max_length=64),
    tier: Literal["FOUNDATION", "COMMON", "SPECIALIZED"] | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> ControlListResponse:
    """List catalog controls with simple domain/tier filters and pagination."""
    where_clause, params = _control_filters(domain=domain, tier=tier)

    count_result = await session.execute(
        text(
            f"""
            SELECT COUNT(*) AS total
            FROM control c
            {where_clause}
            """
        ),
        params,
    )
    total = int(count_result.scalar_one())

    page_params = {**params, "skip": skip, "limit": limit}
    rows_result = await session.execute(
        text(
            f"""
            {CONTROL_BASE_SELECT}
            {where_clause}
            ORDER BY c.code
            OFFSET :skip
            LIMIT :limit
            """
        ),
        page_params,
    )
    items = [ControlListItem(**row) for row in rows_result.mappings().all()]

    return ControlListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/catalog/controls/{control_id}", response_model=ControlListItem)
async def get_control(
    control_id: UUID = Path(..., description="Control UUID"),
    session: AsyncSession = Depends(get_db_session),
) -> ControlListItem:
    result = await session.execute(
        text(
            f"""
            {CONTROL_BASE_SELECT}
            WHERE c.id::text = :control_id
            """
        ),
        {"control_id": str(control_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Control not found")
    return ControlListItem(**row)


@router.get("/catalog/requirements", response_model=RequirementListResponse)
async def list_requirements(
    control_id: UUID | None = Query(default=None, description="Filter by control UUID"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> RequirementListResponse:
    joins, where_clause, params = _requirement_filters(control_id=control_id)

    count_result = await session.execute(
        text(
            f"""
            SELECT COUNT(*) AS total
            FROM requirement r
            {joins}
            {where_clause}
            """
        ),
        params,
    )
    total = int(count_result.scalar_one())

    page_params = {**params, "skip": skip, "limit": limit}
    rows_result = await session.execute(
        text(
            f"""
            {REQUIREMENT_BASE_SELECT}
            {joins}
            {where_clause}
            ORDER BY r.code
            OFFSET :skip
            LIMIT :limit
            """
        ),
        page_params,
    )
    items = [RequirementListItem(**row) for row in rows_result.mappings().all()]

    return RequirementListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/catalog/requirements/{req_id}", response_model=RequirementListItem)
async def get_requirement(
    req_id: UUID = Path(..., description="Requirement UUID"),
    session: AsyncSession = Depends(get_db_session),
) -> RequirementListItem:
    result = await session.execute(
        text(
            f"""
            {REQUIREMENT_BASE_SELECT}
            WHERE r.id::text = :req_id
            """
        ),
        {"req_id": str(req_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return RequirementListItem(**row)


@router.get("/catalog/regulations", response_model=RegulationListResponse)
async def list_regulations(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
) -> RegulationListResponse:
    count_result = await session.execute(
        text(
            """
            SELECT COUNT(*) AS total
            FROM regulation reg
            """
        )
    )
    total = int(count_result.scalar_one())

    rows_result = await session.execute(
        text(
            """
            SELECT
                reg.id::text AS id,
                reg.title AS title,
                reg.jurisdiction AS jurisdiction,
                COUNT(r.id) AS requirement_count
            FROM regulation reg
            LEFT JOIN requirement r ON r.regulation_id = reg.id
            GROUP BY reg.id, reg.title, reg.jurisdiction
            ORDER BY reg.title
            OFFSET :skip
            LIMIT :limit
            """
        ),
        {"skip": skip, "limit": limit},
    )

    items = [
        RegulationListItem(
            id=row["id"],
            title=row["title"],
            jurisdiction=row.get("jurisdiction"),
            requirement_count=int(row.get("requirement_count") or 0),
        )
        for row in rows_result.mappings().all()
    ]
    return RegulationListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/catalog/overview-stats", response_model=CatalogOverviewStatsResponse)
async def catalog_overview_stats(
    session: AsyncSession = Depends(get_db_session),
) -> CatalogOverviewStatsResponse:
    result = await session.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM requirement) AS total_requirements,
                (
                    SELECT COUNT(DISTINCT LOWER(TRIM(COALESCE(NULLIF(r.title, ''), r.code))))
                    FROM requirement r
                ) AS distinct_rules,
                (
                    SELECT COUNT(DISTINCT cr.requirement_id)
                    FROM control_requirement cr
                ) AS rules_with_controls,
                (
                    SELECT COUNT(DISTINCT cr.requirement_id)
                    FROM control_requirement cr
                    JOIN control_metric_definition cmd ON cmd.control_id = cr.control_id
                ) AS rules_with_measures,
                (SELECT COUNT(*) FROM control) AS total_controls,
                (
                    SELECT COUNT(DISTINCT cmd.control_id)
                    FROM control_metric_definition cmd
                ) AS controls_with_measures,
                (
                    SELECT COUNT(DISTINCT LOWER(TRIM(COALESCE(NULLIF(c.domain, ''), 'unassigned'))))
                    FROM control c
                ) AS distinct_control_domains,
                (SELECT COUNT(*) FROM control_requirement) AS total_control_requirement_links,
                (SELECT COUNT(*) FROM control_metric_definition) AS total_measure_definitions,
                (SELECT COUNT(DISTINCT cmd.metric_name) FROM control_metric_definition cmd) AS distinct_measure_metrics,
                (
                    SELECT COUNT(DISTINCT tpa.metric_name)
                    FROM tier_peer_aggregate tpa
                    WHERE COALESCE(tpa.peer_count, 0) >= 1
                ) AS peer_benchmarked_metrics,
                (
                    SELECT COUNT(*)
                    FROM control c
                    WHERE LOWER(TRIM(COALESCE(c.domain, ''))) IN (
                        'risk management',
                        'regulatory',
                        'governance',
                        'audit',
                        'privacy'
                    )
                ) AS risk_compliance_controls,
                (
                    SELECT COUNT(DISTINCT c.id)
                    FROM control c
                    JOIN control_metric_definition cmd ON cmd.control_id = c.id
                    WHERE LOWER(TRIM(COALESCE(c.domain, ''))) IN (
                        'risk management',
                        'regulatory',
                        'governance',
                        'audit',
                        'privacy'
                    )
                ) AS risk_compliance_measurable_controls,
                (
                    SELECT COUNT(DISTINCT LOWER(TRIM(COALESCE(c.domain, ''))))
                    FROM control c
                    WHERE LOWER(TRIM(COALESCE(c.domain, ''))) IN (
                        'risk management',
                        'regulatory',
                        'governance',
                        'audit',
                        'privacy'
                    )
                ) AS risk_compliance_domains_present,
                (SELECT COUNT(*) FROM regulation) AS total_regulations,
                (
                    SELECT COUNT(DISTINCT LOWER(TRIM(reg.jurisdiction)))
                    FROM regulation reg
                    WHERE reg.jurisdiction IS NOT NULL
                      AND TRIM(reg.jurisdiction) <> ''
                ) AS total_jurisdictions,
                (SELECT COUNT(*) FROM risk_interpretation) AS total_interpretations
            """
        )
    )
    row = result.mappings().first() or {}
    return CatalogOverviewStatsResponse(
        total_requirements=int(row.get("total_requirements") or 0),
        distinct_rules=int(row.get("distinct_rules") or 0),
        rules_with_controls=int(row.get("rules_with_controls") or 0),
        rules_with_measures=int(row.get("rules_with_measures") or 0),
        total_controls=int(row.get("total_controls") or 0),
        controls_with_measures=int(row.get("controls_with_measures") or 0),
        distinct_control_domains=int(row.get("distinct_control_domains") or 0),
        total_control_requirement_links=int(row.get("total_control_requirement_links") or 0),
        total_measure_definitions=int(row.get("total_measure_definitions") or 0),
        distinct_measure_metrics=int(row.get("distinct_measure_metrics") or 0),
        peer_benchmarked_metrics=int(row.get("peer_benchmarked_metrics") or 0),
        risk_compliance_controls=int(row.get("risk_compliance_controls") or 0),
        risk_compliance_measurable_controls=int(row.get("risk_compliance_measurable_controls") or 0),
        risk_compliance_domains_present=int(row.get("risk_compliance_domains_present") or 0),
        total_regulations=int(row.get("total_regulations") or 0),
        total_jurisdictions=int(row.get("total_jurisdictions") or 0),
        total_interpretations=int(row.get("total_interpretations") or 0),
    )


@router.get(
    "/catalog/search",
    response_model=UnifiedSearchResponse,
    summary="Unified catalog search",
    description=(
        "Search controls and requirements with optional filters and pagination. "
        "Use sort=relevance|code|title for globally stable ordering across pages."
    ),
)
async def unified_search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query text"),
    type: Literal["control", "requirement"] | None = Query(default=None),
    domain: str | None = Query(default=None),
    tier: Literal["FOUNDATION", "COMMON", "SPECIALIZED"] | None = Query(default=None),
    jurisdiction: str | None = Query(default=None),
    measurement_mode: Literal["system_calculated", "hybrid", "manual"] | None = Query(default=None),
    sort: Literal["relevance", "code", "title"] = Query(
        default="relevance",
        description="Sort order: relevance (default), code, or title",
        examples=["relevance", "code", "title"],
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> UnifiedSearchResponse:
    filters: dict[str, str] = {}
    if type is not None:
        filters["type"] = type
    if domain is not None:
        filters["domain"] = domain
    if tier is not None:
        filters["tier"] = tier
    if jurisdiction is not None:
        filters["jurisdiction"] = jurisdiction
    if measurement_mode is not None:
        filters["measurement_mode"] = measurement_mode

    try:
        adapter = get_search_adapter(index_name="governance-catalog")
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    order_by = _search_order_by(sort)
    page_rows, total_count = await adapter.search(
        query=q,
        filters=filters or None,
        top=limit,
        skip=skip,
        order_by=order_by,
        include_total_count=True,
    )

    items = [SearchResultItem(**row) for row in page_rows]
    facets = _build_facets(
        rows=page_rows,
        fields=["type", "domain", "tier", "jurisdiction", "measurement_mode", "source"],
    )

    return UnifiedSearchResponse(
        items=items,
        total=int(total_count) if total_count is not None else len(page_rows),
        skip=skip,
        limit=limit,
        facets=facets,
    )


@router.get("/catalog/autocomplete", response_model=AutocompleteResponse)
async def autocomplete(
    q: str = Query(..., min_length=1, max_length=120, description="Prefix or phrase for suggestions"),
    type: Literal["control", "requirement"] | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=50),
) -> AutocompleteResponse:
    filters: dict[str, str] = {}
    if type is not None:
        filters["type"] = type

    try:
        adapter = get_search_adapter(index_name="governance-catalog")
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    raw_results, _ = await adapter.search(
        query=q,
        filters=filters or None,
        top=skip + limit,
    )

    all_candidates = _build_autocomplete_candidates(raw_results)
    page = all_candidates[skip : skip + limit]

    return AutocompleteResponse(
        items=page,
        total=len(all_candidates),
        skip=skip,
        limit=limit,
    )


@router.get(
    "/catalog/interpretations",
    response_model=InterpretationListResponse | InterpretationTreeResponse,
)
async def list_interpretations(
    requirement_id: UUID | None = Query(default=None, description="Filter by requirement UUID"),
    layer: Literal["SOURCE", "SYSTEM", "USER"] | None = Query(default=None),
    view: Literal["flat", "tree"] = Query(
        default="flat",
        description="Response shape: flat list or grouped tree",
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> InterpretationListResponse | InterpretationTreeResponse:
    where_clause, params = _interpretation_filters(requirement_id=requirement_id, layer=layer)

    if view == "tree":
        rows_result = await session.execute(
            text(
                f"""
                SELECT
                    ri.id::text AS id,
                    ri.requirement_id::text AS requirement_id,
                    ri.layer::text AS layer,
                    ri.content AS content,
                    ri.version AS version,
                    ri.created_at AS created_at
                FROM risk_interpretation ri
                {where_clause}
                ORDER BY
                    ri.requirement_id::text,
                    ri.layer::text,
                    ri.version DESC NULLS LAST,
                    ri.created_at DESC NULLS LAST
                """
            ),
            params,
        )
        rows = rows_result.mappings().all()
        full_tree = _build_interpretation_tree(rows)
        page = full_tree[skip : skip + limit]

        return InterpretationTreeResponse(
            items=page,
            total_requirements=len(full_tree),
            skip=skip,
            limit=limit,
        )

    count_result = await session.execute(
        text(
            f"""
            SELECT COUNT(*) AS total
            FROM risk_interpretation ri
            {where_clause}
            """
        ),
        params,
    )
    total = int(count_result.scalar_one())

    page_params = {**params, "skip": skip, "limit": limit}
    rows_result = await session.execute(
        text(
            f"""
            SELECT
                ri.id::text AS id,
                ri.requirement_id::text AS requirement_id,
                ri.layer::text AS layer,
                ri.content AS content,
                ri.version AS version,
                ri.created_at AS created_at
            FROM risk_interpretation ri
            {where_clause}
            ORDER BY ri.created_at DESC NULLS LAST, ri.version DESC NULLS LAST
            OFFSET :skip
            LIMIT :limit
            """
        ),
        page_params,
    )
    items = [InterpretationItem(**row) for row in rows_result.mappings().all()]

    return InterpretationListResponse(items=items, total=total, skip=skip, limit=limit)


@router.post(
    "/catalog/interpretations",
    status_code=201,
    response_model=InterpretationItem,
    summary="Create interpretation",
    description=(
        "Creates a new interpretation version for a requirement/layer pair. "
        "If ENFORCE_ADMIN_SCOPE_CHECK=true, send header "
        "X-Governance-Scopes including governance.admin."
    ),
    responses={403: {"description": "governance.admin scope required"}},
)
async def create_interpretation(
    payload: InterpretationCreateRequest,
    _admin_scope: None = Depends(require_governance_admin_scope),
    session: AsyncSession = Depends(get_db_session),
) -> InterpretationItem:
    """Create an interpretation row and auto-increment version by requirement+layer."""
    requirement_result = await session.execute(
        text(
            """
            SELECT 1
            FROM requirement r
            WHERE r.id::text = :requirement_id
            """
        ),
        {"requirement_id": str(payload.requirement_id)},
    )
    if requirement_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Requirement not found")

    next_version_result = await session.execute(
        text(
            """
            SELECT COALESCE(MAX(ri.version), 0) + 1 AS next_version
            FROM risk_interpretation ri
            WHERE ri.requirement_id::text = :requirement_id
              AND ri.layer::text = :layer
            """
        ),
        {
            "requirement_id": str(payload.requirement_id),
            "layer": payload.layer,
        },
    )
    next_version = int(next_version_result.scalar_one())
    now = datetime.utcnow()

    created_result = await session.execute(
        text(
            """
            INSERT INTO risk_interpretation (
                id,
                requirement_id,
                layer,
                content,
                version,
                created_at
            )
            VALUES (
                :id,
                :requirement_id,
                :layer,
                :content,
                :version,
                :created_at
            )
            RETURNING
                id::text AS id,
                requirement_id::text AS requirement_id,
                layer::text AS layer,
                content AS content,
                version AS version,
                created_at AS created_at
            """
        ),
        {
            "id": str(uuid4()),
            "requirement_id": str(payload.requirement_id),
            "layer": payload.layer,
            "content": payload.content,
            "version": next_version,
            "created_at": now,
        },
    )
    await session.commit()

    row = created_result.mappings().first()
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create interpretation")
    return InterpretationItem(**row)
