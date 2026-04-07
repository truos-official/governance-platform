"""
MCP server - 11 tools - Phase 3.

Server name: ai-governance
Auth: Azure Entra ID OAuth2 client_credentials, scope: governance.read
Base URL: https://{governance-api-host}/mcp

Catalog tools (5):
  search_controls, get_control_detail, get_requirement_detail,
  list_controls_by_domain, get_interpretation_tree

Peer intelligence tools (6):
  get_peer_benchmarks, get_alignment_score, get_risk_tier,
  get_recommended_controls, get_gap_analysis, get_compliance_trend

Phase 3 implementation. Adapters injected from adapters/search and adapters/graph.
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import text


class GovernanceMCPServer:
    """
    Exposes the governance catalog and peer intelligence to external agents.
    Connected via MCP protocol - not a REST API.
    """

    def __init__(self, search_adapter, graph_adapter, db_session):
        self._search = search_adapter
        self._graph = graph_adapter
        self._db = db_session

    # ------------------------------------------------------------------
    # Catalog tools
    # ------------------------------------------------------------------

    async def search_controls(
        self,
        query: str,
        domain: str | None = None,
        top: int = 10,
    ) -> list[dict]:
        """Hybrid BM25 + vector + semantic search across catalog controls."""
        effective_top = max(1, min(top, 100))
        filters: dict[str, str] = {"type": "control"}
        if domain:
            filters["domain"] = domain

        rows, _ = await self._search.search(
            query=query,
            filters=filters,
            top=effective_top,
        )
        return [
            {
                "id": row.get("id"),
                "code": row.get("code"),
                "title": row.get("title"),
                "description": row.get("description"),
                "domain": row.get("domain"),
                "tier": row.get("tier"),
                "measurement_mode": row.get("measurement_mode"),
                "score": row.get("score"),
            }
            for row in rows
        ]

    async def get_control_detail(self, control_id: str) -> dict:
        """Full control detail including KPI definitions and tier."""
        control_result = await self._db.execute(
            text(
                """
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
                WHERE c.id::text = :control_id
                """
            ),
            {"control_id": control_id},
        )
        control = control_result.mappings().first()
        if control is None:
            raise LookupError("Control not found")

        metric_result = await self._db.execute(
            text(
                """
                SELECT
                    cmd.id::text AS id,
                    cmd.metric_name AS metric_name,
                    cmd.threshold AS threshold,
                    cmd.is_manual AS is_manual
                FROM control_metric_definition cmd
                WHERE cmd.control_id::text = :control_id
                ORDER BY cmd.metric_name
                """
            ),
            {"control_id": control_id},
        )
        metrics = [dict(row) for row in metric_result.mappings().all()]

        requirement_result = await self._db.execute(
            text(
                """
                SELECT
                    r.id::text AS id,
                    r.code AS code,
                    r.title AS title,
                    r.category AS category
                FROM control_requirement cr
                JOIN requirement r ON r.id = cr.requirement_id
                WHERE cr.control_id::text = :control_id
                ORDER BY r.code
                """
            ),
            {"control_id": control_id},
        )
        requirements = [dict(row) for row in requirement_result.mappings().all()]

        detail = dict(control)
        detail["metrics"] = metrics
        detail["requirements"] = requirements
        return detail

    async def get_requirement_detail(self, requirement_id: str) -> dict:
        """Requirement detail with 3-layer interpretation tree."""
        requirement_result = await self._db.execute(
            text(
                """
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
                WHERE r.id::text = :requirement_id
                """
            ),
            {"requirement_id": requirement_id},
        )
        requirement = requirement_result.mappings().first()
        if requirement is None:
            raise LookupError("Requirement not found")

        control_result = await self._db.execute(
            text(
                """
                SELECT
                    c.id::text AS id,
                    c.code AS code,
                    c.title AS title,
                    c.domain AS domain,
                    c.tier::text AS tier
                FROM control_requirement cr
                JOIN control c ON c.id = cr.control_id
                WHERE cr.requirement_id::text = :requirement_id
                ORDER BY c.code
                """
            ),
            {"requirement_id": requirement_id},
        )
        controls = [dict(row) for row in control_result.mappings().all()]
        interpretation_tree = await self.get_interpretation_tree(requirement_id)

        detail = dict(requirement)
        detail["controls"] = controls
        detail["interpretation_tree"] = interpretation_tree
        return detail

    async def list_controls_by_domain(self, domain: str) -> list[dict]:
        """
        List controls for a domain.
        Domains: RM, RO, LC, SE, OM, AA, GL, CO (13 total).
        """
        result = await self._db.execute(
            text(
                """
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
                WHERE LOWER(c.domain) = LOWER(:domain)
                ORDER BY c.code
                """
            ),
            {"domain": domain},
        )
        return [dict(row) for row in result.mappings().all()]

    async def get_interpretation_tree(self, requirement_id: str) -> dict:
        """
        Returns {source: ..., system: ..., user: ...} 3-layer interpretation.
        Source = regulatory text, System = platform interpretation, User = org override.
        """
        result = await self._db.execute(
            text(
                """
                SELECT
                    ri.id::text AS id,
                    ri.requirement_id::text AS requirement_id,
                    ri.layer::text AS layer,
                    ri.content AS content,
                    ri.version AS version,
                    ri.created_at AS created_at
                FROM risk_interpretation ri
                WHERE ri.requirement_id::text = :requirement_id
                ORDER BY
                    ri.layer::text,
                    ri.version DESC NULLS LAST,
                    ri.created_at DESC NULLS LAST
                """
            ),
            {"requirement_id": requirement_id},
        )

        layers: dict[str, list[dict]] = defaultdict(list)
        for row in result.mappings().all():
            created_at = row.get("created_at")
            layers[(row.get("layer") or "UNKNOWN").lower()].append(
                {
                    "id": row.get("id"),
                    "content": row.get("content"),
                    "version": row.get("version"),
                    "created_at": (
                        created_at.isoformat()
                        if isinstance(created_at, datetime)
                        else created_at
                    ),
                }
            )

        return {
            "requirement_id": requirement_id,
            "source": layers.get("source", []),
            "system": layers.get("system", []),
            "user": layers.get("user", []),
        }

    # ------------------------------------------------------------------
    # Peer intelligence tools
    # ------------------------------------------------------------------

    def get_peer_benchmarks(self, app_id: str) -> dict:
        """
        Peer benchmarks for same risk tier (minimum N=3 peers).
        Returns per-metric percentile positions.
        """
        raise NotImplementedError("Phase 3.8")

    def get_alignment_score(self, app_id: str) -> dict:
        """
        Alignment score breakdown.
        Formula: peer*0.50 + reg_density*0.30 + trend_velocity*0.20
        """
        raise NotImplementedError("Phase 3.8")

    def get_risk_tier(self, app_id: str) -> dict:
        """Current risk tier with NIST score + domain floor applied."""
        raise NotImplementedError("Phase 3.8")

    def get_recommended_controls(self, app_id: str) -> list[dict]:
        """Controls recommended based on gap analysis + peer benchmarks."""
        raise NotImplementedError("Phase 3.8")

    def get_gap_analysis(self, app_id: str) -> list[dict]:
        """Controls assigned but failing or with insufficient data."""
        raise NotImplementedError("Phase 3.8")

    def get_compliance_trend(self, app_id: str, window_days: int = 30) -> list[dict]:
        """Rolling compliance trend from metric_reading hypertable."""
        raise NotImplementedError("Phase 3.8")
