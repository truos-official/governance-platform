import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend root is importable regardless of pytest invocation style.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from mcp.server import GovernanceMCPServer


class _FakeMappings:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def all(self) -> list[dict]:
        return self._rows

    def first(self) -> dict | None:
        return self._rows[0] if self._rows else None


class _FakeResult:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._rows)


class _FakeDBSession:
    def __init__(self, results: list[_FakeResult]) -> None:
        self._results = list(results)
        self.calls: list[dict] = []

    async def execute(self, query, params: dict) -> _FakeResult:
        self.calls.append({"query": str(query), "params": params})
        if not self._results:
            raise AssertionError("Unexpected execute() call: no fake results remaining")
        return self._results.pop(0)


class _FakeSearchAdapter:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.calls: list[dict] = []

    async def search(
        self,
        query: str,
        filters: dict | None,
        top: int,
        *,
        skip: int = 0,
        order_by: list[str] | None = None,
        include_total_count: bool = False,
    ) -> tuple[list[dict], int | None]:
        self.calls.append(
            {
                "query": query,
                "filters": filters,
                "top": top,
                "skip": skip,
                "order_by": order_by,
                "include_total_count": include_total_count,
            }
        )
        return list(self._rows)[:top], None


class _FakeGraphAdapter:
    async def query(self, sparql: str) -> list[dict]:
        return []


def test_search_controls_applies_control_filter_and_domain() -> None:
    search = _FakeSearchAdapter(
        rows=[
            {
                "id": "c1",
                "code": "AA-1",
                "title": "Internal Audit",
                "domain": "AA",
                "tier": "FOUNDATION",
            }
        ]
    )
    server = GovernanceMCPServer(search, _FakeGraphAdapter(), _FakeDBSession([]))

    result = asyncio.run(server.search_controls(query="audit", domain="AA", top=5))

    assert len(result) == 1
    assert result[0]["code"] == "AA-1"
    assert search.calls[0]["filters"] == {"type": "control", "domain": "AA"}
    assert search.calls[0]["top"] == 5


def test_get_control_detail_includes_metrics_and_requirements() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(
                rows=[
                    {
                        "id": "ctrl-1",
                        "code": "AA-1",
                        "title": "Internal Audit",
                        "description": "desc",
                        "domain": "AA",
                        "tier": "FOUNDATION",
                        "is_foundation": True,
                        "measurement_mode": "hybrid",
                    }
                ]
            ),
            _FakeResult(
                rows=[
                    {
                        "id": "metric-1",
                        "metric_name": "ai.model.error_rate",
                        "threshold": {"operator": "<=", "value": 0.05},
                        "is_manual": False,
                    }
                ]
            ),
            _FakeResult(
                rows=[
                    {
                        "id": "req-1",
                        "code": "NIST-G10",
                        "title": "Human Oversight",
                        "category": "NIST",
                    }
                ]
            ),
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    detail = asyncio.run(server.get_control_detail("ctrl-1"))

    assert detail["id"] == "ctrl-1"
    assert len(detail["metrics"]) == 1
    assert detail["metrics"][0]["metric_name"] == "ai.model.error_rate"
    assert len(detail["requirements"]) == 1
    assert detail["requirements"][0]["code"] == "NIST-G10"


def test_get_requirement_detail_includes_controls_and_tree() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(
                rows=[
                    {
                        "id": "req-1",
                        "regulation_id": "reg-1",
                        "regulation_title": "Reg 1",
                        "jurisdiction": "US",
                        "code": "R-1",
                        "title": "Requirement 1",
                        "description": "desc",
                        "category": "CAT",
                    }
                ]
            ),
            _FakeResult(
                rows=[
                    {
                        "id": "ctrl-1",
                        "code": "AA-1",
                        "title": "Internal Audit",
                        "domain": "AA",
                        "tier": "FOUNDATION",
                    }
                ]
            ),
            _FakeResult(
                rows=[
                    {
                        "id": "int-1",
                        "requirement_id": "req-1",
                        "layer": "SOURCE",
                        "content": "source text",
                        "version": 1,
                        "created_at": datetime(2026, 4, 6, 10, 0, 0, tzinfo=timezone.utc),
                    }
                ]
            ),
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    detail = asyncio.run(server.get_requirement_detail("req-1"))

    assert detail["id"] == "req-1"
    assert len(detail["controls"]) == 1
    assert detail["controls"][0]["code"] == "AA-1"
    assert detail["interpretation_tree"]["source"][0]["content"] == "source text"
    assert detail["interpretation_tree"]["system"] == []


def test_list_controls_by_domain_returns_rows() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(
                rows=[
                    {
                        "id": "ctrl-1",
                        "code": "AA-1",
                        "title": "Internal Audit",
                        "description": "desc",
                        "domain": "AA",
                        "tier": "FOUNDATION",
                        "is_foundation": True,
                        "measurement_mode": "hybrid",
                    }
                ]
            )
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    rows = asyncio.run(server.list_controls_by_domain("AA"))

    assert len(rows) == 1
    assert rows[0]["domain"] == "AA"
    assert db.calls[0]["params"] == {"domain": "AA"}


def test_get_risk_tier_returns_latest_event_with_floor_applied() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(
                rows=[
                    {
                        "id": "app-1",
                        "domain": "criminal_justice",
                    }
                ]
            ),
            _FakeResult(
                rows=[
                    {
                        "new_tier": "MEDIUM",
                        "changed_at": datetime(2026, 4, 6, 12, 0, 0, tzinfo=timezone.utc),
                    }
                ]
            ),
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    result = asyncio.run(server.get_risk_tier("app-1"))

    assert result["app_id"] == "app-1"
    assert result["tier_raw"] == "MEDIUM"
    assert result["domain_floor"] == "HIGH"
    assert result["tier_effective"] == "HIGH"
    assert result["source"] == "tier_change_event"
    assert result["last_changed_at"] is not None


def test_get_risk_tier_defaults_low_when_no_events_and_applies_floor() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(
                rows=[
                    {
                        "id": "app-2",
                        "domain": "healthcare",
                    }
                ]
            ),
            _FakeResult(rows=[]),
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    result = asyncio.run(server.get_risk_tier("app-2"))

    assert result["tier_raw"] == "LOW"
    assert result["domain_floor"] == "MEDIUM"
    assert result["tier_effective"] == "MEDIUM"
    assert result["source"] == "default_low_no_events"
    assert result["last_changed_at"] is None


def test_get_risk_tier_raises_for_missing_application() -> None:
    db = _FakeDBSession(results=[_FakeResult(rows=[])])
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    try:
        asyncio.run(server.get_risk_tier("missing-app"))
        raise AssertionError("Expected LookupError for missing application")
    except LookupError as exc:
        assert str(exc) == "Application not found"


def test_get_risk_tier_coerces_invalid_raw_tier_to_low() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(
                rows=[
                    {
                        "id": "app-3",
                        "domain": "financial",
                    }
                ]
            ),
            _FakeResult(
                rows=[
                    {
                        "new_tier": "CRITICAL",
                        "changed_at": datetime(2026, 4, 6, 12, 30, 0, tzinfo=timezone.utc),
                    }
                ]
            ),
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    result = asyncio.run(server.get_risk_tier("app-3"))

    assert result["tier_raw"] == "LOW"
    assert result["domain_floor"] == "MEDIUM"
    assert result["tier_effective"] == "MEDIUM"


def test_get_peer_benchmarks_returns_metric_percentiles() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(
                rows=[
                    {
                        "app_id": "app-1",
                        "domain": "healthcare",
                        "new_tier": "LOW",
                    }
                ]
            ),
            _FakeResult(
                rows=[
                    {"app_id": "peer-1", "domain": "healthcare", "new_tier": "LOW"},
                    {"app_id": "peer-2", "domain": "financial", "new_tier": "LOW"},
                    {"app_id": "peer-3", "domain": "education", "new_tier": "MEDIUM"},
                    {"app_id": "peer-4", "domain": "criminal_justice", "new_tier": "MEDIUM"},
                ]
            ),
            _FakeResult(
                rows=[
                    {"app_id": "app-1", "metric_name": "ai.model.error_rate", "value": 0.20},
                    {"app_id": "peer-1", "metric_name": "ai.model.error_rate", "value": 0.10},
                    {"app_id": "peer-2", "metric_name": "ai.model.error_rate", "value": 0.30},
                    {"app_id": "peer-3", "metric_name": "ai.model.error_rate", "value": 0.40},
                    {"app_id": "app-1", "metric_name": "ai.latency.p95_ms", "value": 120.0},
                    {"app_id": "peer-1", "metric_name": "ai.latency.p95_ms", "value": 150.0},
                    {"app_id": "peer-2", "metric_name": "ai.latency.p95_ms", "value": 130.0},
                    {"app_id": "peer-3", "metric_name": "ai.latency.p95_ms", "value": 110.0},
                ]
            ),
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    result = asyncio.run(server.get_peer_benchmarks("app-1"))

    assert result["app_id"] == "app-1"
    assert result["tier"] == "MEDIUM"
    assert result["peer_count"] == 3
    assert len(result["metrics"]) == 2

    by_name = {item["metric_name"]: item for item in result["metrics"]}
    assert by_name["ai.model.error_rate"]["peer_average"] == 0.266667
    assert by_name["ai.model.error_rate"]["percentile"] == 50.0
    assert by_name["ai.model.error_rate"]["sample_size"] == 4


def test_get_peer_benchmarks_raises_when_insufficient_peers() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(rows=[{"app_id": "app-1", "domain": "healthcare", "new_tier": "LOW"}]),
            _FakeResult(
                rows=[
                    {"app_id": "peer-1", "domain": "healthcare", "new_tier": "LOW"},
                    {"app_id": "peer-2", "domain": "education", "new_tier": "MEDIUM"},
                ]
            ),
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    try:
        asyncio.run(server.get_peer_benchmarks("app-1"))
        raise AssertionError("Expected ValueError for insufficient peers")
    except ValueError as exc:
        assert str(exc) == "Insufficient peers: minimum 3 peers required"


def test_get_peer_benchmarks_raises_for_missing_application() -> None:
    db = _FakeDBSession(results=[_FakeResult(rows=[])])
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    try:
        asyncio.run(server.get_peer_benchmarks("missing-app"))
        raise AssertionError("Expected LookupError for missing application")
    except LookupError as exc:
        assert str(exc) == "Application not found"


def test_get_alignment_score_returns_weighted_components() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(
                rows=[
                    {
                        "app_id": "app-1",
                        "domain": "healthcare",
                        "new_tier": "LOW",
                    }
                ]
            ),
            _FakeResult(
                rows=[
                    {"app_id": "peer-1", "domain": "healthcare", "new_tier": "LOW"},
                    {"app_id": "peer-2", "domain": "financial", "new_tier": "LOW"},
                    {"app_id": "peer-3", "domain": "education", "new_tier": "MEDIUM"},
                    {"app_id": "peer-4", "domain": "criminal_justice", "new_tier": "LOW"},
                ]
            ),
            _FakeResult(
                rows=[
                    {"app_id": "app-1", "metric_name": "ai.model.error_rate", "value": 0.20},
                    {"app_id": "peer-1", "metric_name": "ai.model.error_rate", "value": 0.10},
                    {"app_id": "peer-2", "metric_name": "ai.model.error_rate", "value": 0.30},
                    {"app_id": "peer-3", "metric_name": "ai.model.error_rate", "value": 0.40},
                ]
            ),
            _FakeResult(
                rows=[
                    {"app_id": "app-1", "control_count": 8},
                    {"app_id": "peer-1", "control_count": 6},
                    {"app_id": "peer-2", "control_count": 8},
                    {"app_id": "peer-3", "control_count": 10},
                ]
            ),
            _FakeResult(rows=[{"current_pass_rate": 0.9, "previous_pass_rate": 0.7}]),
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    result = asyncio.run(server.get_alignment_score("app-1"))

    assert result["tier"] == "MEDIUM"
    assert result["peer_count"] == 3
    assert result["components"]["peer_score"] == 0.5
    assert result["components"]["reg_density"] == 1.0
    assert result["components"]["trend_velocity"] == 0.6
    assert result["score"] == 0.67


def test_get_alignment_score_raises_when_insufficient_peers() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(rows=[{"app_id": "app-1", "domain": "healthcare", "new_tier": "LOW"}]),
            _FakeResult(
                rows=[
                    {"app_id": "peer-1", "domain": "healthcare", "new_tier": "LOW"},
                    {"app_id": "peer-2", "domain": "education", "new_tier": "MEDIUM"},
                ]
            ),
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    try:
        asyncio.run(server.get_alignment_score("app-1"))
        raise AssertionError("Expected ValueError for insufficient peers")
    except ValueError as exc:
        assert str(exc) == "Insufficient peers: minimum 3 peers required"


def test_get_alignment_score_raises_for_missing_application() -> None:
    db = _FakeDBSession(results=[_FakeResult(rows=[])])
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    try:
        asyncio.run(server.get_alignment_score("missing-app"))
        raise AssertionError("Expected LookupError for missing application")
    except LookupError as exc:
        assert str(exc) == "Application not found"


def test_get_gap_analysis_returns_failing_and_insufficient_controls() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(rows=[{"app_id": "app-1", "domain": "healthcare", "new_tier": "LOW"}]),
            _FakeResult(
                rows=[
                    {
                        "control_id": "c-1",
                        "control_code": "AA-1",
                        "control_title": "Internal Audit",
                        "domain": "AA",
                        "control_tier": "FOUNDATION",
                        "measurement_mode": "hybrid",
                        "metric_name": "ai.model.error_rate",
                        "result": "FAIL",
                        "value": 0.21,
                        "calculated_at": datetime(2026, 4, 6, 13, 0, 0, tzinfo=timezone.utc),
                    },
                    {
                        "control_id": "c-2",
                        "control_code": "OM-1",
                        "control_title": "Model Ops",
                        "domain": "OM",
                        "control_tier": "COMMON",
                        "measurement_mode": "system_calculated",
                        "metric_name": "ai.latency.p95_ms",
                        "result": "INSUFFICIENT_DATA",
                        "value": None,
                        "calculated_at": datetime(2026, 4, 6, 13, 5, 0, tzinfo=timezone.utc),
                    },
                    {
                        "control_id": "c-3",
                        "control_code": "RM-1",
                        "control_title": "Risk Mgmt",
                        "domain": "RM",
                        "control_tier": "COMMON",
                        "measurement_mode": "manual",
                        "metric_name": "ai.false_positive_rate",
                        "result": "PASS",
                        "value": 0.03,
                        "calculated_at": datetime(2026, 4, 6, 13, 10, 0, tzinfo=timezone.utc),
                    },
                ]
            ),
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    gaps = asyncio.run(server.get_gap_analysis("app-1"))

    assert len(gaps) == 2
    assert gaps[0]["result"] == "FAIL"
    assert gaps[0]["gap_type"] == "threshold_breach"
    assert gaps[0]["priority"] == "HIGH"
    assert gaps[1]["result"] == "INSUFFICIENT_DATA"
    assert gaps[1]["gap_type"] == "insufficient_data"
    assert gaps[1]["priority"] == "MEDIUM"


def test_get_gap_analysis_raises_for_missing_application() -> None:
    db = _FakeDBSession(results=[_FakeResult(rows=[])])
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    try:
        asyncio.run(server.get_gap_analysis("missing-app"))
        raise AssertionError("Expected LookupError for missing application")
    except LookupError as exc:
        assert str(exc) == "Application not found"


def test_get_compliance_trend_returns_daily_points() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(rows=[{"app_id": "app-1", "domain": "healthcare", "new_tier": "LOW"}]),
            _FakeResult(
                rows=[
                    {
                        "day": "2026-04-04",
                        "pass_count": 8,
                        "fail_count": 2,
                        "insufficient_count": 1,
                        "evaluated_count": 10,
                        "compliance_rate": 0.8,
                    },
                    {
                        "day": "2026-04-05",
                        "pass_count": 9,
                        "fail_count": 1,
                        "insufficient_count": 0,
                        "evaluated_count": 10,
                        "compliance_rate": 0.9,
                    },
                ]
            ),
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    points = asyncio.run(server.get_compliance_trend("app-1", window_days=30))

    assert len(points) == 2
    assert points[0]["day"] == "2026-04-04"
    assert points[0]["pass_count"] == 8
    assert points[0]["compliance_rate"] == 0.8
    assert points[1]["compliance_rate"] == 0.9


def test_get_compliance_trend_raises_for_missing_application() -> None:
    db = _FakeDBSession(results=[_FakeResult(rows=[])])
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    try:
        asyncio.run(server.get_compliance_trend("missing-app", window_days=30))
        raise AssertionError("Expected LookupError for missing application")
    except LookupError as exc:
        assert str(exc) == "Application not found"


def test_get_recommended_controls_combines_gap_and_peer_signals() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(rows=[{"app_id": "app-1", "domain": "healthcare", "new_tier": "LOW"}]),
            _FakeResult(
                rows=[
                    {
                        "control_id": "c-1",
                        "control_code": "AA-1",
                        "control_title": "Internal Audit",
                        "domain": "AA",
                        "control_tier": "FOUNDATION",
                        "measurement_mode": "hybrid",
                        "metric_name": "ai.model.error_rate",
                        "result": "FAIL",
                        "value": 0.2,
                        "calculated_at": "2026-04-06T13:00:00+00:00",
                    },
                    {
                        "control_id": "c-2",
                        "control_code": "OM-1",
                        "control_title": "Model Ops",
                        "domain": "OM",
                        "control_tier": "COMMON",
                        "measurement_mode": "manual",
                        "metric_name": "ai.latency.p95_ms",
                        "result": "INSUFFICIENT_DATA",
                        "value": None,
                        "calculated_at": "2026-04-06T13:05:00+00:00",
                    },
                ]
            ),
            _FakeResult(rows=[{"app_id": "app-1", "domain": "healthcare", "new_tier": "LOW"}]),
            _FakeResult(
                rows=[
                    {"app_id": "peer-1", "domain": "healthcare", "new_tier": "LOW"},
                    {"app_id": "peer-2", "domain": "financial", "new_tier": "LOW"},
                    {"app_id": "peer-3", "domain": "education", "new_tier": "MEDIUM"},
                    {"app_id": "peer-4", "domain": "criminal_justice", "new_tier": "LOW"},
                ]
            ),
            _FakeResult(
                rows=[
                    {"app_id": "app-1", "metric_name": "ai.model.error_rate", "value": 0.8},
                    {"app_id": "peer-1", "metric_name": "ai.model.error_rate", "value": 0.7},
                    {"app_id": "peer-2", "metric_name": "ai.model.error_rate", "value": 0.6},
                    {"app_id": "peer-3", "metric_name": "ai.model.error_rate", "value": 0.5},
                    {"app_id": "app-1", "metric_name": "ai.latency.p95_ms", "value": 0.2},
                    {"app_id": "peer-1", "metric_name": "ai.latency.p95_ms", "value": 0.4},
                    {"app_id": "peer-2", "metric_name": "ai.latency.p95_ms", "value": 0.3},
                    {"app_id": "peer-3", "metric_name": "ai.latency.p95_ms", "value": 0.5},
                ]
            ),
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    recommendations = asyncio.run(server.get_recommended_controls("app-1"))

    assert len(recommendations) == 2
    assert recommendations[0]["control_code"] == "AA-1"
    assert recommendations[0]["priority"] == "HIGH"
    assert recommendations[0]["peer_count"] == 3

    rec_by_code = {item["control_code"]: item for item in recommendations}
    assert rec_by_code["OM-1"]["measurement_mode"] == "manual"
    assert "Submit manual evidence" in " ".join(rec_by_code["OM-1"]["recommended_actions"])
    assert rec_by_code["OM-1"]["metric_gaps"][0]["peer_percentile"] == 25.0


def test_get_recommended_controls_falls_back_when_peers_insufficient() -> None:
    db = _FakeDBSession(
        results=[
            _FakeResult(rows=[{"app_id": "app-1", "domain": "healthcare", "new_tier": "LOW"}]),
            _FakeResult(
                rows=[
                    {
                        "control_id": "c-1",
                        "control_code": "AA-1",
                        "control_title": "Internal Audit",
                        "domain": "AA",
                        "control_tier": "FOUNDATION",
                        "measurement_mode": "hybrid",
                        "metric_name": "ai.model.error_rate",
                        "result": "FAIL",
                        "value": 0.2,
                        "calculated_at": "2026-04-06T13:00:00+00:00",
                    }
                ]
            ),
            _FakeResult(rows=[{"app_id": "app-1", "domain": "healthcare", "new_tier": "LOW"}]),
            _FakeResult(
                rows=[
                    {"app_id": "peer-1", "domain": "healthcare", "new_tier": "LOW"},
                    {"app_id": "peer-2", "domain": "education", "new_tier": "MEDIUM"},
                ]
            ),
        ]
    )
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    recommendations = asyncio.run(server.get_recommended_controls("app-1"))

    assert len(recommendations) == 1
    assert recommendations[0]["peer_count"] == 0
    assert recommendations[0]["metric_gaps"][0]["peer_percentile"] is None


def test_get_recommended_controls_raises_for_missing_application() -> None:
    db = _FakeDBSession(results=[_FakeResult(rows=[])])
    server = GovernanceMCPServer(_FakeSearchAdapter([]), _FakeGraphAdapter(), db)

    try:
        asyncio.run(server.get_recommended_controls("missing-app"))
        raise AssertionError("Expected LookupError for missing application")
    except LookupError as exc:
        assert str(exc) == "Application not found"
