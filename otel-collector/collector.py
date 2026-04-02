"""
OTEL Collector integration — Phase 4.

In local dev, the otel-collector service runs the official
otel/opentelemetry-collector-contrib image with otel-config.yaml mounted.

This module is a Phase 4 extension point for custom Python processing
before metrics reach the FastAPI ingest endpoint — e.g.:
  - Enriching metrics with application metadata from PostgreSQL
  - Computing derived metrics not emitted by source apps
  - Validating the 28-metric contract (Section 10)

Phase 4.2: implement metric validation and enrichment pipeline.
"""

# 28 mandatory metrics across 8 groups (Section 10, all prefixed ai.*)
MANDATORY_METRICS = {
    "core": [
        "ai.model.error_rate",
        "ai.model.latency_p95",
        "ai.logs.coverage_rate",
        "ai.logs.retention_days",
        "ai.transparency.disclosure_rate",
        "ai.monitoring.coverage",
        "ai.access.mfa_coverage",
        "ai.access.failed_auth_rate",
    ],
    "llm_quality": [
        "ai.model.accuracy",
        "ai.model.hallucination_rate",
        "ai.model.drift_score",
        "ai.explain.coverage_rate",
    ],
    "fairness": [
        "ai.fairness.demographic_parity",
        "ai.fairness.equal_opportunity",
    ],
    "human_oversight": [
        "ai.oversight.override_rate",
        "ai.oversight.review_rate",
    ],
    "appeals": [
        "ai.appeals.rate",
        "ai.appeals.resolution_time",
    ],
    "security": [
        "ai.security.vuln_open_critical",
        "ai.data.encryption_coverage",
        "ai.data.dlp_incident_rate",
    ],
    "privacy": [
        "ai.privacy.dsr_response_time",
        "ai.privacy.consent_rate",
    ],
}

# Governance events (Group 8) — processed by governance-event-collector
GOVERNANCE_EVENTS = [
    "governance.oversight.override",
    "governance.appeal.submitted",
    "governance.appeal.resolved",
    "governance.fairness.test_result",
    "governance.risk.event",
]

MANDATORY_RESOURCE_ATTRIBUTES = [
    "service.name",
    "service.version",
    "deployment.environment",
    "governance.application_id",
    "governance.division",
]
