"""
POST   /applications              — register an AI application
GET    /applications              — list all applications
GET    /applications/{id}         — get application detail
PATCH  /applications/{id}         — update application metadata
GET    /applications/{id}/tier    — current risk tier (NIST scoring + domain floor)
GET    /applications/{id}/tier/history   — tier change log (immutable)
GET    /applications/{id}/alignment      — alignment score
GET    /applications/{id}/benchmarks     — peer benchmarks (same tier, N>=3)
GET    /applications/{id}/recommendations

Phase 4 implementation. Auth: Azure Entra ID Bearer token.
"""
from fastapi import APIRouter

router = APIRouter(tags=["applications"])


@router.post("/applications", status_code=201)
def register_application():
    raise NotImplementedError("Phase 4.1")


@router.get("/applications")
def list_applications():
    raise NotImplementedError("Phase 4.1")


@router.get("/applications/{app_id}")
def get_application(app_id: str):
    raise NotImplementedError("Phase 4.1")


@router.patch("/applications/{app_id}")
def update_application(app_id: str):
    raise NotImplementedError("Phase 4.1")


@router.get("/applications/{app_id}/tier")
def get_tier(app_id: str):
    raise NotImplementedError("Phase 4.3")


@router.get("/applications/{app_id}/tier/history")
def get_tier_history(app_id: str):
    raise NotImplementedError("Phase 4.3")


@router.get("/applications/{app_id}/alignment")
def get_alignment(app_id: str):
    raise NotImplementedError("Phase 4.6")


@router.get("/applications/{app_id}/benchmarks")
def get_benchmarks(app_id: str):
    raise NotImplementedError("Phase 4.7")


@router.get("/applications/{app_id}/recommendations")
def get_recommendations(app_id: str):
    raise NotImplementedError("Phase 4.7")
