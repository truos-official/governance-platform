# AI Governance Platform — Roadmap

## Phase 5 — Frontend (IN PROGRESS)
Full platform UI: Governance tab (9-step pipeline), Applications tab,
Risks & Controls tab, Admin tab with Technical Documentation shell.

## Phase 6 — Demo App Integration Track
Runs after Phase 5 is complete and deployed.

### Track A — Clone and Strip Demo App
- Clone governance-demo-agentic → new repo: governance-agent-demo
- Strip to Agent tab only (QueryTab.js + 3 backend endpoints)
- Rewrite App.js — single tab, no auth, simplified header
- Add governance platform link to QueryTab footer

### Track B — OTEL Instrumentation
- Write src/otel_emitter.py
- Emit 6 governance metrics per /query call
- Add GOVERNANCE_APPLICATION_ID / GOVERNANCE_COLLECTOR_URL / GOVERNANCE_DIVISION env vars

### Track C — Local Integration Test
- Register demo app → get application_id
- Set env var, start demo app locally
- Fire 5 test queries, verify MetricReading rows appear
- Verify tier recalculation, compliance updates, alignment score

### Track D — Production Deployment (isolated)
- New Azure resource group: agent-demo-rg
- Backend: Azure Container Apps (separate from aigov-cae)
- Frontend: Azure Static Web Apps (separate domain)
- Point GOVERNANCE_COLLECTOR_URL at prod aigov-platform collector
- Register demo app in production governance platform

### Track E — Client Onboarding Documentation
- Developer Integration Guide updated with demo app as reference implementation
- Process documented: register → instrument → verify → disconnect

## Phase 7 — Hardening
Security, auth scope enforcement, observability, performance, DR patterns.

## Phase 8 — Release Readiness
Final QA, acceptance tests, deployment runbook, production cutover.
