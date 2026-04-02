"""
POST   /telemetry/ingest    — ingest OTEL metrics from connected apps
GET    /telemetry/status    — ingest pipeline health

OTEL contract: 28 mandatory metrics across 8 groups (Section 10).
Only ingests metrics where deployment.environment == 'production'.
Connected apps must carry resource attributes:
  service.name, service.version, deployment.environment,
  governance.application_id, governance.division.

AI applications are instrumented, not aware.
They emit standard OTEL as a side effect of normal operation.

Phase 4 implementation.
"""
from fastapi import APIRouter, Request

router = APIRouter(tags=["telemetry"])


@router.post("/telemetry/ingest", status_code=202)
async def ingest(request: Request):
    raise NotImplementedError("Phase 4.2")


@router.get("/telemetry/status")
def telemetry_status():
    raise NotImplementedError("Phase 4.2")
