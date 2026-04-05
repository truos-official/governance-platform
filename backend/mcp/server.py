"""
MCP server — 11 tools — Phase 3.

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
class GovernanceMCPServer:
    """
    Exposes the governance catalog and peer intelligence to external agents.
    Connected via MCP protocol — not a REST API.
    """

    def __init__(self, search_adapter, graph_adapter, db_session):
        self._search = search_adapter
        self._graph = graph_adapter
        self._db = db_session

    # ------------------------------------------------------------------
    # Catalog tools
    # ------------------------------------------------------------------

    def search_controls(self, query: str, domain: str | None = None, top: int = 10) -> list[dict]:
        """Hybrid BM25 + vector + semantic search across 59 controls."""
        raise NotImplementedError("Phase 3.5")

    def get_control_detail(self, control_id: str) -> dict:
        """Full control detail including KPI definitions and tier."""
        raise NotImplementedError("Phase 3.5")

    def get_requirement_detail(self, requirement_id: str) -> dict:
        """Requirement detail with 3-layer interpretation tree."""
        raise NotImplementedError("Phase 3.5")

    def list_controls_by_domain(self, domain: str) -> list[dict]:
        """
        List controls for a domain.
        Domains: RM, RO, LC, SE, OM, AA, GL, CO (13 total).
        """
        raise NotImplementedError("Phase 3.5")

    def get_interpretation_tree(self, requirement_id: str) -> dict:
        """
        Returns {source: ..., system: ..., user: ...} 3-layer interpretation.
        Source = regulatory text, System = platform interpretation, User = org override.
        """
        raise NotImplementedError("Phase 3.5")

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
