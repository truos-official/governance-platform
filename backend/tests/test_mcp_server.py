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
