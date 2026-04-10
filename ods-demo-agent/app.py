from __future__ import annotations

import math
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator

app = FastAPI(title="ODS Demo Agent", version="0.2.0")

GOVERNANCE_BACKEND_URL = os.getenv("GOVERNANCE_BACKEND_URL", "http://backend:8000").rstrip("/")
GOVERNANCE_TELEMETRY_ENDPOINT = os.getenv(
    "GOVERNANCE_TELEMETRY_ENDPOINT",
    f"{GOVERNANCE_BACKEND_URL}/api/v1/telemetry/ingest",
)
GOVERNANCE_APPLICATION_ID = os.getenv("GOVERNANCE_APPLICATION_ID", "").strip()
GOVERNANCE_APPLICATION_NAME = os.getenv("GOVERNANCE_APPLICATION_NAME", "ODS Demo Agent").strip()
GOVERNANCE_DIVISION = os.getenv("GOVERNANCE_DIVISION", "unassigned").strip() or "unassigned"
DEPLOYMENT_ENVIRONMENT = os.getenv("DEPLOYMENT_ENVIRONMENT", "production").strip() or "production"

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "aigov-gpt41-mini").strip()

MODEL_INPUT_COST_PER_1K = float(os.getenv("MODEL_INPUT_COST_PER_1K", "0.0008"))
MODEL_OUTPUT_COST_PER_1K = float(os.getenv("MODEL_OUTPUT_COST_PER_1K", "0.0032"))
ACTIVE_USER_WINDOW_MINUTES = int(os.getenv("ACTIVE_USER_WINDOW_MINUTES", "30"))
MAX_TRACKED_RESPONSES = int(os.getenv("MAX_TRACKED_RESPONSES", "400"))

KNOWN_FRONTIER_MODEL_TOKENS = (
    "gpt-5",
    "gpt-4.1",
    "gpt-4o",
    "claude-opus",
    "claude-3.7",
    "gemini-1.5-pro",
    "gemini-2.0",
)

RETRIEVAL_KB = [
    {
        "title": "UN AI Ethics Principles",
        "url": "https://unsceb.org/principles-for-the-ethical-use-of-artificial-intelligence-in-the-un-system",
        "snippet": "AI systems should preserve human rights, accountability, safety, transparency, and oversight.",
        "keywords": ["ethics", "oversight", "rights", "transparency", "accountability"],
    },
    {
        "title": "UN Model Policy for Responsible AI",
        "url": "https://www.unsceb.org/content/un-system-framework-model-policy-responsible-use-artificial-intelligence",
        "snippet": "Organizations should define governance roles, risk controls, and continuous monitoring for AI deployments.",
        "keywords": ["governance", "risk", "monitoring", "policy", "responsible"],
    },
    {
        "title": "RAG Safety Guidance",
        "url": "https://learn.microsoft.com/azure/ai-services/openai/concepts/use-your-data",
        "snippet": "Grounding generated responses in retrieved documents improves traceability and reduces hallucinations.",
        "keywords": ["rag", "retrieval", "citation", "grounding", "hallucination"],
    },
]

_openai_client_instance: AsyncOpenAI | None = None
_cached_application_id: str | None = None
_user_last_seen: dict[str, datetime] = {}
_response_store: dict[str, dict[str, Any]] = {}
_response_order: list[str] = []
_feedback_totals: dict[str, dict[str, int]] = {}


class QueryRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    user_id: str | None = Field(default=None, max_length=200)


class CitationItem(BaseModel):
    title: str
    url: str
    snippet: str


class QueryResponse(BaseModel):
    response_id: str
    answer: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    retrieval_latency_ms: float
    citations: list[CitationItem]
    telemetry_sent: bool


class FeedbackRequest(BaseModel):
    response_id: str = Field(..., min_length=1, max_length=120)
    feedback: str = Field(..., description="up or down")
    user_id: str | None = Field(default=None, max_length=200)

    @field_validator("feedback")
    @classmethod
    def validate_feedback(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"up", "down"}:
            raise ValueError("feedback must be 'up' or 'down'")
        return normalized


class FeedbackResponse(BaseModel):
    response_id: str
    feedback: str
    feedback_positive_rate: float
    total_feedback_count: int
    telemetry_sent: bool


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config")
async def config() -> dict[str, str]:
    return {
        "governance_backend_url": GOVERNANCE_BACKEND_URL,
        "telemetry_endpoint": GOVERNANCE_TELEMETRY_ENDPOINT,
        "application_name": GOVERNANCE_APPLICATION_NAME,
        "deployment_environment": DEPLOYMENT_ENVIRONMENT,
    }


def _ns_now() -> str:
    return str(int(time.time() * 1_000_000_000))


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _fallback_answer(prompt: str) -> str:
    condensed = " ".join(prompt.strip().split())
    if not condensed:
        return "No prompt provided."
    preview = condensed[:220]
    return (
        "Fallback response (local runtime mode): "
        f"{preview}. Governance telemetry still captured from this live request."
    )


def _looks_frontier(model_name: str) -> bool:
    lowered = (model_name or "").lower()
    return any(token in lowered for token in KNOWN_FRONTIER_MODEL_TOKENS)


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if token}


def _retrieve_citations(prompt: str) -> tuple[list[dict[str, str]], float]:
    started = time.perf_counter()
    prompt_terms = _tokenize(prompt)

    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in RETRIEVAL_KB:
        score = 0
        for kw in entry["keywords"]:
            if kw.lower() in prompt_terms:
                score += 2
        if any(term in entry["snippet"].lower() for term in prompt_terms):
            score += 1
        scored.append((score, entry))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [item[1] for item in scored if item[0] > 0][:3]
    if not selected:
        selected = [entry for _, entry in scored[:2]]

    latency_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
    citations = [
        {
            "title": item["title"],
            "url": item["url"],
            "snippet": item["snippet"],
        }
        for item in selected
    ]
    return citations, latency_ms


def _build_rag_prompt(prompt: str, citations: list[dict[str, str]]) -> str:
    if not citations:
        return prompt
    sources = "\n".join(
        f"- {c['title']}: {c['snippet']} ({c['url']})"
        for c in citations
    )
    return (
        "Answer the user question using the source excerpts when relevant. "
        "If a claim relies on a source, keep it grounded.\n\n"
        f"User question:\n{prompt}\n\n"
        f"Retrieved sources:\n{sources}"
    )


def _append_sources(answer: str, citations: list[dict[str, str]]) -> str:
    if not citations:
        return answer
    source_lines = "\n".join(f"- {c['title']}" for c in citations)
    return f"{answer}\n\nSources:\n{source_lines}"


def _estimate_claim_count(answer: str) -> int:
    sentences = [segment.strip() for segment in re.split(r"[.!?]+", answer) if segment.strip()]
    return max(1, len(sentences))


def _citation_coverage(answer: str, citations: list[dict[str, str]]) -> tuple[float, int, int]:
    total_claims = _estimate_claim_count(answer)
    cited_claims = total_claims if citations else 0
    ratio = cited_claims / total_claims if total_claims > 0 else 0.0
    return ratio, cited_claims, total_claims


def _record_response(response_id: str, payload: dict[str, Any]) -> None:
    _response_store[response_id] = payload
    _response_order.append(response_id)

    while len(_response_order) > MAX_TRACKED_RESPONSES:
        oldest_id = _response_order.pop(0)
        _response_store.pop(oldest_id, None)


def _active_user_count(user_id: str) -> int:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=ACTIVE_USER_WINDOW_MINUTES)

    stale = [uid for uid, ts in _user_last_seen.items() if ts < cutoff]
    for uid in stale:
        _user_last_seen.pop(uid, None)

    _user_last_seen[user_id] = now
    return len(_user_last_seen)


def _feedback_counter(app_id: str) -> dict[str, int]:
    if app_id not in _feedback_totals:
        _feedback_totals[app_id] = {"up": 0, "down": 0}
    return _feedback_totals[app_id]


def _otel_attr(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        val = {"boolValue": value}
    elif isinstance(value, int):
        val = {"intValue": value}
    elif isinstance(value, float):
        val = {"doubleValue": value}
    else:
        val = {"stringValue": str(value)}
    return {"key": key, "value": val}


def _gauge_metric(name: str, value: float | int, attrs: dict[str, Any]) -> dict[str, Any]:
    point: dict[str, Any] = {
        "timeUnixNano": _ns_now(),
        "attributes": [_otel_attr(k, v) for k, v in attrs.items()],
    }
    if isinstance(value, int):
        point["asInt"] = value
    else:
        point["asDouble"] = float(value)
    return {"name": name, "gauge": {"dataPoints": [point]}}


def _resource_attributes(application_id: str) -> list[dict[str, Any]]:
    return [
        _otel_attr("service.name", "ods-demo-agent"),
        _otel_attr("service.version", "0.2.0"),
        _otel_attr("deployment.environment", DEPLOYMENT_ENVIRONMENT),
        _otel_attr("governance.application_id", application_id),
        _otel_attr("governance.division", GOVERNANCE_DIVISION),
    ]


async def _resolve_application_id() -> str:
    global _cached_application_id

    if GOVERNANCE_APPLICATION_ID:
        return GOVERNANCE_APPLICATION_ID
    if _cached_application_id:
        return _cached_application_id

    apps_url = f"{GOVERNANCE_BACKEND_URL}/api/v1/applications"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(apps_url)
    response.raise_for_status()

    payload = response.json()
    apps = payload if isinstance(payload, list) else [payload]
    for item in apps:
        name = str(item.get("name", "")).strip().lower()
        if name == GOVERNANCE_APPLICATION_NAME.lower():
            _cached_application_id = str(item["id"])
            return _cached_application_id

    raise HTTPException(
        status_code=404,
        detail=(
            f"Application '{GOVERNANCE_APPLICATION_NAME}' not found in governance backend. "
            "Set GOVERNANCE_APPLICATION_ID explicitly or register the app first."
        ),
    )


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client_instance
    if _openai_client_instance is None:
        if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
            raise HTTPException(
                status_code=500,
                detail="AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set for live model telemetry.",
            )
        _openai_client_instance = AsyncOpenAI(
            base_url=f"{AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/v1/",
            api_key=AZURE_OPENAI_API_KEY,
        )
    return _openai_client_instance


async def _run_model(prompt: str) -> tuple[str, str, int, int]:
    client = _get_openai_client()
    response = await client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "You are ODS Demo Agent. Respond concisely and clearly."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=700,
    )

    content = (response.choices[0].message.content or "").strip()
    usage = response.usage

    prompt_tokens = int(usage.prompt_tokens) if usage and usage.prompt_tokens is not None else _estimate_tokens(prompt)
    completion_tokens = int(usage.completion_tokens) if usage and usage.completion_tokens is not None else _estimate_tokens(content)

    model_name = response.model or AZURE_OPENAI_DEPLOYMENT
    return content, model_name, prompt_tokens, completion_tokens


async def _emit_query_telemetry(
    *,
    application_id: str,
    response_id: str,
    user_id: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    estimated_cost_usd: float,
    active_users: int,
    model_latency_ms: float,
    retrieval_latency_ms: float,
    citation_coverage: float,
    cited_claims: int,
    total_claims: int,
    citation_count: int,
) -> None:
    is_frontier = _looks_frontier(model_name)

    metric_attrs_common = {
        "response_id": response_id,
        "model.name": model_name,
        "user_id": user_id,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "total_cost_usd": estimated_cost_usd,
        "is_frontier_model": is_frontier,
    }

    payload = {
        "resourceMetrics": [
            {
                "resource": {"attributes": _resource_attributes(application_id)},
                "scopeMetrics": [
                    {
                        "scope": {"name": "ods-demo-agent", "version": "0.2.0"},
                        "metrics": [
                            _gauge_metric("ai.resources.token_usage", total_tokens, metric_attrs_common),
                            _gauge_metric("ai.resources.compute_cost", estimated_cost_usd, metric_attrs_common),
                            _gauge_metric(
                                "ai.resources.active_users",
                                active_users,
                                {"active_users": active_users, "user_id": user_id, "response_id": response_id},
                            ),
                            _gauge_metric(
                                "ai.model.latency_p95",
                                model_latency_ms,
                                {"model.name": model_name, "user_id": user_id, "response_id": response_id},
                            ),
                            _gauge_metric(
                                "ai.rag.retrieval_latency_p95",
                                retrieval_latency_ms,
                                {
                                    "response_id": response_id,
                                    "model.name": model_name,
                                    "user_id": user_id,
                                    "retrieval_latency_ms": retrieval_latency_ms,
                                },
                            ),
                            _gauge_metric(
                                "ai.rag.citation_coverage",
                                citation_coverage,
                                {
                                    "response_id": response_id,
                                    "model.name": model_name,
                                    "user_id": user_id,
                                    "cited_claims": cited_claims,
                                    "total_claims": total_claims,
                                    "citation_count": citation_count,
                                },
                            ),
                        ],
                    }
                ],
            }
        ]
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(GOVERNANCE_TELEMETRY_ENDPOINT, json=payload)
    response.raise_for_status()


async def _emit_feedback_telemetry(
    *,
    application_id: str,
    response_id: str,
    user_id: str,
    model_name: str,
    feedback: str,
    thumbs_up: int,
    thumbs_down: int,
    feedback_positive_rate: float,
    total_feedback_count: int,
) -> None:
    payload = {
        "resourceMetrics": [
            {
                "resource": {"attributes": _resource_attributes(application_id)},
                "scopeMetrics": [
                    {
                        "scope": {"name": "ods-demo-agent", "version": "0.2.0"},
                        "metrics": [
                            _gauge_metric(
                                "ai.oversight.feedback_positive_rate",
                                feedback_positive_rate,
                                {
                                    "response_id": response_id,
                                    "user_id": user_id,
                                    "model.name": model_name,
                                    "feedback": feedback,
                                    "thumbs_up": thumbs_up,
                                    "thumbs_down": thumbs_down,
                                    "total_feedback": total_feedback_count,
                                },
                            )
                        ],
                    }
                ],
            }
        ]
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(GOVERNANCE_TELEMETRY_ENDPOINT, json=payload)
    response.raise_for_status()


@app.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest) -> QueryResponse:
    request_started = time.perf_counter()

    app_id = await _resolve_application_id()
    user_id = (body.user_id or "anonymous").strip() or "anonymous"

    citations, retrieval_latency_ms = _retrieve_citations(body.prompt)
    rag_prompt = _build_rag_prompt(body.prompt, citations)

    try:
        answer, model_name, prompt_tokens, completion_tokens = await _run_model(rag_prompt)
    except Exception:
        answer = _fallback_answer(body.prompt)
        model_name = "local-fallback"
        prompt_tokens = _estimate_tokens(rag_prompt)
        completion_tokens = _estimate_tokens(answer)

    answer = _append_sources(answer, citations)
    total_tokens = int(prompt_tokens + completion_tokens)

    estimated_input_cost = (prompt_tokens / 1000.0) * MODEL_INPUT_COST_PER_1K
    estimated_output_cost = (completion_tokens / 1000.0) * MODEL_OUTPUT_COST_PER_1K
    estimated_cost_usd = round(estimated_input_cost + estimated_output_cost, 6)

    active_users = _active_user_count(user_id)
    model_latency_ms = max(0.0, (time.perf_counter() - request_started) * 1000.0)
    citation_coverage, cited_claims, total_claims = _citation_coverage(answer, citations)

    response_id = str(uuid4())
    _record_response(
        response_id,
        {
            "application_id": app_id,
            "user_id": user_id,
            "model_name": model_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    try:
        await _emit_query_telemetry(
            application_id=app_id,
            response_id=response_id,
            user_id=user_id,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            active_users=active_users,
            model_latency_ms=model_latency_ms,
            retrieval_latency_ms=retrieval_latency_ms,
            citation_coverage=citation_coverage,
            cited_claims=cited_claims,
            total_claims=total_claims,
            citation_count=len(citations),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Telemetry emit failed: {exc}") from exc

    return QueryResponse(
        response_id=response_id,
        answer=answer,
        model=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost_usd,
        retrieval_latency_ms=retrieval_latency_ms,
        citations=[CitationItem(**item) for item in citations],
        telemetry_sent=True,
    )


@app.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(body: FeedbackRequest) -> FeedbackResponse:
    record = _response_store.get(body.response_id)
    if not record:
        raise HTTPException(status_code=404, detail="response_id not found; submit feedback for a recent query response")

    app_id = str(record["application_id"])
    user_id = (body.user_id or record.get("user_id") or "anonymous").strip() or "anonymous"
    model_name = str(record.get("model_name") or "unknown-model")

    counters = _feedback_counter(app_id)
    counters[body.feedback] += 1
    thumbs_up = int(counters.get("up", 0))
    thumbs_down = int(counters.get("down", 0))
    total_feedback_count = thumbs_up + thumbs_down
    feedback_positive_rate = (thumbs_up / total_feedback_count) if total_feedback_count > 0 else 0.0

    try:
        await _emit_feedback_telemetry(
            application_id=app_id,
            response_id=body.response_id,
            user_id=user_id,
            model_name=model_name,
            feedback=body.feedback,
            thumbs_up=thumbs_up,
            thumbs_down=thumbs_down,
            feedback_positive_rate=feedback_positive_rate,
            total_feedback_count=total_feedback_count,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Feedback telemetry emit failed: {exc}") from exc

    return FeedbackResponse(
        response_id=body.response_id,
        feedback=body.feedback,
        feedback_positive_rate=feedback_positive_rate,
        total_feedback_count=total_feedback_count,
        telemetry_sent=True,
    )
