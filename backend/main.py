from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.applications import router as applications_router
from api.catalog import router as catalog_router
from api.compliance import router as compliance_router
from api.telemetry import router as telemetry_router
from db.session import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize shared async engine once for API lifetime.
    get_engine()
    yield
    await get_engine().dispose()


app = FastAPI(
    title="AI Governance Platform API",
    version="0.1.0",
    description="Phase 1 — skeleton API for AI Governance Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(applications_router, prefix="/api/v1")
app.include_router(catalog_router,      prefix="/api/v1")
app.include_router(compliance_router,   prefix="/api/v1")
app.include_router(telemetry_router,    prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/info")
def info():
    return {
        "platform": "AI Governance Platform",
        "version": "0.1.0",
        "phase": 1,
        "llm_deployment": "aigov-gpt41",
        "llm_model": "gpt-4.1",
    }
