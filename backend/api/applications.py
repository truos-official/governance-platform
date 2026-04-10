"""
applications.py â€” Application registration and governance endpoints

Phase 4.1: CRUD (register, list, get, update)
Phase 4.3: Tier endpoints (current tier, tier history)
Phase 4.6: Alignment score          â€” NotImplementedError (next phase)
Phase 4.7: Benchmarks/recommendations â€” NotImplementedError (next phase)

Auth: Azure Entra ID Bearer token (enforced at middleware layer).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Application,
    TierChangeEvent,
    ControlAssignment,
    TierPeerAggregate,
    CalculatedMetric,
    Control,
    ControlRequirement,
    MetricReading,
    Requirement,
    Regulation,
    ApplicationRequirement,
    AppInterpretation,
    ControlMetricDefinition,
    MeasureFormula,
    ControlLifecycleTag,
)
from db.session import get_db_session as get_db
from core.alignment import calculate_alignment
from core.tier_engine import registration_trigger, TierResult
from core.kpi_calculator import KPICalculator, _evaluate_threshold

router = APIRouter(tags=["applications"])
calculator = KPICalculator()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ApplicationRegisterRequest(BaseModel):
    name:                 str
    description:          Optional[str]   = None
    division_id:          Optional[str]   = None
    domain:               str             = Field(..., description="healthcare | criminal_justice | financial | hr | education | internal_ops | asylum | biometric_id | other")
    ai_system_type:       str             = Field(..., description="GEN | RAG | AUTO | DECISION | OTHER")
    decision_type:        str             = Field(..., description="binding | advisory | informational")
    autonomy_level:       str             = Field(..., description="human_in_the_loop | human_on_loop | human_out_of_loop")
    population_breadth:   str             = Field(..., description="local | regional | national | global")
    affected_populations: str             = Field(..., description="general | vulnerable | mixed")
    consent_scope:        str             = Field("tier_aggregate", description="none | tier_aggregate | full")
    owner_email:          Optional[str]   = None


class ApplicationUpdateRequest(BaseModel):
    name:                 Optional[str]   = None
    description:          Optional[str]   = None
    owner_email:          Optional[str]   = None
    consent_scope:        Optional[str]   = None


class TierDimensionBreakdown(BaseModel):
    deployment_domain:    float
    decision_type:        float
    autonomy_level:       float
    population_breadth:   float
    affected_populations: float
    likelihood:           float


class TierResponse(BaseModel):
    application_id: str
    current_tier:   str
    raw_score:      float
    floor_rule:     Optional[str]
    dimensions:     TierDimensionBreakdown
    calculated_at:  datetime


class TierHistoryEntry(BaseModel):
    id:             str
    previous_tier:  Optional[str]
    new_tier:       str
    reason:         Optional[str]
    changed_at:     datetime


class ApplicationResponse(BaseModel):
    id:                   str
    name:                 str
    description:          Optional[str]
    division_id:          Optional[str]
    domain:               Optional[str]
    ai_system_type:       str
    decision_type:        str
    autonomy_level:       str
    population_breadth:   str
    affected_populations: str
    consent_scope:        str
    owner_email:          Optional[str]
    status:               str
    current_tier:         Optional[str]
    registered_at:        datetime


class RegisterApplicationResponse(BaseModel):
    application:          ApplicationResponse
    tier:                 TierResponse
    otel_config:          dict
    missing_metric_groups: list[str]


class ApplicationRequirementScopeItem(BaseModel):
    requirement_id: str
    code: str
    title: str
    regulation_title: Optional[str]
    jurisdiction: Optional[str]
    category: Optional[str]
    selected: bool
    is_default: bool = False
    linked_controls: list[dict[str, Any]] = Field(default_factory=list)


class ApplicationRequirementScopeResponse(BaseModel):
    application_id: str
    items: list[ApplicationRequirementScopeItem]
    total: int
    skip: int
    limit: int
    selected_count: int


class ApplicationRequirementScopeUpdateRequest(BaseModel):
    requirement_ids: list[str] = Field(default_factory=list)


class ApplicationRequirementScopeUpdateResponse(BaseModel):
    application_id: str
    selected_count: int
    updated_at: datetime


class StrictRequestModel(BaseModel):
    class Config:
        extra = "forbid"


class AppInterpretationCreateRequest(StrictRequestModel):
    requirement_id: str
    control_id: str
    interpretation_text: Optional[str] = None
    threshold_override: Optional[dict] = None
    set_by: str
    metric_name: Optional[str] = None
    threshold: Optional[dict] = None
    control_metric_definition_id: Optional[str] = None

    @field_validator("metric_name", "threshold", "control_metric_definition_id")
    @classmethod
    def reject_global_metric_mutation_fields(cls, v, info):
        if v is not None:
            raise ValueError(
                f"{info.field_name} is not allowed for app-scoped interpretation updates; "
                "metric definitions are immutable at app scope"
            )
        return v


class AppInterpretationPatchRequest(StrictRequestModel):
    interpretation_text: Optional[str] = None
    threshold_override: Optional[dict] = None
    set_by: Optional[str] = None
    metric_name: Optional[str] = None
    threshold: Optional[dict] = None
    control_metric_definition_id: Optional[str] = None

    @field_validator("metric_name", "threshold", "control_metric_definition_id")
    @classmethod
    def reject_global_metric_mutation_fields(cls, v, info):
        if v is not None:
            raise ValueError(
                f"{info.field_name} is not allowed for app-scoped interpretation updates; "
                "metric definitions are immutable at app scope"
            )
        return v


class AppInterpretationResponse(BaseModel):
    id: str
    application_id: str
    requirement_id: str
    requirement_code: Optional[str]
    requirement_title: Optional[str]
    control_id: str
    control_code: Optional[str]
    control_title: Optional[str]
    interpretation_text: Optional[str]
    threshold_override: Optional[dict]
    set_by: str
    set_at: datetime


class DashboardMeasureRow(BaseModel):
    control_id: str
    control_code: Optional[str]
    control_title: Optional[str]
    requirement_id: Optional[str]
    requirement_code: Optional[str]
    requirement_title: Optional[str]
    metric_name: str
    result: str
    value: Optional[float]
    threshold: Optional[dict]
    interpretation_text: str
    industry_benchmark: Optional[float]
    peer_benchmark: Optional[float]
    benchmark_result: Optional[str]
    peer_avg: Optional[float]
    peer_delta: Optional[float]
    peer_count: Optional[int]
    percentile_rank: Optional[float]
    p25: Optional[float]
    p75: Optional[float]
    adoption_count: Optional[int]
    adoption_rate: Optional[float]
    popularity_stars: Optional[str]
    tags: list[str] = Field(default_factory=list)
    regulatory_density: int = 0


class DashboardStepResponse(BaseModel):
    application_id: str
    step: int
    step_key: str
    generated_at: datetime
    scope_active: bool
    row_count: int
    summary: dict[str, Any]
    rows: list[DashboardMeasureRow]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

METRIC_GROUPS_BY_SYSTEM_TYPE: dict[str, list[str]] = {
    "RAG":      ["core", "rag", "security"],
    "GEN":      ["core", "security"],
    "AUTO":     ["core", "security", "risk", "incident"],
    "DECISION": ["core", "risk", "incident", "appeals"],
    "OTHER":    ["core"],
}

METRIC_GROUPS_BY_TIER: dict[str, list[str]] = {
    "High":       ["risk", "incident"],
    "Common":     ["risk", "incident"],
    "Foundation": [],
}


def _required_metric_groups(app: Application) -> list[str]:
    groups = set(METRIC_GROUPS_BY_SYSTEM_TYPE.get(app.ai_system_type, ["core"]))
    groups.update(METRIC_GROUPS_BY_TIER.get(app.current_tier or "Foundation", []))
    return sorted(groups)


def _otel_config(app: Application) -> dict:
    return {
        "service_name":                 app.id,
        "required_resource_attributes": {
            "service.name":                    app.id,
            "service.version":                 "<your-semver>",
            "deployment.environment":          "production",
            "governance.application_id":       app.id,
            "governance.division":             app.division_id or "unassigned",
        },
        "required_metric_groups": _required_metric_groups(app),
        "collector_endpoint":     "https://<governance-api-host>/telemetry/ingest",
    }


def _app_to_response(app: Application) -> ApplicationResponse:
    return ApplicationResponse(
        id=app.id,
        name=app.name,
        description=app.description,
        division_id=app.division_id,
        domain=app.domain,
        ai_system_type=app.ai_system_type,
        decision_type=app.decision_type,
        autonomy_level=app.autonomy_level,
        population_breadth=app.population_breadth,
        affected_populations=app.affected_populations,
        consent_scope=app.consent_scope,
        owner_email=app.owner_email,
        status=app.status,
        current_tier=app.current_tier,
        registered_at=app.registered_at,
    )


def _tier_result_to_response(app_id: str, result: TierResult) -> TierResponse:
    return TierResponse(
        application_id=app_id,
        current_tier=result.final_tier.value,
        raw_score=result.raw_score,
        floor_rule=result.floor_rule,
        dimensions=TierDimensionBreakdown(**result.dimensions),
        calculated_at=result.calculated_at,
    )


STEP_KEY_MAP: dict[int, str] = {
    1: "corporate_oversight",
    2: "risk_compliance",
    3: "technical_architecture",
    4: "data_readiness",
    5: "data_integration",
    6: "security",
    7: "infrastructure",
    8: "solution_design",
    9: "system_performance",
}

STEP_TAG_MAP: dict[int, set[str]] = {
    3: {"Technical Architecture"},
    4: {"Data Readiness"},
    5: {"Data Integration"},
    6: {"Security"},
    7: {"Infrastructure"},
    8: {"Solution Design"},
    9: {"System Performance"},
}

STEP2_BASELINE_KPI_PAIRS: list[tuple[str, str]] = [
    ("RM-2", "ai.core.error_rate"),
    ("RM-2", "ai.risk.error_to_limit_ratio"),
    ("RM-3", "ai.oversight.override_rate"),
    ("RM-3", "ai.risk.override_to_target_ratio"),
    ("RM-5", "ai.core.drift_score"),
    ("RM-5", "ai.risk.drift_to_limit_ratio"),
    ("RO-1", "ai.transparency.disclosure_rate"),
    ("RO-1", "ai.risk.disclosure_gap_pct"),
    ("RO-2", "ai.transparency.doc_completeness"),
    ("RO-2", "ai.risk.doc_completeness_gap_pct"),
]

STEP1_CORPORATE_FINOPS_KPIS: list[dict[str, Any]] = [
    {
        "control_id": "co-finops-compute-cost",
        "control_code": "CO-FN-1",
        "control_title": "Compute Cost Governance",
        "requirement_id": "co-req-finops-compute-cost",
        "requirement_code": "CO-REQ-FN-1",
        "requirement_title": (
            "Corporate oversight should track compute cost for AI operations to ensure spend "
            "stays within approved governance limits."
        ),
        "metric_name": "ai.resources.compute_cost",
        "threshold": {
            "operator": "lte",
            "value": 5000,
            "unit": " USD",
            "direction": "lower_better",
            "industry_benchmark": 3500,
            "source_system": "otel",
            "formula": "latest(compute_cost_usd)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects current AI compute spending against governance targets."
        ),
        "tags": ["Corporate Oversight"],
    },
    {
        "control_id": "co-finops-token-usage",
        "control_code": "CO-FN-2",
        "control_title": "Token Consumption Governance",
        "requirement_id": "co-req-finops-token-usage",
        "requirement_code": "CO-REQ-FN-2",
        "requirement_title": (
            "Corporate oversight should monitor model token consumption to manage cost "
            "exposure and operational efficiency."
        ),
        "metric_name": "ai.resources.token_usage",
        "threshold": {
            "operator": "lte",
            "value": 2000000,
            "unit": " tokens",
            "direction": "lower_better",
            "industry_benchmark": 1500000,
            "source_system": "otel",
            "formula": "latest(total_tokens)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates current model token utilization under governance oversight."
        ),
        "tags": ["Corporate Oversight"],
    },
    {
        "control_id": "co-finops-active-users",
        "control_code": "CO-FN-3",
        "control_title": "Active User Load Governance",
        "requirement_id": "co-req-finops-active-users",
        "requirement_code": "CO-REQ-FN-3",
        "requirement_title": (
            "Corporate oversight should track active-user load to ensure AI service scale "
            "stays within approved operating assumptions."
        ),
        "metric_name": "ai.resources.active_users",
        "threshold": {
            "operator": "gte",
            "value": 5,
            "unit": " users",
            "direction": "higher_better",
            "industry_benchmark": 25,
            "source_system": "otel",
            "formula": "latest(active_users)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects current active-user telemetry observed for governance load oversight."
        ),
        "tags": ["Corporate Oversight"],
    },
    {
        "control_id": "co-finops-cost-per-token",
        "control_code": "CO-FN-4",
        "control_title": "Data Cost Per Token Efficiency",
        "requirement_id": "co-req-finops-cost-per-token",
        "requirement_code": "CO-REQ-FN-4",
        "requirement_title": (
            "Corporate oversight should track cost efficiency per token to ensure data and "
            "model usage remains financially sustainable."
        ),
        "metric_name": "ai.resources.cost_per_token",
        "threshold": {
            "operator": "lte",
            "value": 0.005,
            "unit": " USD/token",
            "direction": "lower_better",
            "industry_benchmark": 0.003,
            "source_system": "otel",
            "formula": "(ai.resources.compute_cost / ai.resources.token_usage)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects the average cost efficiency of model token consumption."
        ),
        "tags": ["Corporate Oversight"],
    },
    {
        "control_id": "co-frontier-model-footprint",
        "control_code": "CO-FN-5",
        "control_title": "Frontier Model Footprint",
        "requirement_id": "co-req-frontier-model-footprint",
        "requirement_code": "CO-REQ-FN-5",
        "requirement_title": (
            "Corporate oversight should track how many frontier AI models are in active use "
            "to manage concentration and governance exposure."
        ),
        "metric_name": "ai.resources.frontier_model_count",
        "threshold": {
            "operator": "lte",
            "value": 2,
            "unit": " models",
            "direction": "lower_better",
            "industry_benchmark": 1,
            "source_system": "otel",
            "formula": "count(distinct frontier_model_names)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates how many frontier models are currently active in the solution."
        ),
        "tags": ["Corporate Oversight"],
    },
]

STEP3_TECHNICAL_ARCHITECTURE_KPIS: list[dict[str, Any]] = [
    {
        "control_id": "ta-rag-citation-coverage",
        "control_code": "TA-1",
        "control_title": "Evidence-Linked Response Architecture",
        "requirement_id": "ta-req-citation-coverage",
        "requirement_code": "TA-REQ-1",
        "requirement_title": (
            "RAG responses should include citations for grounded claims so the retrieval "
            "architecture can be audited and verified."
        ),
        "metric_name": "ai.rag.citation_coverage",
        "threshold": {
            "operator": "gte",
            "value": 0.85,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 0.82,
            "source_system": "otel",
            "formula": "(cited_claims / total_claims)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects how consistently the retrieval architecture returns cited "
            "evidence with each answer."
        ),
        "tags": ["Technical Architecture"],
    },
    {
        "control_id": "ta-model-quality-accuracy",
        "control_code": "TA-3",
        "control_title": "Model Quality Reliability",
        "requirement_id": "ta-req-model-accuracy",
        "requirement_code": "TA-REQ-3",
        "requirement_title": (
            "The selected model stack should sustain validated output quality in "
            "production conditions."
        ),
        "metric_name": "ai.model.accuracy",
        "threshold": {
            "operator": "gte",
            "value": 90,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 92,
            "source_system": "otel",
            "formula": "(successful_model_outputs / evaluated_outputs)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates whether the current model architecture is meeting expected quality."
        ),
        "tags": ["Technical Architecture"],
    },
    {
        "control_id": "ta-model-hallucination-control",
        "control_code": "TA-4",
        "control_title": "Grounding Fidelity",
        "requirement_id": "ta-req-hallucination-control",
        "requirement_code": "TA-REQ-4",
        "requirement_title": (
            "Architecture should minimize ungrounded generation through grounding and "
            "retrieval controls."
        ),
        "metric_name": "ai.model.hallucination_rate",
        "threshold": {
            "operator": "lte",
            "value": 20,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 15,
            "source_system": "otel",
            "formula": "(hallucinated_outputs / total_outputs)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects how effectively the architecture prevents ungrounded answers."
        ),
        "tags": ["Technical Architecture"],
    },
    {
        "control_id": "ta-serving-error-budget",
        "control_code": "TA-5",
        "control_title": "Serving Error Budget",
        "requirement_id": "ta-req-serving-error-budget",
        "requirement_code": "TA-REQ-5",
        "requirement_title": (
            "The inference architecture should operate within an acceptable error budget "
            "for production requests."
        ),
        "metric_name": "ai.core.error_rate",
        "threshold": {
            "operator": "lte",
            "value": 0.05,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.04,
            "source_system": "otel",
            "formula": "(failed_requests / total_requests)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects reliability of the deployed model-serving architecture."
        ),
        "tags": ["Technical Architecture"],
    },
    {
        "control_id": "ta-drift-resilience",
        "control_code": "TA-6",
        "control_title": "Architecture Drift Resilience",
        "requirement_id": "ta-req-drift-resilience",
        "requirement_code": "TA-REQ-6",
        "requirement_title": (
            "Architecture should detect and absorb drift before quality degradation "
            "impacts end users."
        ),
        "metric_name": "ai.core.drift_score",
        "threshold": {
            "operator": "lte",
            "value": 0.2,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.18,
            "source_system": "otel",
            "formula": "drift_score(current_distribution, baseline_distribution)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates whether architecture-level drift controls are working."
        ),
        "tags": ["Technical Architecture"],
    },
    {
        "control_id": "ta-doc-governance-readiness",
        "control_code": "TA-7",
        "control_title": "Architecture Documentation Readiness",
        "requirement_id": "ta-req-doc-governance-readiness",
        "requirement_code": "TA-REQ-7",
        "requirement_title": (
            "The technical architecture should maintain complete and current design "
            "documentation for governance traceability."
        ),
        "metric_name": "ai.transparency.doc_completeness",
        "threshold": {
            "operator": "gte",
            "value": 85,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 82,
            "source_system": "otel",
            "formula": "(completed_doc_sections / required_doc_sections)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This shows whether architecture documentation is sufficiently complete."
        ),
        "tags": ["Technical Architecture"],
    },
    {
        "control_id": "ta-rag-retrieval-latency",
        "control_code": "TA-2",
        "control_title": "Retrieval Path Performance",
        "requirement_id": "ta-req-retrieval-latency",
        "requirement_code": "TA-REQ-2",
        "requirement_title": (
            "The retrieval layer should return supporting context within the latency "
            "budget required for production use."
        ),
        "metric_name": "ai.rag.retrieval_latency_p95",
        "threshold": {
            "operator": "lte",
            "value": 500,
            "unit": "ms",
            "direction": "lower_better",
            "industry_benchmark": 450,
            "source_system": "otel",
            "formula": "p95(retrieval_latency_ms)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects whether retrieval remains fast enough for the current "
            "RAG architecture."
        ),
        "tags": ["Technical Architecture"],
    },
]

STEP4_DATA_READINESS_KPIS: list[dict[str, Any]] = [
    {
        "control_id": "dr-data-quality-integrity",
        "control_code": "DR-1",
        "control_title": "Training and Input Data Quality",
        "requirement_id": "dr-req-data-quality-integrity",
        "requirement_code": "DR-REQ-1",
        "requirement_title": (
            "Data used in AI workflows should meet quality standards for completeness, "
            "consistency, and reliability."
        ),
        "metric_name": "ai.data.quality_score",
        "threshold": {
            "operator": "gte",
            "value": 0.85,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 0.82,
            "source_system": "otel",
            "formula": "data_quality_score(completeness, validity, consistency)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates overall readiness of data feeding the AI system."
        ),
        "tags": ["Data Readiness"],
    },
    {
        "control_id": "dr-bias-monitoring",
        "control_code": "DR-2",
        "control_title": "Data Bias Monitoring",
        "requirement_id": "dr-req-bias-monitoring",
        "requirement_code": "DR-REQ-2",
        "requirement_title": (
            "Input and evaluation datasets should be monitored for bias indicators "
            "that could affect fairness outcomes."
        ),
        "metric_name": "ai.data.bias_score",
        "threshold": {
            "operator": "lte",
            "value": 0.10,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.08,
            "source_system": "otel",
            "formula": "bias_score(group_disparity_metrics)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects whether data bias remains within acceptable limits."
        ),
        "tags": ["Data Readiness"],
    },
    {
        "control_id": "dr-distribution-stability",
        "control_code": "DR-3",
        "control_title": "Data Distribution Stability",
        "requirement_id": "dr-req-distribution-stability",
        "requirement_code": "DR-REQ-3",
        "requirement_title": (
            "Data distributions should remain stable or trigger review when material "
            "shift is detected."
        ),
        "metric_name": "ai.core.drift_score",
        "threshold": {
            "operator": "lte",
            "value": 0.20,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.18,
            "source_system": "otel",
            "formula": "drift_score(current_distribution, baseline_distribution)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This measures shift in data or behavior relative to the approved baseline."
        ),
        "tags": ["Data Readiness"],
    },
    {
        "control_id": "dr-data-documentation",
        "control_code": "DR-4",
        "control_title": "Data and Model Documentation Coverage",
        "requirement_id": "dr-req-data-documentation",
        "requirement_code": "DR-REQ-4",
        "requirement_title": (
            "Required data and model documentation should be complete and current "
            "before operational use."
        ),
        "metric_name": "ai.transparency.doc_completeness",
        "threshold": {
            "operator": "gte",
            "value": 85,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 80,
            "source_system": "otel",
            "formula": "(completed_doc_sections / required_doc_sections)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This shows readiness of required governance documentation."
        ),
        "tags": ["Data Readiness"],
    },
    {
        "control_id": "dr-disclosure-readiness",
        "control_code": "DR-5",
        "control_title": "Operational Disclosure Readiness",
        "requirement_id": "dr-req-disclosure-readiness",
        "requirement_code": "DR-REQ-5",
        "requirement_title": (
            "User-facing transparency disclosures should be prepared and consistently "
            "available before broad deployment."
        ),
        "metric_name": "ai.transparency.disclosure_rate",
        "threshold": {
            "operator": "gte",
            "value": 90,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 85,
            "source_system": "otel",
            "formula": "(disclosed_interactions / total_interactions)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates how ready the system is to meet transparency expectations."
        ),
        "tags": ["Data Readiness"],
    },
]

STEP5_DATA_INTEGRATION_KPIS: list[dict[str, Any]] = [
    {
        "control_id": "di-ingestion-quality",
        "control_code": "DI-1",
        "control_title": "Ingestion Data Quality Assurance",
        "requirement_id": "di-req-ingestion-quality",
        "requirement_code": "DI-REQ-1",
        "requirement_title": (
            "Data flowing through integration pipelines should preserve quality before "
            "it reaches model-serving components."
        ),
        "metric_name": "ai.data.quality_score",
        "threshold": {
            "operator": "gte",
            "value": 0.85,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 0.82,
            "source_system": "otel",
            "formula": "data_quality_score(completeness, validity, consistency)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects whether integrated data streams are arriving in usable condition."
        ),
        "tags": ["Data Integration"],
    },
    {
        "control_id": "di-pipeline-error-budget",
        "control_code": "DI-2",
        "control_title": "Pipeline Reliability Error Budget",
        "requirement_id": "di-req-pipeline-error-budget",
        "requirement_code": "DI-REQ-2",
        "requirement_title": (
            "Integrated services should maintain low failure rates across retrieval, "
            "model, and orchestration pathways."
        ),
        "metric_name": "ai.core.error_rate",
        "threshold": {
            "operator": "lte",
            "value": 0.05,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.04,
            "source_system": "otel",
            "formula": "(failed_requests / total_requests)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates how reliably integrated components are executing end-to-end."
        ),
        "tags": ["Data Integration"],
    },
    {
        "control_id": "di-data-flow-stability",
        "control_code": "DI-3",
        "control_title": "Integrated Data Flow Stability",
        "requirement_id": "di-req-data-flow-stability",
        "requirement_code": "DI-REQ-3",
        "requirement_title": (
            "Integration pipelines should detect and respond to distribution shifts in "
            "incoming or transformed data."
        ),
        "metric_name": "ai.core.drift_score",
        "threshold": {
            "operator": "lte",
            "value": 0.20,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.18,
            "source_system": "otel",
            "formula": "drift_score(current_distribution, baseline_distribution)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This shows whether integrated data flows remain stable over time."
        ),
        "tags": ["Data Integration"],
    },
    {
        "control_id": "di-transparency-propagation",
        "control_code": "DI-4",
        "control_title": "Transparency Signal Propagation",
        "requirement_id": "di-req-transparency-propagation",
        "requirement_code": "DI-REQ-4",
        "requirement_title": (
            "Transparency metadata should be preserved across integrated systems so "
            "user-facing disclosures remain consistent."
        ),
        "metric_name": "ai.transparency.disclosure_rate",
        "threshold": {
            "operator": "gte",
            "value": 90,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 85,
            "source_system": "otel",
            "formula": "(disclosed_interactions / total_interactions)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates whether integrated channels are preserving required disclosures."
        ),
        "tags": ["Data Integration"],
    },
    {
        "control_id": "di-lineage-documentation",
        "control_code": "DI-5",
        "control_title": "Data Lineage Documentation Completeness",
        "requirement_id": "di-req-lineage-documentation",
        "requirement_code": "DI-REQ-5",
        "requirement_title": (
            "Integration architecture should maintain complete lineage and interface "
            "documentation for governance traceability."
        ),
        "metric_name": "ai.transparency.doc_completeness",
        "threshold": {
            "operator": "gte",
            "value": 85,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 80,
            "source_system": "otel",
            "formula": "(completed_doc_sections / required_doc_sections)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects whether integration lineage evidence is governance-ready."
        ),
        "tags": ["Data Integration"],
    },
]

STEP6_SECURITY_KPIS: list[dict[str, Any]] = [
    {
        "control_id": "se-secure-service-reliability",
        "control_code": "SE-1",
        "control_title": "Secure Service Reliability",
        "requirement_id": "se-req-secure-service-reliability",
        "requirement_code": "SE-REQ-1",
        "requirement_title": (
            "Security controls should maintain stable service operation and prevent "
            "error spikes associated with insecure requests."
        ),
        "metric_name": "ai.core.error_rate",
        "threshold": {
            "operator": "lte",
            "value": 0.04,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.03,
            "source_system": "otel",
            "formula": "(failed_requests / total_requests)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates whether secure service pathways are operating reliably."
        ),
        "tags": ["Security"],
    },
    {
        "control_id": "se-human-override-security",
        "control_code": "SE-2",
        "control_title": "Human Security Intervention Rate",
        "requirement_id": "se-req-human-override-security",
        "requirement_code": "SE-REQ-2",
        "requirement_title": (
            "Security-relevant model outputs should be reviewable, with human override "
            "available when automated safeguards are insufficient."
        ),
        "metric_name": "ai.oversight.override_rate",
        "threshold": {
            "operator": "gte",
            "value": 0.05,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 0.04,
            "source_system": "otel",
            "formula": "(overridden_outputs / total_outputs)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects whether security-sensitive outputs receive active human checks."
        ),
        "tags": ["Security"],
    },
    {
        "control_id": "se-unsafe-output-suppression",
        "control_code": "SE-3",
        "control_title": "Unsafe Output Suppression",
        "requirement_id": "se-req-unsafe-output-suppression",
        "requirement_code": "SE-REQ-3",
        "requirement_title": (
            "Security posture should suppress ungrounded or unsafe outputs that could "
            "expose users to harmful content."
        ),
        "metric_name": "ai.model.hallucination_rate",
        "threshold": {
            "operator": "lte",
            "value": 0.15,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.12,
            "source_system": "otel",
            "formula": "(hallucinated_outputs / total_outputs)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This shows how effectively security guardrails limit unsafe generated content."
        ),
        "tags": ["Security"],
    },
    {
        "control_id": "se-incident-disclosure-readiness",
        "control_code": "SE-4",
        "control_title": "Incident Disclosure Readiness",
        "requirement_id": "se-req-incident-disclosure-readiness",
        "requirement_code": "SE-REQ-4",
        "requirement_title": (
            "Security incidents and safeguards should be consistently disclosed where "
            "policy requires user-facing transparency."
        ),
        "metric_name": "ai.transparency.disclosure_rate",
        "threshold": {
            "operator": "gte",
            "value": 90,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 85,
            "source_system": "otel",
            "formula": "(disclosed_interactions / total_interactions)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates security disclosure consistency across user interactions."
        ),
        "tags": ["Security"],
    },
    {
        "control_id": "se-security-doc-readiness",
        "control_code": "SE-5",
        "control_title": "Security Documentation Completeness",
        "requirement_id": "se-req-security-doc-readiness",
        "requirement_code": "SE-REQ-5",
        "requirement_title": (
            "Security architecture, control evidence, and response procedures should be "
            "fully documented and audit-ready."
        ),
        "metric_name": "ai.transparency.doc_completeness",
        "threshold": {
            "operator": "gte",
            "value": 85,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 80,
            "source_system": "otel",
            "formula": "(completed_doc_sections / required_doc_sections)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects readiness of security evidence and documentation controls."
        ),
        "tags": ["Security"],
    },
]

STEP7_INFRASTRUCTURE_KPIS: list[dict[str, Any]] = [
    {
        "control_id": "in-runtime-reliability-budget",
        "control_code": "IN-1",
        "control_title": "Runtime Reliability Budget",
        "requirement_id": "in-req-runtime-reliability-budget",
        "requirement_code": "IN-REQ-1",
        "requirement_title": (
            "Infrastructure should maintain stable runtime reliability so AI requests are "
            "served consistently under normal operational load."
        ),
        "metric_name": "ai.core.error_rate",
        "threshold": {
            "operator": "lte",
            "value": 0.04,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.03,
            "source_system": "otel",
            "formula": "(failed_requests / total_requests)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects runtime stability of the deployed infrastructure."
        ),
        "tags": ["Infrastructure"],
    },
    {
        "control_id": "in-runtime-drift-monitoring",
        "control_code": "IN-2",
        "control_title": "Runtime Drift Monitoring",
        "requirement_id": "in-req-runtime-drift-monitoring",
        "requirement_code": "IN-REQ-2",
        "requirement_title": (
            "Infrastructure observability should detect drift in live model behavior before "
            "service quality degrades."
        ),
        "metric_name": "ai.core.drift_score",
        "threshold": {
            "operator": "lte",
            "value": 0.15,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.12,
            "source_system": "otel",
            "formula": "drift_score(current_distribution, baseline_distribution)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates whether infrastructure monitoring is catching runtime drift."
        ),
        "tags": ["Infrastructure"],
    },
    {
        "control_id": "in-serving-quality-slo",
        "control_code": "IN-3",
        "control_title": "Serving Quality SLO",
        "requirement_id": "in-req-serving-quality-slo",
        "requirement_code": "IN-REQ-3",
        "requirement_title": (
            "Serving infrastructure should meet production quality service levels across "
            "deployed requests."
        ),
        "metric_name": "ai.model.accuracy",
        "threshold": {
            "operator": "gte",
            "value": 90,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 92,
            "source_system": "otel",
            "formula": "(successful_model_outputs / evaluated_outputs)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This shows whether infrastructure-backed serving quality is within target."
        ),
        "tags": ["Infrastructure"],
    },
    {
        "control_id": "in-operational-disclosure-readiness",
        "control_code": "IN-4",
        "control_title": "Operational Disclosure Readiness",
        "requirement_id": "in-req-operational-disclosure-readiness",
        "requirement_code": "IN-REQ-4",
        "requirement_title": (
            "Operational infrastructure events should support consistent user-facing "
            "disclosure practices where required."
        ),
        "metric_name": "ai.transparency.disclosure_rate",
        "threshold": {
            "operator": "gte",
            "value": 90,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 86,
            "source_system": "otel",
            "formula": "(disclosed_interactions / total_interactions)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects disclosure consistency supported by operational infrastructure."
        ),
        "tags": ["Infrastructure"],
    },
    {
        "control_id": "in-runbook-documentation-completeness",
        "control_code": "IN-5",
        "control_title": "Runbook and Control Documentation Completeness",
        "requirement_id": "in-req-runbook-documentation-completeness",
        "requirement_code": "IN-REQ-5",
        "requirement_title": (
            "Infrastructure runbooks and operational control documentation should remain "
            "complete and audit-ready."
        ),
        "metric_name": "ai.transparency.doc_completeness",
        "threshold": {
            "operator": "gte",
            "value": 85,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 80,
            "source_system": "otel",
            "formula": "(completed_doc_sections / required_doc_sections)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This shows whether infrastructure evidence remains documentation-complete."
        ),
        "tags": ["Infrastructure"],
    },
]

STEP8_SOLUTION_DESIGN_KPIS: list[dict[str, Any]] = [
    {
        "control_id": "sd-human-oversight-effectiveness",
        "control_code": "SD-1",
        "control_title": "Human Oversight Effectiveness",
        "requirement_id": "sd-req-human-oversight-effectiveness",
        "requirement_code": "SD-REQ-1",
        "requirement_title": (
            "Solution design should keep meaningful human oversight available for "
            "high-impact outputs and decisions."
        ),
        "metric_name": "ai.oversight.override_rate",
        "threshold": {
            "operator": "gte",
            "value": 0.05,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 0.04,
            "source_system": "otel",
            "formula": "(overridden_outputs / total_outputs)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates whether the solution design supports active human intervention."
        ),
        "tags": ["Solution Design"],
    },
    {
        "control_id": "sd-fairness-bias-control",
        "control_code": "SD-2",
        "control_title": "Fairness and Bias Control",
        "requirement_id": "sd-req-fairness-bias-control",
        "requirement_code": "SD-REQ-2",
        "requirement_title": (
            "Solution design should limit bias exposure and maintain fairness across "
            "affected user groups."
        ),
        "metric_name": "ai.data.bias_score",
        "threshold": {
            "operator": "lte",
            "value": 0.10,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.08,
            "source_system": "otel",
            "formula": "bias_score(protected_group_outcomes, baseline_outcomes)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects fairness performance of the current solution design."
        ),
        "tags": ["Solution Design"],
    },
    {
        "control_id": "sd-output-reliability-quality",
        "control_code": "SD-3",
        "control_title": "Output Reliability Quality",
        "requirement_id": "sd-req-output-reliability-quality",
        "requirement_code": "SD-REQ-3",
        "requirement_title": (
            "The designed solution should sustain reliable output quality for user-facing "
            "workflows."
        ),
        "metric_name": "ai.model.accuracy",
        "threshold": {
            "operator": "gte",
            "value": 90,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 92,
            "source_system": "otel",
            "formula": "(successful_model_outputs / evaluated_outputs)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This shows whether solution-design quality targets are being met."
        ),
        "tags": ["Solution Design"],
    },
    {
        "control_id": "sd-hallucination-suppression",
        "control_code": "SD-4",
        "control_title": "Hallucination Suppression",
        "requirement_id": "sd-req-hallucination-suppression",
        "requirement_code": "SD-REQ-4",
        "requirement_title": (
            "Solution design should reduce ungrounded outputs through guardrails and "
            "validation mechanisms."
        ),
        "metric_name": "ai.model.hallucination_rate",
        "threshold": {
            "operator": "lte",
            "value": 0.15,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.12,
            "source_system": "otel",
            "formula": "(hallucinated_outputs / total_outputs)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates how effectively design guardrails suppress ungrounded outputs."
        ),
        "tags": ["Solution Design"],
    },
    {
        "control_id": "sd-user-transparency-disclosure",
        "control_code": "SD-5",
        "control_title": "User Transparency Disclosure",
        "requirement_id": "sd-req-user-transparency-disclosure",
        "requirement_code": "SD-REQ-5",
        "requirement_title": (
            "The solution should clearly disclose AI involvement to users in contexts where "
            "transparency is required."
        ),
        "metric_name": "ai.transparency.disclosure_rate",
        "threshold": {
            "operator": "gte",
            "value": 90,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 86,
            "source_system": "otel",
            "formula": "(disclosed_interactions / total_interactions)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects whether user-facing transparency is built into the solution."
        ),
        "tags": ["Solution Design"],
    },
    {
        "control_id": "sd-human-feedback-alignment",
        "control_code": "SD-6",
        "control_title": "Human Feedback Alignment Rate",
        "requirement_id": "sd-req-human-feedback-alignment",
        "requirement_code": "SD-REQ-6",
        "requirement_title": (
            "Solution design should capture thumbs-up/down user feedback and monitor "
            "positive feedback trends as a human-in-the-loop quality signal."
        ),
        "metric_name": "ai.oversight.feedback_positive_rate",
        "threshold": {
            "operator": "gte",
            "value": 0.70,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 0.72,
            "source_system": "your_feedback",
            "formula": "(thumbs_up_feedback / total_feedback_events)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates how strongly human reviewers affirm response usefulness and quality."
        ),
        "tags": ["Solution Design"],
    }
]

STEP9_SYSTEM_PERFORMANCE_KPIS: list[dict[str, Any]] = [
    {
        "control_id": "sp-production-error-budget",
        "control_code": "SP-1",
        "control_title": "Production Error Budget",
        "requirement_id": "sp-req-production-error-budget",
        "requirement_code": "SP-REQ-1",
        "requirement_title": (
            "System operations should keep production error rates within the approved "
            "service reliability budget."
        ),
        "metric_name": "ai.core.error_rate",
        "threshold": {
            "operator": "lte",
            "value": 0.04,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.03,
            "source_system": "otel",
            "formula": "(failed_requests / total_requests)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates current production reliability for live AI operations."
        ),
        "tags": ["System Performance"],
    },
    {
        "control_id": "sp-behavior-stability-drift",
        "control_code": "SP-2",
        "control_title": "Behavior Stability Under Drift",
        "requirement_id": "sp-req-behavior-stability-drift",
        "requirement_code": "SP-REQ-2",
        "requirement_title": (
            "System performance should remain stable under changing data conditions, with "
            "drift detected before user impact grows."
        ),
        "metric_name": "ai.core.drift_score",
        "threshold": {
            "operator": "lte",
            "value": 0.15,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.12,
            "source_system": "otel",
            "formula": "drift_score(current_distribution, baseline_distribution)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects runtime behavior stability over time."
        ),
        "tags": ["System Performance"],
    },
    {
        "control_id": "sp-output-quality-consistency",
        "control_code": "SP-3",
        "control_title": "Output Quality Consistency",
        "requirement_id": "sp-req-output-quality-consistency",
        "requirement_code": "SP-REQ-3",
        "requirement_title": (
            "The system should sustain consistent output quality during ongoing operations "
            "and changing workload."
        ),
        "metric_name": "ai.model.accuracy",
        "threshold": {
            "operator": "gte",
            "value": 90,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 92,
            "source_system": "otel",
            "formula": "(successful_model_outputs / evaluated_outputs)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This shows whether model output quality remains stable in production."
        ),
        "tags": ["System Performance"],
    },
    {
        "control_id": "sp-grounding-failure-rate",
        "control_code": "SP-4",
        "control_title": "Grounding Failure Rate",
        "requirement_id": "sp-req-grounding-failure-rate",
        "requirement_code": "SP-REQ-4",
        "requirement_title": (
            "Operational performance should minimize ungrounded responses that reduce "
            "trust and usefulness of system outputs."
        ),
        "metric_name": "ai.model.hallucination_rate",
        "threshold": {
            "operator": "lte",
            "value": 0.20,
            "unit": "%",
            "direction": "lower_better",
            "industry_benchmark": 0.15,
            "source_system": "otel",
            "formula": "(hallucinated_outputs / total_outputs)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This indicates how often output-grounding failures occur in production."
        ),
        "tags": ["System Performance"],
    },
    {
        "control_id": "sp-observability-evidence-readiness",
        "control_code": "SP-5",
        "control_title": "Observability Evidence Readiness",
        "requirement_id": "sp-req-observability-evidence-readiness",
        "requirement_code": "SP-REQ-5",
        "requirement_title": (
            "System performance operations should maintain complete documentation evidence "
            "for monitoring and audit response."
        ),
        "metric_name": "ai.transparency.doc_completeness",
        "threshold": {
            "operator": "gte",
            "value": 85,
            "unit": "%",
            "direction": "higher_better",
            "industry_benchmark": 80,
            "source_system": "otel",
            "formula": "(completed_doc_sections / required_doc_sections)",
        },
        "interpretation_template": (
            "Your {metric_name} is {value}{unit}, which is {threshold_verdict}. "
            "This reflects whether performance monitoring evidence is documentation-ready."
        ),
        "tags": ["System Performance"],
    },
]

ALLOWED_THRESHOLD_OPERATORS = {"lte", "gte", "lt", "gt", "eq", "between"}


def _to_popularity_stars(adoption_rate: Optional[float]) -> Optional[str]:
    if adoption_rate is None:
        return None
    if adoption_rate >= 0.80:
        return "â˜…â˜…â˜…â˜…â˜…"
    if adoption_rate >= 0.60:
        return "â˜…â˜…â˜…â˜…â˜†"
    if adoption_rate >= 0.40:
        return "â˜…â˜…â˜…â˜†â˜†"
    if adoption_rate >= 0.20:
        return "â˜…â˜…â˜†â˜†â˜†"
    return "â˜…â˜†â˜†â˜†â˜†"


def _result_priority(result: str) -> int:
    if result == "FAIL":
        return 0
    if result == "INSUFFICIENT_DATA":
        return 1
    return 2


def _extract_industry_benchmark(threshold: Optional[dict]) -> Optional[float]:
    if not isinstance(threshold, dict):
        return None
    raw = threshold.get("industry_benchmark")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _benchmark_is_higher_better(threshold: Optional[dict]) -> bool:
    if isinstance(threshold, dict):
        direction = str(threshold.get("direction", "") or "").strip().lower()
        if direction == "higher_better":
            return True
        if direction == "lower_better":
            return False
    return False


def _passes_benchmark(value: float, benchmark: float, higher_better: bool) -> bool:
    return value >= benchmark if higher_better else value <= benchmark


def _evaluate_benchmark_result(
    *,
    value: Optional[float],
    threshold: Optional[dict],
    industry_benchmark: Optional[float],
    peer_benchmark: Optional[float],
) -> Optional[str]:
    if value is None:
        return "INSUFFICIENT_DATA"
    checks: list[bool] = []
    higher_better = _benchmark_is_higher_better(threshold)
    if industry_benchmark is not None:
        checks.append(_passes_benchmark(value, industry_benchmark, higher_better))
    if peer_benchmark is not None:
        checks.append(_passes_benchmark(value, peer_benchmark, higher_better))
    if not checks:
        return None
    return "PASS" if all(checks) else "FAIL"


async def _compute_step2_live_metric(
    *,
    app_id: str,
    metric_name: str,
    threshold: Optional[dict],
    db: AsyncSession,
) -> tuple[Optional[float], str]:
    threshold_obj = threshold if isinstance(threshold, dict) else {}
    value = await calculator._latest_metric_value(app_id, metric_name, threshold_obj, db)
    if value is None:
        value = await calculator._evaluate_derived_formula(app_id, threshold_obj, db)
    # Demo fallback: use latest available historical reading/formula when no fresh telemetry exists yet.
    if value is None:
        value = await calculator._latest_metric_value(
            app_id, metric_name, threshold_obj, db, allow_stale=True
        )
    if value is None:
        value = await calculator._evaluate_derived_formula(
            app_id, threshold_obj, db, allow_stale=True
        )
    if value is None:
        return None, "INSUFFICIENT_DATA"
    return value, _evaluate_threshold(value, threshold_obj)


async def _build_curated_dashboard_rows(
    *,
    app_id: str,
    tier: Optional[str],
    configs: list[dict[str, Any]],
    db: AsyncSession,
) -> list[DashboardMeasureRow]:
    benchmark_rows = await db.execute(
        select(TierPeerAggregate.metric_name, TierPeerAggregate.avg_value, TierPeerAggregate.peer_count)
        .where(TierPeerAggregate.tier == tier)
    )
    peer_map = {
        row.metric_name: {"avg": row.avg_value, "count": row.peer_count}
        for row in benchmark_rows.all()
    }

    rows: list[DashboardMeasureRow] = []
    for config in configs:
        threshold = dict(config.get("threshold") or {})
        metric_name = config["metric_name"]
        value, result = await _compute_step2_live_metric(
            app_id=app_id,
            metric_name=metric_name,
            threshold=threshold,
            db=db,
        )
        peer = peer_map.get(metric_name, {})
        peer_avg = peer.get("avg")
        peer_count = peer.get("count")
        industry_benchmark = _extract_industry_benchmark(threshold)
        benchmark_result = _evaluate_benchmark_result(
            value=value,
            threshold=threshold,
            industry_benchmark=industry_benchmark,
            peer_benchmark=peer_avg,
        )
        peer_delta = None
        if peer_avg is not None and value is not None:
            peer_delta = round(float(value) - float(peer_avg), 6)

        rows.append(
            DashboardMeasureRow(
                control_id=config["control_id"],
                control_code=config.get("control_code"),
                control_title=config.get("control_title"),
                requirement_id=config.get("requirement_id"),
                requirement_code=config.get("requirement_code"),
                requirement_title=config.get("requirement_title"),
                metric_name=metric_name,
                result=result,
                value=value,
                threshold=threshold,
                interpretation_text=_render_measure_interpretation(
                    result=result,
                    metric_name=metric_name,
                    value=value,
                    threshold=threshold,
                    custom_text=None,
                    template_text=config.get("interpretation_template"),
                    generated_text=None,
                ),
                industry_benchmark=industry_benchmark,
                peer_benchmark=peer_avg,
                benchmark_result=benchmark_result,
                peer_avg=peer_avg,
                peer_delta=peer_delta,
                peer_count=peer_count,
                percentile_rank=None,
                p25=None,
                p75=None,
                adoption_count=None,
                adoption_rate=None,
                popularity_stars=None,
                tags=list(config.get("tags") or []),
                regulatory_density=int(config.get("regulatory_density") or 1),
            )
        )

    rows.sort(key=lambda row: (_result_priority(row.result), -row.regulatory_density, row.control_code or ""))
    return rows


def _validate_threshold_override(threshold_override: Optional[dict]) -> None:
    if threshold_override is None:
        return
    if not isinstance(threshold_override, dict):
        raise HTTPException(status_code=422, detail="threshold_override must be an object")
    operator = threshold_override.get("operator")
    if operator not in ALLOWED_THRESHOLD_OPERATORS:
        raise HTTPException(
            status_code=422,
            detail=f"threshold_override.operator must be one of {sorted(ALLOWED_THRESHOLD_OPERATORS)}",
        )
    if operator == "between":
        if "min_value" not in threshold_override or "max_value" not in threshold_override:
            raise HTTPException(
                status_code=422,
                detail="threshold_override for operator=between must include min_value and max_value",
            )
        try:
            float(threshold_override["min_value"])
            float(threshold_override["max_value"])
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422,
                detail="threshold_override min_value/max_value must be numeric",
            )
        return
    if "value" not in threshold_override:
        raise HTTPException(status_code=422, detail="threshold_override must include numeric value")
    try:
        float(threshold_override["value"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="threshold_override value must be numeric")


def _format_threshold_verdict(result: str) -> str:
    if result == "PASS":
        return "within the acceptable range"
    if result == "FAIL":
        return "outside the acceptable range"
    return "insufficient to evaluate"


def _render_measure_interpretation(
    *,
    result: str,
    metric_name: str,
    value: Optional[float],
    threshold: Optional[dict],
    custom_text: Optional[str],
    template_text: Optional[str],
    generated_text: Optional[str],
) -> str:
    if custom_text:
        return custom_text
    if generated_text:
        return generated_text

    threshold_verdict = _format_threshold_verdict(result)
    unit = ""
    if isinstance(threshold, dict):
        unit = str(threshold.get("unit", "") or "")

    rendered_value = "-"
    if value is not None:
        display_value = float(value)
        if unit == "%" and abs(display_value) <= 1:
            display_value *= 100
        if unit in {"%", "ms"}:
            rendered_value = str(int(round(display_value)))
        else:
            rendered_value = str(round(display_value, 6))

    if template_text:
        rendered = template_text
        rendered = rendered.replace("{metric_name}", metric_name)
        rendered = rendered.replace("{value}", rendered_value)
        rendered = rendered.replace("{unit}", unit)
        rendered = rendered.replace("{threshold_verdict}", threshold_verdict)
        rendered = rendered.replace(
            "{context_sentence}",
            "This measure is calculated automatically from available telemetry and system attributes.",
        )
        return rendered

    if value is None:
        return f"No recent reading is available for {metric_name}; collect telemetry to evaluate this control."
    return (
        f"{metric_name} is {round(value, 6)}, which is {threshold_verdict}. "
        "Use peer comparison to assess relative posture."
    )


FOUNDATION_CONTROL_CODES = [
    "RM-0", "RM-1", "RM-2", "RO-2",
    "LC-1", "SE-1", "OM-1", "AA-1", "GL-1", "CO-1",
]

async def _assign_foundation_controls(app: Application, db: AsyncSession) -> None:
    """Auto-assign the 10 foundation controls to every registered application."""
    from db.models import Control
    result = await db.execute(
        select(Control).where(Control.code.in_(FOUNDATION_CONTROL_CODES))
    )
    controls = result.scalars().all()
    for control in controls:
        assignment = ControlAssignment(
            id=str(uuid4()),
            application_id=app.id,
            control_id=control.id,
            status="adopted",
            assigned_at=datetime.utcnow(),
        )
        db.add(assignment)


# ---------------------------------------------------------------------------
# Routes â€” Phase 4.1: CRUD
# ---------------------------------------------------------------------------

@router.post("/applications", status_code=status.HTTP_201_CREATED,
             response_model=RegisterApplicationResponse)
async def register_application(
    body: ApplicationRegisterRequest,
    db:   AsyncSession = Depends(get_db),
):
    app = Application(
        id=str(uuid4()),
        name=body.name,
        description=body.description,
        division_id=body.division_id,
        domain=body.domain,
        ai_system_type=body.ai_system_type,
        decision_type=body.decision_type,
        autonomy_level=body.autonomy_level,
        population_breadth=body.population_breadth,
        affected_populations=body.affected_populations,
        consent_scope=body.consent_scope,
        owner_email=body.owner_email,
        registered_at=datetime.utcnow(),
    )
    db.add(app)
    await db.flush()  # assign id before tier engine runs

    await _assign_foundation_controls(app, db)
    tier_result = await registration_trigger(app, db)

    # Refresh to pick up current_tier written by tier engine
    await db.refresh(app)

    missing = [g for g in _required_metric_groups(app)
               if g not in METRIC_GROUPS_BY_SYSTEM_TYPE.get(app.ai_system_type, [])]

    return RegisterApplicationResponse(
        application=_app_to_response(app),
        tier=_tier_result_to_response(app.id, tier_result),
        otel_config=_otel_config(app),
        missing_metric_groups=missing,
    )


@router.get("/applications", response_model=list[ApplicationResponse])
async def list_applications(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Application).order_by(Application.registered_at.desc()))
    return [_app_to_response(a) for a in result.scalars().all()]


@router.get("/applications/{app_id}", response_model=ApplicationResponse)
async def get_application(app_id: str, db: AsyncSession = Depends(get_db)):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return _app_to_response(app)


@router.patch("/applications/{app_id}", response_model=ApplicationResponse)
async def update_application(
    app_id: str,
    body:   ApplicationUpdateRequest,
    db:     AsyncSession = Depends(get_db),
):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if body.name is not None:
        app.name = body.name
    if body.description is not None:
        app.description = body.description
    if body.owner_email is not None:
        app.owner_email = body.owner_email
    if body.consent_scope is not None:
        app.consent_scope = body.consent_scope

    await db.commit()
    await db.refresh(app)
    return _app_to_response(app)


@router.patch("/applications/{app_id}/disconnect",
              response_model=ApplicationResponse)
async def disconnect_application(
    app_id: str,
    db:     AsyncSession = Depends(get_db),
):
    """Mark application as disconnected. Preserves all historical data."""
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    app.status = "disconnected"
    await db.commit()
    await db.refresh(app)
    return _app_to_response(app)


@router.get(
    "/applications/{app_id}/requirements",
    response_model=ApplicationRequirementScopeResponse,
)
async def list_application_requirements(
    app_id: str,
    q: Optional[str] = None,
    selected_only: bool = False,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    base_query = (
        select(
            Requirement.id.label("requirement_id"),
            Requirement.code.label("code"),
            Requirement.title.label("title"),
            Requirement.category.label("category"),
            Regulation.title.label("regulation_title"),
            Regulation.jurisdiction.label("jurisdiction"),
            ApplicationRequirement.id.label("selection_id"),
            ApplicationRequirement.is_default.label("is_default"),
        )
        .join(Regulation, Regulation.id == Requirement.regulation_id, isouter=True)
        .join(
            ApplicationRequirement,
            (ApplicationRequirement.requirement_id == Requirement.id)
            & (ApplicationRequirement.application_id == app_id),
            isouter=True,
        )
    )

    if q:
        pattern = f"%{q.strip().lower()}%"
        base_query = base_query.where(
            or_(
                func.lower(Requirement.code).like(pattern),
                func.lower(Requirement.title).like(pattern),
                func.lower(Regulation.title).like(pattern),
                func.lower(Regulation.jurisdiction).like(pattern),
            )
        )

    if selected_only:
        base_query = base_query.where(ApplicationRequirement.id.is_not(None))

    total_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = int(total_result.scalar_one())

    rows_result = await db.execute(
        base_query.order_by(Requirement.code).offset(skip).limit(limit)
    )
    rows = rows_result.all()
    requirement_ids = [str(row.requirement_id) for row in rows]

    linked_controls_by_requirement: dict[str, list[dict[str, Optional[str]]]] = {}
    if requirement_ids:
        linked_controls_result = await db.execute(
            select(
                ControlRequirement.requirement_id.label("requirement_id"),
                Control.id.label("control_id"),
                Control.code.label("control_code"),
                Control.title.label("control_title"),
            )
            .join(Control, Control.id == ControlRequirement.control_id)
            .where(ControlRequirement.requirement_id.in_(requirement_ids))
            .order_by(Control.code)
        )
        linked_control_rows = linked_controls_result.all()
        control_ids = sorted({str(row.control_id) for row in linked_control_rows})

        primary_metric_by_control: dict[str, dict[str, Any]] = {}
        if control_ids:
            metric_rows = await db.execute(
                select(
                    ControlMetricDefinition.control_id,
                    ControlMetricDefinition.metric_name,
                    ControlMetricDefinition.threshold,
                )
                .where(ControlMetricDefinition.control_id.in_(control_ids))
                .order_by(ControlMetricDefinition.control_id, ControlMetricDefinition.metric_name)
            )
            for metric_row in metric_rows.all():
                control_key = str(metric_row.control_id)
                if control_key not in primary_metric_by_control:
                    primary_metric_by_control[control_key] = {
                        "metric_name": metric_row.metric_name,
                        "threshold": metric_row.threshold,
                    }

        for row in linked_control_rows:
            requirement_key = str(row.requirement_id)
            metric_meta = primary_metric_by_control.get(str(row.control_id), {})
            linked_controls_by_requirement.setdefault(requirement_key, []).append(
                {
                    "id": str(row.control_id),
                    "code": row.control_code,
                    "title": row.control_title,
                    "metric_name": metric_meta.get("metric_name"),
                    "default_threshold": metric_meta.get("threshold"),
                }
            )

    selected_count = int(
        await db.scalar(
            select(func.count())
            .select_from(ApplicationRequirement)
            .where(ApplicationRequirement.application_id == app_id)
        )
        or 0
    )

    items = [
        ApplicationRequirementScopeItem(
            requirement_id=str(row.requirement_id),
            code=row.code,
            title=row.title,
            regulation_title=row.regulation_title,
            jurisdiction=row.jurisdiction,
            category=row.category,
            selected=row.selection_id is not None,
            is_default=bool(row.is_default),
            linked_controls=linked_controls_by_requirement.get(str(row.requirement_id), []),
        )
        for row in rows
    ]

    return ApplicationRequirementScopeResponse(
        application_id=app_id,
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        selected_count=selected_count,
    )


@router.put(
    "/applications/{app_id}/requirements",
    response_model=ApplicationRequirementScopeUpdateResponse,
)
async def update_application_requirements(
    app_id: str,
    body: ApplicationRequirementScopeUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    normalized_ids: list[str] = []
    invalid_ids: list[str] = []
    for raw_id in body.requirement_ids:
        value = (raw_id or "").strip()
        if not value:
            continue
        try:
            normalized_ids.append(str(UUID(value)))
        except ValueError:
            invalid_ids.append(value)

    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid requirement UUID(s): {', '.join(invalid_ids[:5])}",
        )

    requested_ids = sorted(set(normalized_ids))
    if requested_ids:
        existing_result = await db.execute(
            select(Requirement.id).where(Requirement.id.in_(requested_ids))
        )
        existing_ids = {str(rid) for rid in existing_result.scalars().all()}
        missing_ids = [rid for rid in requested_ids if rid not in existing_ids]
        if missing_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown requirement_id(s): {', '.join(missing_ids[:5])}",
            )

    existing_rows_result = await db.execute(
        select(ApplicationRequirement).where(ApplicationRequirement.application_id == app_id)
    )
    existing_rows = list(existing_rows_result.scalars().all())
    existing_by_requirement = {str(row.requirement_id): row for row in existing_rows}
    default_ids = {
        str(row.requirement_id)
        for row in existing_rows
        if bool(row.is_default)
    }

    # Platform defaults are non-removable at app scope.
    final_ids = sorted(set(requested_ids) | default_ids)

    updated_at = datetime.utcnow()
    for row in existing_rows:
        req_id = str(row.requirement_id)
        if req_id not in final_ids and not bool(row.is_default):
            await db.delete(row)

    for requirement_id in final_ids:
        if requirement_id in existing_by_requirement:
            continue
        db.add(
            ApplicationRequirement(
                id=str(uuid4()),
                application_id=app_id,
                requirement_id=requirement_id,
                selected_at=updated_at,
                is_default=False,
                added_by="application_owner",
                added_at=updated_at,
            )
        )

    await db.commit()

    return ApplicationRequirementScopeUpdateResponse(
        application_id=app_id,
        selected_count=len(final_ids),
        updated_at=updated_at,
    )


@router.get(
    "/applications/{app_id}/interpretations",
    response_model=list[AppInterpretationResponse],
)
async def list_application_interpretations(
    app_id: str,
    db: AsyncSession = Depends(get_db),
):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    result = await db.execute(
        select(
            AppInterpretation,
            Requirement.code.label("requirement_code"),
            Requirement.title.label("requirement_title"),
            Control.code.label("control_code"),
            Control.title.label("control_title"),
        )
        .join(Requirement, Requirement.id == AppInterpretation.requirement_id, isouter=True)
        .join(Control, Control.id == AppInterpretation.control_id, isouter=True)
        .where(AppInterpretation.application_id == app_id)
        .order_by(AppInterpretation.set_at.desc())
    )

    items: list[AppInterpretationResponse] = []
    for row in result.all():
        interp = row[0]
        items.append(
            AppInterpretationResponse(
                id=str(interp.id),
                application_id=str(interp.application_id),
                requirement_id=str(interp.requirement_id),
                requirement_code=row.requirement_code,
                requirement_title=row.requirement_title,
                control_id=str(interp.control_id),
                control_code=row.control_code,
                control_title=row.control_title,
                interpretation_text=interp.interpretation_text,
                threshold_override=interp.threshold_override,
                set_by=interp.set_by,
                set_at=interp.set_at,
            )
        )
    return items


@router.post(
    "/applications/{app_id}/interpretations",
    response_model=AppInterpretationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application_interpretation(
    app_id: str,
    body: AppInterpretationCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    _validate_threshold_override(body.threshold_override)

    requirement = await db.get(Requirement, body.requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")
    control = await db.get(Control, body.control_id)
    if not control:
        raise HTTPException(status_code=404, detail="Control not found")

    link_exists = await db.scalar(
        select(func.count())
        .select_from(ControlRequirement)
        .where(
            ControlRequirement.control_id == body.control_id,
            ControlRequirement.requirement_id == body.requirement_id,
        )
    )
    if not link_exists:
        raise HTTPException(
            status_code=400,
            detail="control_id is not linked to requirement_id in control_requirement",
        )

    now = datetime.utcnow()
    existing = await db.scalar(
        select(AppInterpretation).where(
            AppInterpretation.application_id == app_id,
            AppInterpretation.requirement_id == body.requirement_id,
            AppInterpretation.control_id == body.control_id,
        )
    )
    if existing:
        existing.interpretation_text = body.interpretation_text
        existing.threshold_override = body.threshold_override
        existing.set_by = body.set_by
        existing.set_at = now
        entity = existing
    else:
        entity = AppInterpretation(
            id=str(uuid4()),
            application_id=app_id,
            requirement_id=body.requirement_id,
            control_id=body.control_id,
            interpretation_text=body.interpretation_text,
            threshold_override=body.threshold_override,
            set_by=body.set_by,
            set_at=now,
        )
        db.add(entity)

    await db.commit()
    await db.refresh(entity)

    return AppInterpretationResponse(
        id=str(entity.id),
        application_id=str(entity.application_id),
        requirement_id=str(entity.requirement_id),
        requirement_code=requirement.code,
        requirement_title=requirement.title,
        control_id=str(entity.control_id),
        control_code=control.code,
        control_title=control.title,
        interpretation_text=entity.interpretation_text,
        threshold_override=entity.threshold_override,
        set_by=entity.set_by,
        set_at=entity.set_at,
    )


@router.patch(
    "/applications/{app_id}/interpretations/{interpretation_id}",
    response_model=AppInterpretationResponse,
)
async def patch_application_interpretation(
    app_id: str,
    interpretation_id: str,
    body: AppInterpretationPatchRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    entity = await db.scalar(
        select(AppInterpretation).where(
            AppInterpretation.id == interpretation_id,
            AppInterpretation.application_id == app_id,
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Interpretation not found")

    _validate_threshold_override(body.threshold_override)

    if body.interpretation_text is not None:
        entity.interpretation_text = body.interpretation_text
    if body.threshold_override is not None:
        entity.threshold_override = body.threshold_override
    if body.set_by is not None:
        entity.set_by = body.set_by
    entity.set_at = datetime.utcnow()

    await db.commit()
    await db.refresh(entity)

    requirement = await db.get(Requirement, entity.requirement_id)
    control = await db.get(Control, entity.control_id)

    return AppInterpretationResponse(
        id=str(entity.id),
        application_id=str(entity.application_id),
        requirement_id=str(entity.requirement_id),
        requirement_code=requirement.code if requirement else None,
        requirement_title=requirement.title if requirement else None,
        control_id=str(entity.control_id),
        control_code=control.code if control else None,
        control_title=control.title if control else None,
        interpretation_text=entity.interpretation_text,
        threshold_override=entity.threshold_override,
        set_by=entity.set_by,
        set_at=entity.set_at,
    )


@router.get(
    "/applications/{app_id}/dashboard/{step}",
    response_model=DashboardStepResponse,
)
async def get_dashboard_step(
    app_id: str,
    step: int = Path(..., ge=1, le=9),
    db: AsyncSession = Depends(get_db),
):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    step_key = STEP_KEY_MAP[step]

    if step == 1:
        rows = await _build_curated_dashboard_rows(
            app_id=app_id,
            tier=app.current_tier,
            configs=STEP1_CORPORATE_FINOPS_KPIS,
            db=db,
        )
        rows_with_values = sum(1 for row in rows if row.value is not None)
        summary = {
            "name": app.name,
            "description": app.description,
            "domain": app.domain,
            "ai_system_type": app.ai_system_type,
            "decision_type": app.decision_type,
            "autonomy_level": app.autonomy_level,
            "current_tier": app.current_tier,
            "baseline_kpi_count": len(rows),
            "instrumented_kpi_count": rows_with_values,
            "missing_kpi_count": len(rows) - rows_with_values,
        }
        if rows_with_values == 0:
            summary["message"] = (
                "FinOps KPIs are configured for Corporate Oversight, but no cost/token telemetry "
                "has been ingested yet for this application."
            )
        return DashboardStepResponse(
            application_id=app_id,
            step=step,
            step_key=step_key,
            generated_at=datetime.utcnow(),
            scope_active=False,
            row_count=len(rows),
            summary=summary,
            rows=rows,
        )

    if step == 2:
        latest_event = await db.scalar(
            select(TierChangeEvent)
            .where(TierChangeEvent.application_id == app_id)
            .order_by(TierChangeEvent.changed_at.desc())
            .limit(1)
        )
        selected_count = int(
            await db.scalar(
                select(func.count())
                .select_from(ApplicationRequirement)
                .where(ApplicationRequirement.application_id == app_id)
            )
            or 0
        )
        default_count = int(
            await db.scalar(
                select(func.count())
                .select_from(ApplicationRequirement)
                .where(
                    ApplicationRequirement.application_id == app_id,
                    ApplicationRequirement.is_default.is_(True),
                )
            )
            or 0
        )

        control_codes = sorted({code for code, _ in STEP2_BASELINE_KPI_PAIRS})
        pair_set = set(STEP2_BASELINE_KPI_PAIRS)

        control_rows = await db.execute(
            select(Control.id, Control.code, Control.title)
            .where(Control.code.in_(control_codes))
        )
        controls_by_code = {row.code: row for row in control_rows.all()}
        control_ids = [str(row.id) for row in controls_by_code.values()]

        # Refresh Step 2 KPI values on-demand so status reflects latest telemetry + derived formulas.
        if control_ids:
            await calculator.calculate_for_application(
                app_id=app_id,
                db=db,
                scoped_control_ids=set(control_ids),
            )
            await db.flush()

        # Build tag map for chips in UI
        tags_by_control: dict[str, set[str]] = {}
        if control_ids:
            tag_rows = await db.execute(
                select(ControlLifecycleTag.control_id, ControlLifecycleTag.tag)
                .where(
                    ControlLifecycleTag.control_id.in_(control_ids),
                    ControlLifecycleTag.approved.is_(True),
                )
            )
            for control_id, tag in tag_rows.all():
                key = str(control_id)
                tags_by_control.setdefault(key, set()).add(tag)

        # Requirement pick: one representative baseline rule per control.
        req_rows = await db.execute(
            select(
                ControlRequirement.control_id,
                Requirement.id,
                Requirement.code,
                Requirement.title,
            )
            .join(Requirement, Requirement.id == ControlRequirement.requirement_id)
            .join(Regulation, Regulation.id == Requirement.regulation_id)
            .where(
                ControlRequirement.control_id.in_(control_ids),
                ~func.lower(Regulation.title).like("%frontier%"),
                ~func.lower(Regulation.title).like("%genai%"),
            )
            .order_by(Requirement.code)
        )
        requirements_by_control: dict[str, list[dict[str, str]]] = {}
        for row in req_rows.all():
            requirements_by_control.setdefault(str(row.control_id), []).append(
                {
                    "id": str(row.id),
                    "code": row.code,
                    "title": row.title,
                }
            )

        # Density for sorting/usefulness signal.
        reg_density_rows = await db.execute(
            select(
                ControlRequirement.control_id,
                func.count(ControlRequirement.requirement_id).label("density"),
            )
            .where(ControlRequirement.control_id.in_(control_ids))
            .group_by(ControlRequirement.control_id)
        )
        density_map = {str(row.control_id): int(row.density or 0) for row in reg_density_rows.all()}

        # Metric definitions for threshold + formula interpretation templates.
        metric_def_rows = await db.execute(
            select(
                ControlMetricDefinition.id,
                ControlMetricDefinition.control_id,
                ControlMetricDefinition.metric_name,
                ControlMetricDefinition.threshold,
            )
            .where(ControlMetricDefinition.control_id.in_(control_ids))
        )
        metric_def_map: dict[tuple[str, str], dict[str, Any]] = {}
        metric_def_ids: list[str] = []
        for row in metric_def_rows.all():
            key = (str(row.control_id), row.metric_name)
            metric_def_map[key] = {
                "id": str(row.id),
                "threshold": row.threshold,
            }
            metric_def_ids.append(str(row.id))

        formula_map: dict[str, MeasureFormula] = {}
        if metric_def_ids:
            formula_rows = await db.execute(
                select(MeasureFormula)
                .where(MeasureFormula.control_metric_definition_id.in_(metric_def_ids))
            )
            formula_map = {
                str(row.control_metric_definition_id): row
                for row in formula_rows.scalars().all()
            }

        benchmark_rows = await db.execute(
            select(TierPeerAggregate.metric_name, TierPeerAggregate.avg_value, TierPeerAggregate.peer_count)
            .where(TierPeerAggregate.tier == app.current_tier)
        )
        peer_map = {
            row.metric_name: {"avg": row.avg_value, "count": row.peer_count}
            for row in benchmark_rows.all()
        }

        tier_app_count = int(
            await db.scalar(
                select(func.count())
                .select_from(Application)
                .where(Application.current_tier == app.current_tier)
            )
            or 0
        )
        adoption_rows = await db.execute(
            select(ControlAssignment.control_id, func.count().label("adoption_count"))
            .join(Application, Application.id == ControlAssignment.application_id)
            .where(
                ControlAssignment.status == "adopted",
                Application.current_tier == app.current_tier,
                ControlAssignment.control_id.in_(control_ids),
            )
            .group_by(ControlAssignment.control_id)
        )
        adoption_map = {str(row.control_id): int(row.adoption_count) for row in adoption_rows.all()}

        rows: list[DashboardMeasureRow] = []
        for control_code, metric_name in STEP2_BASELINE_KPI_PAIRS:
            control = controls_by_code.get(control_code)
            if not control:
                continue
            control_id = str(control.id)
            pair_key = (control_id, metric_name)
            metric_def = metric_def_map.get(pair_key)
            if not metric_def:
                continue

            threshold = metric_def.get("threshold")
            value, result = await _compute_step2_live_metric(
                app_id=app_id,
                metric_name=metric_name,
                threshold=threshold,
                db=db,
            )

            metric_def_id = metric_def.get("id")
            formula = formula_map.get(metric_def_id) if metric_def_id else None
            interpretation_text = _render_measure_interpretation(
                result=result,
                metric_name=metric_name,
                value=value,
                threshold=threshold,
                custom_text=None,
                template_text=formula.interpretation_template if formula else None,
                generated_text=(
                    formula.interpretation_generated
                    if formula and formula.interpretation_approved and formula.interpretation_generated
                    else None
                ),
            )

            requirement_info = (requirements_by_control.get(control_id) or [None])[0]
            peer = peer_map.get(metric_name, {})
            peer_avg = peer.get("avg")
            peer_count = peer.get("count")
            industry_benchmark = _extract_industry_benchmark(threshold)
            peer_benchmark = peer_avg
            benchmark_result = _evaluate_benchmark_result(
                value=value,
                threshold=threshold,
                industry_benchmark=industry_benchmark,
                peer_benchmark=peer_benchmark,
            )
            peer_delta = None
            if peer_avg is not None and value is not None:
                peer_delta = round(float(value) - float(peer_avg), 6)

            adoption_count = adoption_map.get(control_id, 0)
            adoption_rate = (
                round(adoption_count / tier_app_count, 4)
                if tier_app_count > 0
                else None
            )

            rows.append(
                DashboardMeasureRow(
                    control_id=control_id,
                    control_code=control.code,
                    control_title=control.title,
                    requirement_id=requirement_info["id"] if requirement_info else None,
                    requirement_code=requirement_info["code"] if requirement_info else None,
                    requirement_title=requirement_info["title"] if requirement_info else None,
                    metric_name=metric_name,
                    result=result,
                    value=value,
                    threshold=threshold,
                    interpretation_text=interpretation_text,
                    industry_benchmark=industry_benchmark,
                    peer_benchmark=peer_benchmark,
                    benchmark_result=benchmark_result,
                    peer_avg=peer_avg,
                    peer_delta=peer_delta,
                    peer_count=peer_count,
                    percentile_rank=None,
                    p25=None,
                    p75=None,
                    adoption_count=adoption_count,
                    adoption_rate=adoption_rate,
                    popularity_stars=_to_popularity_stars(adoption_rate),
                    tags=sorted(tags_by_control.get(control_id, set())),
                    regulatory_density=density_map.get(control_id, 0),
                )
            )

        rows.sort(key=lambda r: (_result_priority(r.result), -r.regulatory_density, r.control_code or ""))

        return DashboardStepResponse(
            application_id=app_id,
            step=step,
            step_key=step_key,
            generated_at=datetime.utcnow(),
            scope_active=True,
            row_count=len(rows),
            summary={
                "current_tier": app.current_tier,
                "latest_tier_change_at": latest_event.changed_at.isoformat() if latest_event else None,
                "latest_tier_reason": latest_event.reason if latest_event else None,
                "selected_requirements": selected_count,
                "default_requirements": default_count,
                "baseline_kpi_count": len(rows),
            },
            rows=rows,
        )

    if step == 3:
        rows = await _build_curated_dashboard_rows(
            app_id=app_id,
            tier=app.current_tier,
            configs=STEP3_TECHNICAL_ARCHITECTURE_KPIS,
            db=db,
        )
        rows_with_values = sum(1 for row in rows if row.value is not None)
        summary = {
            "baseline_kpi_count": len(rows),
            "instrumented_kpi_count": rows_with_values,
            "missing_kpi_count": len(rows) - rows_with_values,
        }
        if rows_with_values == 0:
            summary["message"] = (
                "Technical Architecture is defined by RAG-specific telemetry. "
                "Instrument citation coverage and retrieval latency to populate this panel."
            )
        return DashboardStepResponse(
            application_id=app_id,
            step=step,
            step_key=step_key,
            generated_at=datetime.utcnow(),
            scope_active=True,
            row_count=len(rows),
            summary=summary,
            rows=rows,
        )

    if step == 4:
        rows = await _build_curated_dashboard_rows(
            app_id=app_id,
            tier=app.current_tier,
            configs=STEP4_DATA_READINESS_KPIS,
            db=db,
        )
        rows_with_values = sum(1 for row in rows if row.value is not None)
        summary = {
            "baseline_kpi_count": len(rows),
            "instrumented_kpi_count": rows_with_values,
            "missing_kpi_count": len(rows) - rows_with_values,
        }
        if rows_with_values == 0:
            summary["message"] = (
                "Data Readiness KPIs are configured but no telemetry values are available yet "
                "for this application."
            )
        return DashboardStepResponse(
            application_id=app_id,
            step=step,
            step_key=step_key,
            generated_at=datetime.utcnow(),
            scope_active=True,
            row_count=len(rows),
            summary=summary,
            rows=rows,
        )

    if step == 5:
        rows = await _build_curated_dashboard_rows(
            app_id=app_id,
            tier=app.current_tier,
            configs=STEP5_DATA_INTEGRATION_KPIS,
            db=db,
        )
        rows_with_values = sum(1 for row in rows if row.value is not None)
        summary = {
            "baseline_kpi_count": len(rows),
            "instrumented_kpi_count": rows_with_values,
            "missing_kpi_count": len(rows) - rows_with_values,
        }
        if rows_with_values == 0:
            summary["message"] = (
                "Data Integration KPIs are configured but no telemetry values are available yet "
                "for this application."
            )
        return DashboardStepResponse(
            application_id=app_id,
            step=step,
            step_key=step_key,
            generated_at=datetime.utcnow(),
            scope_active=True,
            row_count=len(rows),
            summary=summary,
            rows=rows,
        )

    if step == 6:
        rows = await _build_curated_dashboard_rows(
            app_id=app_id,
            tier=app.current_tier,
            configs=STEP6_SECURITY_KPIS,
            db=db,
        )
        rows_with_values = sum(1 for row in rows if row.value is not None)
        summary = {
            "baseline_kpi_count": len(rows),
            "instrumented_kpi_count": rows_with_values,
            "missing_kpi_count": len(rows) - rows_with_values,
        }
        if rows_with_values == 0:
            summary["message"] = (
                "Security KPIs are configured but no telemetry values are available yet "
                "for this application."
            )
        return DashboardStepResponse(
            application_id=app_id,
            step=step,
            step_key=step_key,
            generated_at=datetime.utcnow(),
            scope_active=True,
            row_count=len(rows),
            summary=summary,
            rows=rows,
        )

    if step == 7:
        rows = await _build_curated_dashboard_rows(
            app_id=app_id,
            tier=app.current_tier,
            configs=STEP7_INFRASTRUCTURE_KPIS,
            db=db,
        )
        rows_with_values = sum(1 for row in rows if row.value is not None)
        summary = {
            "baseline_kpi_count": len(rows),
            "instrumented_kpi_count": rows_with_values,
            "missing_kpi_count": len(rows) - rows_with_values,
        }
        if rows_with_values == 0:
            summary["message"] = (
                "Infrastructure KPIs are configured but no telemetry values are available yet "
                "for this application."
            )
        return DashboardStepResponse(
            application_id=app_id,
            step=step,
            step_key=step_key,
            generated_at=datetime.utcnow(),
            scope_active=True,
            row_count=len(rows),
            summary=summary,
            rows=rows,
        )

    if step == 8:
        rows = await _build_curated_dashboard_rows(
            app_id=app_id,
            tier=app.current_tier,
            configs=STEP8_SOLUTION_DESIGN_KPIS,
            db=db,
        )
        rows_with_values = sum(1 for row in rows if row.value is not None)
        summary = {
            "baseline_kpi_count": len(rows),
            "instrumented_kpi_count": rows_with_values,
            "missing_kpi_count": len(rows) - rows_with_values,
        }
        if rows_with_values == 0:
            summary["message"] = (
                "Solution Design KPIs are configured but no telemetry values are available yet "
                "for this application."
            )
        return DashboardStepResponse(
            application_id=app_id,
            step=step,
            step_key=step_key,
            generated_at=datetime.utcnow(),
            scope_active=True,
            row_count=len(rows),
            summary=summary,
            rows=rows,
        )

    if step == 9:
        rows = await _build_curated_dashboard_rows(
            app_id=app_id,
            tier=app.current_tier,
            configs=STEP9_SYSTEM_PERFORMANCE_KPIS,
            db=db,
        )
        rows_with_values = sum(1 for row in rows if row.value is not None)
        summary = {
            "baseline_kpi_count": len(rows),
            "instrumented_kpi_count": rows_with_values,
            "missing_kpi_count": len(rows) - rows_with_values,
        }
        if rows_with_values == 0:
            summary["message"] = (
                "System Performance KPIs are configured but no telemetry values are available yet "
                "for this application."
            )
        return DashboardStepResponse(
            application_id=app_id,
            step=step,
            step_key=step_key,
            generated_at=datetime.utcnow(),
            scope_active=True,
            row_count=len(rows),
            summary=summary,
            rows=rows,
        )

    selected_requirements_result = await db.execute(
        select(ApplicationRequirement.requirement_id)
        .where(ApplicationRequirement.application_id == app_id)
    )
    selected_requirement_ids = [str(rid) for rid in selected_requirements_result.scalars().all()]
    if not selected_requirement_ids:
        return DashboardStepResponse(
            application_id=app_id,
            step=step,
            step_key=step_key,
            generated_at=datetime.utcnow(),
            scope_active=False,
            row_count=0,
            summary={"message": "No active requirements selected for this application."},
            rows=[],
        )

    scope_controls_result = await db.execute(
        select(ControlRequirement.control_id)
        .where(ControlRequirement.requirement_id.in_(selected_requirement_ids))
        .distinct()
    )
    scoped_control_ids = {str(cid) for cid in scope_controls_result.scalars().all()}
    if not scoped_control_ids:
        return DashboardStepResponse(
            application_id=app_id,
            step=step,
            step_key=step_key,
            generated_at=datetime.utcnow(),
            scope_active=True,
            row_count=0,
            summary={"message": "No controls are linked to the active requirement scope."},
            rows=[],
        )

    step_tags = STEP_TAG_MAP.get(step, set())
    tag_rows = await db.execute(
        select(ControlLifecycleTag.control_id, ControlLifecycleTag.tag)
        .where(
            ControlLifecycleTag.control_id.in_(scoped_control_ids),
            ControlLifecycleTag.approved.is_(True),
        )
    )
    tags_by_control: dict[str, set[str]] = {}
    for control_id, tag in tag_rows.all():
        key = str(control_id)
        tags_by_control.setdefault(key, set()).add(tag)

    if step_tags:
        scoped_control_ids = {
            cid for cid in scoped_control_ids
            if tags_by_control.get(cid, set()) & step_tags
        }

    if not scoped_control_ids:
        return DashboardStepResponse(
            application_id=app_id,
            step=step,
            step_key=step_key,
            generated_at=datetime.utcnow(),
            scope_active=True,
            row_count=0,
            summary={"message": "No approved lifecycle tags matched this dashboard step."},
            rows=[],
        )

    results = await calculator.calculate_for_application(
        app_id=app_id,
        db=db,
        scoped_control_ids=scoped_control_ids,
    )
    await db.commit()

    control_rows = await db.execute(
        select(Control.id, Control.code, Control.title)
        .where(Control.id.in_(scoped_control_ids))
    )
    control_map = {
        str(row.id): {"code": row.code, "title": row.title}
        for row in control_rows.all()
    }

    req_rows = await db.execute(
        select(
            ControlRequirement.control_id,
            Requirement.id,
            Requirement.code,
            Requirement.title,
        )
        .join(Requirement, Requirement.id == ControlRequirement.requirement_id)
        .where(
            ControlRequirement.control_id.in_(scoped_control_ids),
            ControlRequirement.requirement_id.in_(selected_requirement_ids),
        )
        .order_by(Requirement.code)
    )
    requirements_by_control: dict[str, list[dict]] = {}
    for row in req_rows.all():
        requirements_by_control.setdefault(str(row.control_id), []).append(
            {
                "id": str(row.id),
                "code": row.code,
                "title": row.title,
            }
        )

    reg_density_rows = await db.execute(
        select(
            ControlRequirement.control_id,
            func.count(ControlRequirement.requirement_id).label("density"),
        )
        .where(ControlRequirement.control_id.in_(scoped_control_ids))
        .group_by(ControlRequirement.control_id)
    )
    density_map = {str(row.control_id): int(row.density or 0) for row in reg_density_rows.all()}

    interp_rows = await db.execute(
        select(AppInterpretation)
        .where(
            AppInterpretation.application_id == app_id,
            AppInterpretation.control_id.in_(scoped_control_ids),
        )
        .order_by(AppInterpretation.set_at.desc())
    )
    interp_map: dict[tuple[str, str], AppInterpretation] = {}
    interp_by_control: dict[str, AppInterpretation] = {}
    for interp in interp_rows.scalars().all():
        key = (str(interp.control_id), str(interp.requirement_id))
        interp_map[key] = interp
        interp_by_control.setdefault(str(interp.control_id), interp)

    metric_def_rows = await db.execute(
        select(ControlMetricDefinition.id, ControlMetricDefinition.control_id, ControlMetricDefinition.metric_name)
        .where(ControlMetricDefinition.control_id.in_(scoped_control_ids))
    )
    metric_def_id_map = {
        (str(row.control_id), row.metric_name): str(row.id)
        for row in metric_def_rows.all()
    }

    formula_map: dict[str, MeasureFormula] = {}
    formula_ids = list(metric_def_id_map.values())
    if formula_ids:
        formula_rows = await db.execute(
            select(MeasureFormula)
            .where(MeasureFormula.control_metric_definition_id.in_(formula_ids))
        )
        formula_map = {
            str(row.control_metric_definition_id): row
            for row in formula_rows.scalars().all()
        }

    benchmark_rows = await db.execute(
        select(TierPeerAggregate.metric_name, TierPeerAggregate.avg_value, TierPeerAggregate.peer_count)
        .where(TierPeerAggregate.tier == app.current_tier)
    )
    peer_map = {
        row.metric_name: {"avg": row.avg_value, "count": row.peer_count}
        for row in benchmark_rows.all()
    }

    tier_app_count = int(
        await db.scalar(
            select(func.count())
            .select_from(Application)
            .where(Application.current_tier == app.current_tier)
        )
        or 0
    )
    adoption_rows = await db.execute(
        select(ControlAssignment.control_id, func.count().label("adoption_count"))
        .join(Application, Application.id == ControlAssignment.application_id)
        .where(
            ControlAssignment.status == "adopted",
            Application.current_tier == app.current_tier,
            ControlAssignment.control_id.in_(scoped_control_ids),
        )
        .group_by(ControlAssignment.control_id)
    )
    adoption_map = {str(row.control_id): int(row.adoption_count) for row in adoption_rows.all()}

    rows: list[DashboardMeasureRow] = []
    for entry in results:
        control_id = str(entry["control_id"])
        metric_name = entry["metric_name"]
        requirement_info = (requirements_by_control.get(control_id) or [None])[0]
        requirement_id = requirement_info["id"] if requirement_info else None
        interp = None
        if requirement_id:
            interp = interp_map.get((control_id, requirement_id))
        if interp is None:
            interp = interp_by_control.get(control_id)

        threshold_for_row = interp.threshold_override if interp and interp.threshold_override else entry["threshold"]
        metric_def_id = metric_def_id_map.get((control_id, metric_name))
        formula = formula_map.get(metric_def_id) if metric_def_id else None
        interpretation_text = _render_measure_interpretation(
            result=entry["result"],
            metric_name=metric_name,
            value=entry["value"],
            threshold=threshold_for_row,
            custom_text=interp.interpretation_text if interp else None,
            template_text=formula.interpretation_template if formula else None,
            generated_text=(
                formula.interpretation_generated
                if formula and formula.interpretation_approved and formula.interpretation_generated
                else None
            ),
        )

        peer = peer_map.get(metric_name, {})
        peer_avg = peer.get("avg")
        peer_count = peer.get("count")
        industry_benchmark = _extract_industry_benchmark(threshold_for_row)
        peer_benchmark = peer_avg
        benchmark_result = _evaluate_benchmark_result(
            value=entry["value"],
            threshold=threshold_for_row,
            industry_benchmark=industry_benchmark,
            peer_benchmark=peer_benchmark,
        )
        peer_delta = None
        if peer_avg is not None and entry["value"] is not None:
            peer_delta = round(float(entry["value"]) - float(peer_avg), 6)

        adoption_count = adoption_map.get(control_id, 0)
        adoption_rate = (
            round(adoption_count / tier_app_count, 4)
            if tier_app_count > 0
            else None
        )

        rows.append(
            DashboardMeasureRow(
                control_id=control_id,
                control_code=control_map.get(control_id, {}).get("code"),
                control_title=control_map.get(control_id, {}).get("title"),
                requirement_id=requirement_id,
                requirement_code=requirement_info["code"] if requirement_info else None,
                requirement_title=requirement_info["title"] if requirement_info else None,
                metric_name=metric_name,
                result=entry["result"],
                value=entry["value"],
                threshold=threshold_for_row,
                interpretation_text=interpretation_text,
                industry_benchmark=industry_benchmark,
                peer_benchmark=peer_benchmark,
                benchmark_result=benchmark_result,
                peer_avg=peer_avg,
                peer_delta=peer_delta,
                peer_count=peer_count,
                percentile_rank=None,
                p25=None,
                p75=None,
                adoption_count=adoption_count,
                adoption_rate=adoption_rate,
                popularity_stars=_to_popularity_stars(adoption_rate),
                tags=sorted(tags_by_control.get(control_id, set())),
                regulatory_density=density_map.get(control_id, 0),
            )
        )

    rows.sort(key=lambda r: (_result_priority(r.result), -r.regulatory_density, r.control_code or ""))

    return DashboardStepResponse(
        application_id=app_id,
        step=step,
        step_key=step_key,
        generated_at=datetime.utcnow(),
        scope_active=True,
        row_count=len(rows),
        summary={
            "current_tier": app.current_tier,
            "selected_requirements": len(selected_requirement_ids),
            "scoped_controls": len(scoped_control_ids),
            "matching_step_tags": sorted(step_tags),
        },
        rows=rows,
    )


# ---------------------------------------------------------------------------
# Routes â€” Phase 4.3: Tier
# ---------------------------------------------------------------------------

@router.get("/applications/{app_id}/tier", response_model=TierResponse)
async def get_tier(app_id: str, db: AsyncSession = Depends(get_db)):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Fetch the most recent TierChangeEvent for full breakdown
    result = await db.execute(
        select(TierChangeEvent)
        .where(TierChangeEvent.application_id == app_id)
        .order_by(TierChangeEvent.changed_at.desc())
        .limit(1)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="No tier calculated yet")

    # Parse stored reason string back to structured response
    # Reason format: "score=XX.XX floor=none|rule dims={...}"
    import ast
    import re
    score_match = re.search(r"score=([\d.]+)", event.reason or "")
    floor_match = re.search(r"floor=(\S+)", event.reason or "")
    dims_match  = re.search(r"dims=(\{.*\})", event.reason or "")

    raw_score  = float(score_match.group(1)) if score_match else 0.0
    floor_rule = floor_match.group(1) if floor_match else None
    if floor_rule == "none":
        floor_rule = None
    dims_dict  = ast.literal_eval(dims_match.group(1)) if dims_match else {}

    return TierResponse(
        application_id=app_id,
        current_tier=event.new_tier,
        raw_score=raw_score,
        floor_rule=floor_rule,
        dimensions=TierDimensionBreakdown(**dims_dict) if dims_dict else TierDimensionBreakdown(
            deployment_domain=0, decision_type=0, autonomy_level=0,
            population_breadth=0, affected_populations=0, likelihood=0,
        ),
        calculated_at=event.changed_at,
    )


@router.get("/applications/{app_id}/tier/history",
            response_model=list[TierHistoryEntry])
async def get_tier_history(app_id: str, db: AsyncSession = Depends(get_db)):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    result = await db.execute(
        select(TierChangeEvent)
        .where(TierChangeEvent.application_id == app_id)
        .order_by(TierChangeEvent.changed_at.desc())
    )
    return [
        TierHistoryEntry(
            id=e.id,
            previous_tier=e.previous_tier,
            new_tier=e.new_tier,
            reason=e.reason,
            changed_at=e.changed_at,
        )
        for e in result.scalars().all()
    ]


# ---------------------------------------------------------------------------
# Routes â€” Phase 4.6 / 4.7 (not yet implemented)
# ---------------------------------------------------------------------------

@router.get("/applications/{app_id}/alignment")
async def get_alignment(app_id: str, db: AsyncSession = Depends(get_db)):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    result = await calculate_alignment(app, db)

    return {
        "application_id":    result.application_id,
        "alignment_score":   result.alignment_score,
        "calculated_at":     result.calculated_at,
        "weights_config_id": result.weights_config_id,
        "weights": {
            "peer_adoption_rate": result.w1_peer,
            "regulatory_density": result.w2_regulatory,
            "trend_velocity":     result.w3_trend,
        },
        "peer_cohort_size": result.peer_cohort_size,
        "commentary":       result.commentary,
        "controls": [
            {
                "control_id":          c.control_id,
                "peer_adoption_rate":  c.peer_adoption_rate,
                "regulatory_density":  c.regulatory_density,
                "trend_velocity":      c.trend_velocity,
                "control_weight":      c.control_weight,
                "adopted":             c.adopted,
            }
            for c in result.controls
        ],
    }


@router.get("/applications/{app_id}/benchmarks")
async def get_benchmarks(app_id: str, db: AsyncSession = Depends(get_db)):
    """
    Peer benchmarks â€” metric-by-metric comparison against apps in same tier.
    No minimum cohort enforced â€” returns available data with cohort size indicated.
    """
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if not app.current_tier:
        return {
            "application_id": app_id,
            "tier": None,
            "peer_count": 0,
            "tier_app_count": 0,
            "available": False,
            "reason": "Application has no tier assigned yet",
            "benchmarks": [],
        }

    # Get peer aggregates for this tier
    aggs_result = await db.execute(
        select(TierPeerAggregate)
        .where(TierPeerAggregate.tier == app.current_tier)
        .order_by(TierPeerAggregate.metric_name)
    )
    aggregates = aggs_result.scalars().all()
    tier_app_count = int(
        await db.scalar(
            select(func.count())
            .select_from(Application)
            .where(Application.current_tier == app.current_tier)
        )
        or 0
    )

    if not aggregates:
        return {
            "application_id": app_id,
            "tier": app.current_tier,
            "peer_count": 0,
            "tier_app_count": tier_app_count,
            "available": False,
            "reason": "No peer aggregates available â€” admin must run /admin/refresh-peer-aggregates",
            "benchmarks": [],
        }

    # Get this app's latest reading per metric for comparison
    app_readings: dict[str, float] = {}
    for agg in aggregates:
        latest = await db.scalar(
            select(MetricReading.value)
            .where(
                MetricReading.application_id == app_id,
                MetricReading.metric_name    == agg.metric_name,
            )
            .order_by(MetricReading.collected_at.desc())
            .limit(1)
        )
        if latest is not None:
            app_readings[agg.metric_name] = latest

    benchmarks = []
    for agg in aggregates:
        app_value = app_readings.get(agg.metric_name)
        delta     = round(app_value - agg.avg_value, 6) if app_value is not None else None
        adoption_rate = (
            round((agg.peer_count or 0) / tier_app_count, 4)
            if tier_app_count > 0
            else None
        )
        benchmarks.append({
            "metric_name":  agg.metric_name,
            "peer_avg":     agg.avg_value,
            "app_value":    app_value,
            "delta":        delta,
            "peer_count":   agg.peer_count,
            "adoption_rate": adoption_rate,
            "popularity_stars": _to_popularity_stars(adoption_rate),
            "refreshed_at": agg.refreshed_at.isoformat(),
        })

    return {
        "application_id": app_id,
        "tier":           app.current_tier,
        "peer_count":     aggregates[0].peer_count if aggregates else 0,
        "tier_app_count": tier_app_count,
        "available":      True,
        "benchmarks":     benchmarks,
    }


@router.get("/applications/{app_id}/recommendations")
async def get_recommendations(app_id: str, db: AsyncSession = Depends(get_db)):
    """
    Recommend unadopted controls applicable to this app's tier and ai_system_type.
    Ranked by regulatory_density (number of requirements linked to each control).
    Falls back to catalog-based ranking when peer data is insufficient.
    """
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Get already-adopted control IDs
    adopted_result = await db.execute(
        select(ControlAssignment.control_id)
        .where(
            ControlAssignment.application_id == app_id,
            ControlAssignment.status         == "adopted",
        )
    )
    adopted_ids = {r[0] for r in adopted_result.fetchall()}

    # Get applicable controls for this tier (Foundation always, Common if tier>=Common, etc.)
    tier_priority = {"FOUNDATION": 0, "COMMON": 1, "SPECIALIZED": 2}
    app_tier_rank = tier_priority.get(
        (app.current_tier or "Foundation").upper(), 0
    )

    applicable_tiers = [t for t, rank in tier_priority.items() if rank <= app_tier_rank]

    controls_result = await db.execute(
        select(Control)
        .where(Control.tier.in_(applicable_tiers))
        .order_by(Control.code)
    )
    all_controls = controls_result.scalars().all()

    # Filter to unadopted only
    unadopted = [c for c in all_controls if c.id not in adopted_ids]

    if not unadopted:
        return {
            "application_id":   app_id,
            "tier":             app.current_tier,
            "recommendations":  [],
            "message":          "All applicable controls already adopted.",
        }

    # Score each unadopted control by regulatory density
    recommendations = []
    for control in unadopted:
        req_count = await db.scalar(
            select(func.count(ControlRequirement.requirement_id))
            .where(ControlRequirement.control_id == control.id)
        )
        recommendations.append({
            "control_id":          control.id,
            "code":                control.code,
            "title":               control.title,
            "domain":              control.domain,
            "tier":                control.tier,
            "measurement_mode":    getattr(control, "measurement_mode", None),
            "regulatory_density":  req_count or 0,
        })

    # Sort by regulatory density descending â€” most regulation-backed first
    recommendations.sort(key=lambda r: r["regulatory_density"], reverse=True)

    return {
        "application_id":  app_id,
        "tier":            app.current_tier,
        "total_applicable": len(all_controls),
        "already_adopted":  len(adopted_ids),
        "recommendations":  recommendations[:20],  # top 20
    }

