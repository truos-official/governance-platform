"""
GET    /applications/{id}/compliance          — compliance summary
POST   /applications/{id}/compliance          — trigger compliance recalculation
GET    /applications/{id}/compliance/controls — per-control evidence
GET    /curation/queue                        — curation queue (admin)
POST   /curation/queue                        — submit curation item (admin)

KPI model: pull on demand when dashboard loads — NOT pre-scheduled.
Phase 4 implementation.
"""
from fastapi import APIRouter

router = APIRouter(tags=["compliance"])


@router.get("/applications/{app_id}/compliance")
def get_compliance(app_id: str):
    raise NotImplementedError("Phase 4.4")


@router.post("/applications/{app_id}/compliance")
def recalculate_compliance(app_id: str):
    raise NotImplementedError("Phase 4.4")


@router.get("/applications/{app_id}/compliance/controls")
def get_compliance_controls(app_id: str):
    raise NotImplementedError("Phase 4.5")


@router.get("/curation/queue")
def get_curation_queue():
    """Requires governance.admin scope."""
    raise NotImplementedError("Phase 4.9")


@router.post("/curation/queue", status_code=201)
def submit_curation_item():
    """Requires governance.admin scope."""
    raise NotImplementedError("Phase 4.9")
