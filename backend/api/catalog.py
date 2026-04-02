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
from fastapi import APIRouter

router = APIRouter(tags=["catalog"])


@router.get("/catalog/controls")
def list_controls(domain: str | None = None, tier: str | None = None, skip: int = 0, limit: int = 100):
    raise NotImplementedError("Phase 3.1")


@router.get("/catalog/controls/{control_id}")
def get_control(control_id: str):
    raise NotImplementedError("Phase 3.1")


@router.get("/catalog/requirements")
def list_requirements(control_id: str | None = None, skip: int = 0, limit: int = 100):
    raise NotImplementedError("Phase 3.1")


@router.get("/catalog/requirements/{req_id}")
def get_requirement(req_id: str):
    raise NotImplementedError("Phase 3.1")


@router.get("/catalog/interpretations")
def list_interpretations():
    raise NotImplementedError("Phase 3.4")


@router.post("/catalog/interpretations", status_code=201)
def create_interpretation():
    """Admin only — requires governance.admin scope."""
    raise NotImplementedError("Phase 3.4")
