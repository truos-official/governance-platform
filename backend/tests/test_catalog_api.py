import sys
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

# Ensure backend root is importable regardless of pytest invocation style.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from db.session import get_db_session
from main import app


class _FakeMappings:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def all(self) -> list[dict]:
        return self._rows

    def first(self) -> dict | None:
        return self._rows[0] if self._rows else None


class _FakeResult:
    def __init__(self, *, scalar: int | None = None, rows: list[dict] | None = None) -> None:
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one(self) -> int:
        if self._scalar is None:
            raise AssertionError("scalar_one() called without scalar value")
        return self._scalar

    def scalar_one_or_none(self) -> int | None:
        return self._scalar

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._rows)


class _FakeSession:
    def __init__(self, results: list[_FakeResult]) -> None:
        self._results = list(results)
        self.calls: list[tuple[tuple, dict]] = []
        self.committed = False

    async def execute(self, *_args, **_kwargs) -> _FakeResult:
        self.calls.append((_args, _kwargs))
        if not self._results:
            raise AssertionError("Unexpected execute() call: no fake results remaining")
        return self._results.pop(0)

    async def commit(self) -> None:
        self.committed = True


def _override_with(session: _FakeSession):
    async def _dependency() -> AsyncGenerator[_FakeSession, None]:
        yield session

    return _dependency


class _FakeSearchAdapter:
    def __init__(self, results: list[dict]) -> None:
        self._results = results
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
        rows = list(self._results)

        if order_by:
            for clause in reversed(order_by):
                field, direction = clause.split()
                reverse = direction.lower() == "desc"
                rows.sort(key=lambda item: str(item.get(field) or "").lower(), reverse=reverse)

        page = rows[skip : skip + top]
        total = len(rows) if include_total_count else None
        return page, total


def test_list_controls_returns_items() -> None:
    fake_session = _FakeSession(
        results=[
            _FakeResult(scalar=1),
            _FakeResult(
                rows=[
                    {
                        "id": "b9ff9468-27e7-43f0-bce1-0e3d41b29119",
                        "code": "AA-1",
                        "title": "Internal Audit",
                        "description": "desc",
                        "domain": "audit",
                        "tier": "FOUNDATION",
                        "is_foundation": True,
                        "measurement_mode": "hybrid",
                    }
                ]
            ),
        ]
    )
    app.dependency_overrides[get_db_session] = _override_with(fake_session)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/catalog/controls?limit=10")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["code"] == "AA-1"
    finally:
        app.dependency_overrides.clear()


def test_get_control_returns_item() -> None:
    fake_session = _FakeSession(
        results=[
            _FakeResult(
                rows=[
                    {
                        "id": "b9ff9468-27e7-43f0-bce1-0e3d41b29119",
                        "code": "AA-1",
                        "title": "Internal Audit",
                        "description": "desc",
                        "domain": "audit",
                        "tier": "FOUNDATION",
                        "is_foundation": True,
                        "measurement_mode": "hybrid",
                    }
                ]
            )
        ]
    )
    app.dependency_overrides[get_db_session] = _override_with(fake_session)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/catalog/controls/b9ff9468-27e7-43f0-bce1-0e3d41b29119")
        assert response.status_code == 200
        assert response.json()["code"] == "AA-1"
    finally:
        app.dependency_overrides.clear()


def test_list_requirements_returns_items() -> None:
    fake_session = _FakeSession(
        results=[
            _FakeResult(scalar=1),
            _FakeResult(
                rows=[
                    {
                        "id": "0e3051e6-570f-40e2-aac1-6330eed86acf",
                        "regulation_id": "00000000-0000-0000-0000-000000000001",
                        "regulation_title": "Unlinked - Phase 3",
                        "jurisdiction": "PLACEHOLDER",
                        "code": "CA-001",
                        "title": "Requirement Title",
                        "description": "Requirement Description",
                        "category": "California AI Laws",
                    }
                ]
            ),
        ]
    )
    app.dependency_overrides[get_db_session] = _override_with(fake_session)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/catalog/requirements?limit=10")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["code"] == "CA-001"
    finally:
        app.dependency_overrides.clear()


def test_get_requirement_not_found_returns_404() -> None:
    fake_session = _FakeSession(results=[_FakeResult(rows=[])])
    app.dependency_overrides[get_db_session] = _override_with(fake_session)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/catalog/requirements/00000000-0000-0000-0000-000000000999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Requirement not found"
    finally:
        app.dependency_overrides.clear()


def test_unified_search_returns_items_and_facets(monkeypatch) -> None:
    from api import catalog as catalog_module

    adapter = _FakeSearchAdapter(
        results=[
            {
                "id": "requirement_a1",
                "code": "NIST-G10",
                "title": "Human Oversight Requirement",
                "description": "desc",
                "type": "requirement",
                "domain": None,
                "tier": None,
                "measurement_mode": None,
                "source": "NIST",
                "jurisdiction": "PLACEHOLDER",
                "score": 10.0,
            },
            {
                "id": "control_b1",
                "code": "RS-1",
                "title": "Human Oversight Control",
                "description": "desc",
                "type": "control",
                "domain": "responsible systems",
                "tier": "COMMON",
                "measurement_mode": "system_calculated",
                "source": "UN",
                "jurisdiction": None,
                "score": 9.0,
            },
        ]
    )
    monkeypatch.setattr(catalog_module, "get_search_adapter", lambda index_name: adapter)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/search?q=human oversight&limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 2
    assert payload["facets"]["type"]["requirement"] == 1
    assert payload["facets"]["type"]["control"] == 1


def test_unified_search_passes_filters_to_adapter(monkeypatch) -> None:
    from api import catalog as catalog_module

    adapter = _FakeSearchAdapter(results=[])
    monkeypatch.setattr(catalog_module, "get_search_adapter", lambda index_name: adapter)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/catalog/search?q=oversight&type=requirement"
            "&tier=COMMON&measurement_mode=manual&skip=5&limit=7"
        )

    assert response.status_code == 200
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["query"] == "oversight"
    assert adapter.calls[0]["filters"] == {
        "type": "requirement",
        "tier": "COMMON",
        "measurement_mode": "manual",
    }
    assert adapter.calls[0]["top"] == 7
    assert adapter.calls[0]["skip"] == 5
    assert adapter.calls[0]["order_by"] is None
    assert adapter.calls[0]["include_total_count"] is True


def test_unified_search_returns_503_when_adapter_config_missing(monkeypatch) -> None:
    from api import catalog as catalog_module

    def _raise_missing(*_args, **_kwargs):
        raise ValueError("AZURE_SEARCH_KEY environment variable is not set")

    monkeypatch.setattr(catalog_module, "get_search_adapter", _raise_missing)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/search?q=oversight")

    assert response.status_code == 503
    assert response.json()["detail"] == "AZURE_SEARCH_KEY environment variable is not set"


def test_unified_search_applies_skip_limit_pagination(monkeypatch) -> None:
    from api import catalog as catalog_module

    adapter = _FakeSearchAdapter(
        results=[
            {"id": "doc_1", "type": "requirement", "score": 9.0},
            {"id": "doc_2", "type": "control", "score": 8.0},
            {"id": "doc_3", "type": "control", "score": 7.0},
        ]
    )
    monkeypatch.setattr(catalog_module, "get_search_adapter", lambda index_name: adapter)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/search?q=oversight&skip=1&limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["skip"] == 1
    assert payload["limit"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == "doc_2"


def test_unified_search_forwards_sort_to_adapter(monkeypatch) -> None:
    from api import catalog as catalog_module

    adapter = _FakeSearchAdapter(
        results=[
            {"id": "doc_1", "code": "B-20", "title": "Beta", "type": "control", "score": 2.0},
            {"id": "doc_2", "code": "A-10", "title": "Alpha", "type": "control", "score": 1.0},
        ]
    )
    monkeypatch.setattr(catalog_module, "get_search_adapter", lambda index_name: adapter)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/search?q=oversight&sort=code&limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert [item["code"] for item in payload["items"]] == ["A-10", "B-20"]
    assert adapter.calls[0]["order_by"] == ["code asc", "title asc"]


def test_unified_search_requires_query_param_q() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/search")

    assert response.status_code == 422


def test_unified_search_rejects_invalid_sort_value() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/search?q=oversight&sort=priority")

    assert response.status_code == 422


def test_autocomplete_returns_suggestions(monkeypatch) -> None:
    from api import catalog as catalog_module

    adapter = _FakeSearchAdapter(
        results=[
            {"id": "requirement_a1", "title": "Human Oversight Requirement", "type": "requirement", "code": "NIST-G10"},
            {"id": "control_b1", "title": "Human Oversight", "type": "control", "code": "RS-1"},
        ]
    )
    monkeypatch.setattr(catalog_module, "get_search_adapter", lambda index_name: adapter)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/autocomplete?q=oversight&limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["items"][0]["label"] == "Human Oversight Requirement"


def test_autocomplete_passes_type_filter(monkeypatch) -> None:
    from api import catalog as catalog_module

    adapter = _FakeSearchAdapter(results=[])
    monkeypatch.setattr(catalog_module, "get_search_adapter", lambda index_name: adapter)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/autocomplete?q=oversight&type=requirement&limit=3")

    assert response.status_code == 200
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["filters"] == {"type": "requirement"}
    assert adapter.calls[0]["top"] == 3


def test_autocomplete_requires_query_param_q() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/autocomplete")

    assert response.status_code == 422


def test_list_interpretations_returns_empty() -> None:
    fake_session = _FakeSession(
        results=[
            _FakeResult(scalar=0),
            _FakeResult(rows=[]),
        ]
    )
    app.dependency_overrides[get_db_session] = _override_with(fake_session)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/catalog/interpretations?limit=5")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 0
        assert payload["items"] == []
    finally:
        app.dependency_overrides.clear()


def test_list_interpretations_with_filters_returns_items() -> None:
    req_id = "0e3051e6-570f-40e2-aac1-6330eed86acf"
    fake_session = _FakeSession(
        results=[
            _FakeResult(scalar=1),
            _FakeResult(
                rows=[
                    {
                        "id": "f10d2441-e9b0-4a02-b705-4ac8ba3348f5",
                        "requirement_id": req_id,
                        "layer": "SOURCE",
                        "content": "Initial interpretation",
                        "version": 1,
                        "created_at": datetime(2026, 4, 6, 12, 0, 0, tzinfo=timezone.utc),
                    }
                ]
            ),
        ]
    )
    app.dependency_overrides[get_db_session] = _override_with(fake_session)

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/catalog/interpretations?requirement_id={req_id}&layer=SOURCE&limit=5"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["layer"] == "SOURCE"
        assert payload["items"][0]["requirement_id"] == req_id

        # Verify endpoint passed filter parameters into SQL execution.
        count_call_args = fake_session.calls[0][0]
        assert count_call_args[1]["requirement_id"] == req_id
        assert count_call_args[1]["layer"] == "SOURCE"
    finally:
        app.dependency_overrides.clear()


def test_list_interpretations_tree_view_returns_grouped_nodes() -> None:
    req_id = "0e3051e6-570f-40e2-aac1-6330eed86acf"
    fake_session = _FakeSession(
        results=[
            _FakeResult(
                rows=[
                    {
                        "id": "f10d2441-e9b0-4a02-b705-4ac8ba3348f5",
                        "requirement_id": req_id,
                        "layer": "SOURCE",
                        "content": "Source interpretation",
                        "version": 2,
                        "created_at": datetime(2026, 4, 6, 12, 0, 0, tzinfo=timezone.utc),
                    },
                    {
                        "id": "02ad28dc-c60b-4607-a965-f6bb6dbf71de",
                        "requirement_id": req_id,
                        "layer": "SYSTEM",
                        "content": "System interpretation",
                        "version": 1,
                        "created_at": datetime(2026, 4, 6, 11, 0, 0, tzinfo=timezone.utc),
                    },
                ]
            ),
        ]
    )
    app.dependency_overrides[get_db_session] = _override_with(fake_session)

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/catalog/interpretations?view=tree&requirement_id={req_id}&limit=5"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total_requirements"] == 1
        assert len(payload["items"]) == 1
        assert payload["items"][0]["requirement_id"] == req_id
        layers = {layer["layer"] for layer in payload["items"][0]["layers"]}
        assert layers == {"SOURCE", "SYSTEM"}

        first_call_args = fake_session.calls[0][0]
        assert first_call_args[1]["requirement_id"] == req_id
    finally:
        app.dependency_overrides.clear()


def test_legacy_interpretations_tree_route_not_found() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/interpretations/tree")

    assert response.status_code == 404


def test_create_interpretation_returns_201_and_commits() -> None:
    req_id = "0e3051e6-570f-40e2-aac1-6330eed86acf"
    fake_session = _FakeSession(
        results=[
            _FakeResult(scalar=1),  # requirement exists
            _FakeResult(scalar=1),  # next version
            _FakeResult(
                rows=[
                    {
                        "id": "7f78a395-4494-4455-9cbf-28cbfc758541",
                        "requirement_id": req_id,
                        "layer": "SYSTEM",
                        "content": "System interpretation seed from API",
                        "version": 1,
                        "created_at": datetime(2026, 4, 6, 21, 58, 12),
                    }
                ]
            ),
        ]
    )
    app.dependency_overrides[get_db_session] = _override_with(fake_session)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/catalog/interpretations",
                json={
                    "requirement_id": req_id,
                    "layer": "SYSTEM",
                    "content": "System interpretation seed from API",
                },
            )
        assert response.status_code == 201
        payload = response.json()
        assert payload["requirement_id"] == req_id
        assert payload["layer"] == "SYSTEM"
        assert payload["version"] == 1
        assert fake_session.committed is True
    finally:
        app.dependency_overrides.clear()


def test_create_interpretation_returns_404_for_missing_requirement() -> None:
    fake_session = _FakeSession(results=[_FakeResult(scalar=None)])  # requirement missing
    app.dependency_overrides[get_db_session] = _override_with(fake_session)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/catalog/interpretations",
                json={
                    "requirement_id": "00000000-0000-0000-0000-000000000999",
                    "layer": "SOURCE",
                    "content": "missing req",
                },
            )
        assert response.status_code == 404
        assert response.json()["detail"] == "Requirement not found"
    finally:
        app.dependency_overrides.clear()


def test_create_interpretation_increments_version_per_requirement_layer() -> None:
    req_id = "0e3051e6-570f-40e2-aac1-6330eed86acf"
    fake_session = _FakeSession(
        results=[
            _FakeResult(scalar=1),  # requirement exists
            _FakeResult(scalar=4),  # next version should be 4
            _FakeResult(
                rows=[
                    {
                        "id": "d70fdf0b-5a6d-4f2d-9d9e-55840ecdf335",
                        "requirement_id": req_id,
                        "layer": "SOURCE",
                        "content": "Versioned interpretation",
                        "version": 4,
                        "created_at": datetime(2026, 4, 6, 22, 0, 0),
                    }
                ]
            ),
        ]
    )
    app.dependency_overrides[get_db_session] = _override_with(fake_session)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/catalog/interpretations",
                json={
                    "requirement_id": req_id,
                    "layer": "SOURCE",
                    "content": "Versioned interpretation",
                },
            )
        assert response.status_code == 201
        payload = response.json()
        assert payload["version"] == 4
    finally:
        app.dependency_overrides.clear()


def test_create_interpretation_rejects_empty_content() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/catalog/interpretations",
            json={
                "requirement_id": "0e3051e6-570f-40e2-aac1-6330eed86acf",
                "layer": "SYSTEM",
                "content": "",
            },
        )

    assert response.status_code == 422


def test_create_interpretation_rejects_whitespace_only_content() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/catalog/interpretations",
            json={
                "requirement_id": "0e3051e6-570f-40e2-aac1-6330eed86acf",
                "layer": "SYSTEM",
                "content": "   ",
            },
        )

    assert response.status_code == 422


def test_create_interpretation_requires_admin_scope_when_enforced(monkeypatch) -> None:
    monkeypatch.setenv("ENFORCE_ADMIN_SCOPE_CHECK", "true")

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/catalog/interpretations",
            json={
                "requirement_id": "0e3051e6-570f-40e2-aac1-6330eed86acf",
                "layer": "SYSTEM",
                "content": "Blocked without scope",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "governance.admin scope required"


def test_create_interpretation_allows_admin_scope_when_enforced(monkeypatch) -> None:
    monkeypatch.setenv("ENFORCE_ADMIN_SCOPE_CHECK", "true")

    req_id = "0e3051e6-570f-40e2-aac1-6330eed86acf"
    fake_session = _FakeSession(
        results=[
            _FakeResult(scalar=1),  # requirement exists
            _FakeResult(scalar=1),  # next version
            _FakeResult(
                rows=[
                    {
                        "id": "d0a6f8d3-49cb-4a03-bd9b-c8d5ba9807c1",
                        "requirement_id": req_id,
                        "layer": "SYSTEM",
                        "content": "Allowed with scope",
                        "version": 1,
                        "created_at": datetime(2026, 4, 6, 22, 5, 0),
                    }
                ]
            ),
        ]
    )
    app.dependency_overrides[get_db_session] = _override_with(fake_session)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/catalog/interpretations",
                headers={"X-Governance-Scopes": "governance.read governance.admin"},
                json={
                    "requirement_id": req_id,
                    "layer": "SYSTEM",
                    "content": "Allowed with scope",
                },
            )
        assert response.status_code == 201
        assert response.json()["content"] == "Allowed with scope"
    finally:
        app.dependency_overrides.clear()
