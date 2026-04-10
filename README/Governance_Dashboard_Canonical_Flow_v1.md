# Governance Dashboard Canonical Flow v2 (Stack-Aligned)

Status: Phase 3 baseline for Phase 5 implementation.
Last validated: April 9, 2026.

## 0) Lifecycle Context
- Current lifecycle phase: Phase 3 hardening / Phase 5 UX alignment prep.
- Purpose of this doc: lock user flow to what is implemented now, while defining exact target behavior.

## 1) Solution Stack and Resources (Current)

### Application stack
- Frontend: React 18 + Vite (`frontend`)
- Backend API: FastAPI (Python 3.11) (`backend`)
- Database: PostgreSQL 16 (`aigov`) with pgvector and Timescale patterns
- Cache: Redis 7
- Telemetry: OpenTelemetry Collector + governance-event-collector

### Local runtime services (docker-compose)
- `backend` on `:8000`
- `postgres` on `:5432`
- `redis` on `:6379`
- `otel-collector` on `:4317/:4318`
- `governance-event-collector` on `:8001`

### Azure resources referenced in current config
- Key Vault: `aigov-kv`
- Azure OpenAI endpoint: `aigov-openai-dev` (deployments: `aigov-gpt41`, `aigov-gpt41-mini`)
- Azure Search: `aigov-search`
- GraphDB endpoint: `aigov-graphdb-vm` (`172.210.64.73:7200`)
- Service Bus target: `aigov-bus` (not fully provisioned in current local workflow)

### Auth/roles posture
- Product model uses roles: `admin`, `analyst`, `viewer`.
- Current API wiring is role-aware by design, but strict end-to-end enforcement is still a hardening item.

## 2) Live Data Inventory (Current DB Snapshot)
As of April 9, 2026:
- applications: 2
- controls: 59
- requirements: 140
- regulations: 13
- control-requirement links: 435
- metric definitions: 40
- risk definitions: 8
- interpretations: 4
- application requirement scope rows: 0 (currently no saved scope at capture time)
- tier change events: 4
- metric readings: 11

## 3) Canonical User Flow
1. User signs in (role context loaded).
2. User opens **Applications** to view connected apps.
3. User connects via wizard or disconnects an existing app.
4. User opens **Dashboards** (rename from "Risks & Controls").
5. User selects one application and works through 9-step governance pipeline.
6. Every step must be application-specific and tied to that app's telemetry + requirement scope + controls.

## 4) Current Runtime Step Mapping (What works now)
- Step 1 Use Case: app profile/ownership summary.
- Step 2 Risk Classification: tier score + dimensions + floor rule.
- Step 3 Technical Architecture: catalog controls + recommendations.
- Step 4 Data Readiness: compliance evidence + requirement scope editor + interpretation editor.
- Step 5 Data Integration: telemetry pipeline health/status.
- Step 6 Security: scoped compliance summary and control evidence.
- Step 7 Infrastructure: peer benchmark comparisons.
- Step 8 Solution Design: alignment score and weights.
- Step 9 System Performance: tier history + recommendations.

## 5) Target Step Mapping (Product Intent)

### Step 1 - Use Case
- Telemetry/admin app KPIs + operational profile.

### Step 2 - Risk Classification (two-part)
- Part A: risk/tier explanation in plain English.
- Part B: regulation/rule/control curation (search/select/add scope, interpretations, control measures).
- Secretariat defaults shown at top; app owner can add additional applicable items.

### Step 3-9
- Each step displays controls/measures relevant to that governance domain.
- For each measure, show:
  - measured value,
  - plain-English interpretation,
  - peer benchmark delta (above/below/near peers).

## 6) Non-Negotiable Rules
- Dashboard is always per-application.
- Requirement scope controls downstream KPI evaluation when scope is active.
- Custom user interpretation is allowed; metric calculation logic remains tied to approved metric definitions.
- Peer comparison is a core feature, not optional decoration.

## 7) Implementation Gaps to Close Next
1. IA finalization: complete tab rename/consolidation to **Dashboards**.
2. Move Step 2 Part B curation UX from current Step 4 placement into Step 2.
3. Enforce strict step-domain mapping for 3-9 with explicit control tagging/routing.
4. Ensure each displayed metric has plain-English interpretation + peer delta in every step.
5. Complete role enforcement path (frontend and API) for admin-only actions.
