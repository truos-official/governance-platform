"""
MCP server - 11 tools - Phase 3.

Server name: ai-governance
Auth: Azure Entra ID OAuth2 client_credentials, scope: governance.read
Base URL: https://{governance-api-host}/mcp

Catalog tools (5):
  search_controls, get_control_detail, get_requirement_detail,
  list_controls_by_domain, get_interpretation_tree

Peer intelligence tools (6):
  get_peer_benchmarks, get_alignment_score, get_risk_tier,
  get_recommended_controls, get_gap_analysis, get_compliance_trend

Phase 3 implementation. Adapters injected from adapters/search and adapters/graph.
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import bindparam, text


class GovernanceMCPServer:
    """
    Exposes the governance catalog and peer intelligence to external agents.
    Connected via MCP protocol - not a REST API.
    """

    TIER_ORDER = ("LOW", "MEDIUM", "HIGH")
    DOMAIN_FLOOR = {
        "healthcare": "MEDIUM",
        "criminal_justice": "HIGH",
        "financial": "MEDIUM",
    }
    PEER_WEIGHT = 0.50
    REG_DENSITY_WEIGHT = 0.30
    TREND_VELOCITY_WEIGHT = 0.20

    def __init__(self, search_adapter, graph_adapter, db_session):
        self._search = search_adapter
        self._graph = graph_adapter
        self._db = db_session

    def _normalize_tier(self, tier: str | None) -> str:
        candidate = str(tier or "LOW").upper()
        return candidate if candidate in self.TIER_ORDER else "LOW"

    def _effective_tier(self, raw_tier: str | None, domain: str | None) -> tuple[str, str | None]:
        normalized_raw = self._normalize_tier(raw_tier)
        domain_floor = self.DOMAIN_FLOOR.get((domain or "").lower()) if domain else None
        if not domain_floor:
            return normalized_raw, None
        tier_index = {tier: i for i, tier in enumerate(self.TIER_ORDER)}
        effective = self.TIER_ORDER[max(tier_index[normalized_raw], tier_index[domain_floor])]
        return effective, domain_floor

    async def _get_application_profile(self, app_id: str) -> dict:
        result = await self._db.execute(
            text(
                """
                SELECT
                    a.id::text AS app_id,
                    a.domain AS domain,
                    tce.new_tier AS new_tier
                FROM application a
                LEFT JOIN LATERAL (
                    SELECT t.new_tier
                    FROM tier_change_event t
                    WHERE t.application_id = a.id
                    ORDER BY t.changed_at DESC
                    LIMIT 1
                ) tce ON TRUE
                WHERE a.id::text = :app_id
                """
            ),
            {"app_id": app_id},
        )
        row = result.mappings().first()
        if row is None:
            raise LookupError("Application not found")

        raw_tier = self._normalize_tier(row.get("new_tier"))
        effective_tier, domain_floor = self._effective_tier(
            raw_tier=raw_tier,
            domain=row.get("domain"),
        )
        return {
            "app_id": row.get("app_id"),
            "domain": row.get("domain"),
            "tier_raw": raw_tier,
            "tier_effective": effective_tier,
            "domain_floor": domain_floor,
        }

    async def _get_peer_ids_for_tier(self, app_id: str, target_tier: str) -> list[str]:
        result = await self._db.execute(
            text(
                """
                SELECT
                    a.id::text AS app_id,
                    a.domain AS domain,
                    tce.new_tier AS new_tier
                FROM application a
                LEFT JOIN LATERAL (
                    SELECT t.new_tier
                    FROM tier_change_event t
                    WHERE t.application_id = a.id
                    ORDER BY t.changed_at DESC
                    LIMIT 1
                ) tce ON TRUE
                WHERE a.id::text <> :app_id
                """
            ),
            {"app_id": app_id},
        )

        peer_ids: list[str] = []
        for row in result.mappings().all():
            peer_tier, _ = self._effective_tier(
                raw_tier=row.get("new_tier"),
                domain=row.get("domain"),
            )
            if peer_tier == target_tier:
                peer_ids.append(str(row["app_id"]))
        return peer_ids

    async def _get_latest_metric_snapshot(self, app_ids: list[str]) -> dict[str, dict[str, float]]:
        if not app_ids:
            return {}

        query = text(
            """
            SELECT DISTINCT ON (mr.application_id::text, mr.metric_name)
                mr.application_id::text AS app_id,
                mr.metric_name AS metric_name,
                mr.value AS value
            FROM metric_reading mr
            WHERE mr.application_id::text IN :app_ids
            ORDER BY mr.application_id::text, mr.metric_name, mr.collected_at DESC
            """
        ).bindparams(bindparam("app_ids", expanding=True))

        result = await self._db.execute(query, {"app_ids": app_ids})
        by_metric: dict[str, dict[str, float]] = defaultdict(dict)
        for row in result.mappings().all():
            row_app_id = row.get("app_id")
            metric_name = row.get("metric_name")
            value = row.get("value")
            if row_app_id is None or metric_name is None or value is None:
                continue
            by_metric[str(metric_name)][str(row_app_id)] = float(value)
        return by_metric

    def _build_metric_percentiles(
        self,
        app_id: str,
        by_metric: dict[str, dict[str, float]],
    ) -> list[dict]:
        metrics: list[dict] = []
        for metric_name in sorted(by_metric):
            app_values = by_metric[metric_name]
            if app_id not in app_values:
                continue

            target_value = app_values[app_id]
            peer_values = [v for pid, v in app_values.items() if pid != app_id]
            if not peer_values:
                continue

            all_values = [target_value, *peer_values]
            rank = sum(1 for v in all_values if v <= target_value)
            percentile = round((rank / len(all_values)) * 100.0, 2)
            peer_average = round(sum(peer_values) / len(peer_values), 6)

            metrics.append(
                {
                    "metric_name": metric_name,
                    "app_value": target_value,
                    "peer_average": peer_average,
                    "percentile": percentile,
                    "sample_size": len(all_values),
                }
            )
        return metrics

    # ------------------------------------------------------------------
    # Catalog tools
    # ------------------------------------------------------------------

    async def search_controls(
        self,
        query: str,
        domain: str | None = None,
        top: int = 10,
    ) -> list[dict]:
        """Hybrid BM25 + vector + semantic search across catalog controls."""
        effective_top = max(1, min(top, 100))
        filters: dict[str, str] = {"type": "control"}
        if domain:
            filters["domain"] = domain

        rows, _ = await self._search.search(
            query=query,
            filters=filters,
            top=effective_top,
        )
        return [
            {
                "id": row.get("id"),
                "code": row.get("code"),
                "title": row.get("title"),
                "description": row.get("description"),
                "domain": row.get("domain"),
                "tier": row.get("tier"),
                "measurement_mode": row.get("measurement_mode"),
                "score": row.get("score"),
            }
            for row in rows
        ]

    async def get_control_detail(self, control_id: str) -> dict:
        """Full control detail including KPI definitions and tier."""
        control_result = await self._db.execute(
            text(
                """
                SELECT
                    c.id::text AS id,
                    c.code AS code,
                    c.title AS title,
                    c.description AS description,
                    c.domain AS domain,
                    c.tier::text AS tier,
                    c.is_foundation AS is_foundation,
                    c.measurement_mode::text AS measurement_mode
                FROM control c
                WHERE c.id::text = :control_id
                """
            ),
            {"control_id": control_id},
        )
        control = control_result.mappings().first()
        if control is None:
            raise LookupError("Control not found")

        metric_result = await self._db.execute(
            text(
                """
                SELECT
                    cmd.id::text AS id,
                    cmd.metric_name AS metric_name,
                    cmd.threshold AS threshold,
                    cmd.is_manual AS is_manual
                FROM control_metric_definition cmd
                WHERE cmd.control_id::text = :control_id
                ORDER BY cmd.metric_name
                """
            ),
            {"control_id": control_id},
        )
        metrics = [dict(row) for row in metric_result.mappings().all()]

        requirement_result = await self._db.execute(
            text(
                """
                SELECT
                    r.id::text AS id,
                    r.code AS code,
                    r.title AS title,
                    r.category AS category
                FROM control_requirement cr
                JOIN requirement r ON r.id = cr.requirement_id
                WHERE cr.control_id::text = :control_id
                ORDER BY r.code
                """
            ),
            {"control_id": control_id},
        )
        requirements = [dict(row) for row in requirement_result.mappings().all()]

        detail = dict(control)
        detail["metrics"] = metrics
        detail["requirements"] = requirements
        return detail

    async def get_requirement_detail(self, requirement_id: str) -> dict:
        """Requirement detail with 3-layer interpretation tree."""
        requirement_result = await self._db.execute(
            text(
                """
                SELECT
                    r.id::text AS id,
                    r.regulation_id::text AS regulation_id,
                    reg.title AS regulation_title,
                    reg.jurisdiction AS jurisdiction,
                    r.code AS code,
                    r.title AS title,
                    r.description AS description,
                    r.category AS category
                FROM requirement r
                LEFT JOIN regulation reg ON reg.id = r.regulation_id
                WHERE r.id::text = :requirement_id
                """
            ),
            {"requirement_id": requirement_id},
        )
        requirement = requirement_result.mappings().first()
        if requirement is None:
            raise LookupError("Requirement not found")

        control_result = await self._db.execute(
            text(
                """
                SELECT
                    c.id::text AS id,
                    c.code AS code,
                    c.title AS title,
                    c.domain AS domain,
                    c.tier::text AS tier
                FROM control_requirement cr
                JOIN control c ON c.id = cr.control_id
                WHERE cr.requirement_id::text = :requirement_id
                ORDER BY c.code
                """
            ),
            {"requirement_id": requirement_id},
        )
        controls = [dict(row) for row in control_result.mappings().all()]
        interpretation_tree = await self.get_interpretation_tree(requirement_id)

        detail = dict(requirement)
        detail["controls"] = controls
        detail["interpretation_tree"] = interpretation_tree
        return detail

    async def list_controls_by_domain(self, domain: str) -> list[dict]:
        """
        List controls for a domain.
        Domains: RM, RO, LC, SE, OM, AA, GL, CO (13 total).
        """
        result = await self._db.execute(
            text(
                """
                SELECT
                    c.id::text AS id,
                    c.code AS code,
                    c.title AS title,
                    c.description AS description,
                    c.domain AS domain,
                    c.tier::text AS tier,
                    c.is_foundation AS is_foundation,
                    c.measurement_mode::text AS measurement_mode
                FROM control c
                WHERE LOWER(c.domain) = LOWER(:domain)
                ORDER BY c.code
                """
            ),
            {"domain": domain},
        )
        return [dict(row) for row in result.mappings().all()]

    async def get_interpretation_tree(self, requirement_id: str) -> dict:
        """
        Returns {source: ..., system: ..., user: ...} 3-layer interpretation.
        Source = regulatory text, System = platform interpretation, User = org override.
        """
        result = await self._db.execute(
            text(
                """
                SELECT
                    ri.id::text AS id,
                    ri.requirement_id::text AS requirement_id,
                    ri.layer::text AS layer,
                    ri.content AS content,
                    ri.version AS version,
                    ri.created_at AS created_at
                FROM risk_interpretation ri
                WHERE ri.requirement_id::text = :requirement_id
                ORDER BY
                    ri.layer::text,
                    ri.version DESC NULLS LAST,
                    ri.created_at DESC NULLS LAST
                """
            ),
            {"requirement_id": requirement_id},
        )

        layers: dict[str, list[dict]] = defaultdict(list)
        for row in result.mappings().all():
            created_at = row.get("created_at")
            layers[(row.get("layer") or "UNKNOWN").lower()].append(
                {
                    "id": row.get("id"),
                    "content": row.get("content"),
                    "version": row.get("version"),
                    "created_at": (
                        created_at.isoformat()
                        if isinstance(created_at, datetime)
                        else created_at
                    ),
                }
            )

        return {
            "requirement_id": requirement_id,
            "source": layers.get("source", []),
            "system": layers.get("system", []),
            "user": layers.get("user", []),
        }

    # ------------------------------------------------------------------
    # Peer intelligence tools
    # ------------------------------------------------------------------

    async def get_peer_benchmarks(self, app_id: str) -> dict:
        """
        Peer benchmarks for same risk tier (minimum N=3 peers).
        Returns per-metric percentile positions.
        """
        profile = await self._get_application_profile(app_id)
        target_tier = profile["tier_effective"]
        peer_ids = await self._get_peer_ids_for_tier(app_id, target_tier)
        peer_count = len(peer_ids)
        if peer_count < 3:
            raise ValueError("Insufficient peers: minimum 3 peers required")

        by_metric = await self._get_latest_metric_snapshot([app_id, *peer_ids])
        metrics = self._build_metric_percentiles(app_id=app_id, by_metric=by_metric)

        return {
            "app_id": app_id,
            "tier": target_tier,
            "peer_count": peer_count,
            "metrics": metrics,
        }

    async def get_alignment_score(self, app_id: str) -> dict:
        """
        Alignment score breakdown.
        Formula: peer*0.50 + reg_density*0.30 + trend_velocity*0.20
        """
        profile = await self._get_application_profile(app_id)
        target_tier = profile["tier_effective"]
        peer_ids = await self._get_peer_ids_for_tier(app_id, target_tier)
        if len(peer_ids) < 3:
            raise ValueError("Insufficient peers: minimum 3 peers required")

        by_metric = await self._get_latest_metric_snapshot([app_id, *peer_ids])
        percentile_rows = self._build_metric_percentiles(app_id=app_id, by_metric=by_metric)
        if percentile_rows:
            peer_score = round(
                sum(row["percentile"] / 100.0 for row in percentile_rows) / len(percentile_rows),
                6,
            )
        else:
            peer_score = 0.0

        control_count_query = text(
            """
            SELECT
                cm.application_id::text AS app_id,
                COUNT(DISTINCT cm.control_id)::int AS control_count
            FROM calculated_metric cm
            WHERE cm.application_id::text IN :app_ids
            GROUP BY cm.application_id::text
            """
        ).bindparams(bindparam("app_ids", expanding=True))
        control_count_result = await self._db.execute(
            control_count_query,
            {"app_ids": [app_id, *peer_ids]},
        )
        control_counts = {
            str(row["app_id"]): int(row.get("control_count") or 0)
            for row in control_count_result.mappings().all()
        }
        app_control_count = control_counts.get(app_id, 0)
        peer_control_values = [control_counts.get(pid, 0) for pid in peer_ids]
        peer_avg_controls = (
            sum(peer_control_values) / len(peer_control_values)
            if peer_control_values
            else 0.0
        )
        if peer_avg_controls <= 0:
            reg_density = 0.0
        else:
            reg_density = round(
                max(0.0, min(app_control_count / peer_avg_controls, 1.0)),
                6,
            )

        trend_result = await self._db.execute(
            text(
                """
                SELECT
                    COALESCE(
                        AVG(
                            CASE
                                WHEN cm.result::text = 'PASS' THEN 1.0
                                WHEN cm.result::text = 'FAIL' THEN 0.0
                                ELSE NULL
                            END
                        ) FILTER (
                            WHERE cm.calculated_at >= NOW() - make_interval(days => 30)
                        ),
                        0.0
                    ) AS current_pass_rate,
                    COALESCE(
                        AVG(
                            CASE
                                WHEN cm.result::text = 'PASS' THEN 1.0
                                WHEN cm.result::text = 'FAIL' THEN 0.0
                                ELSE NULL
                            END
                        ) FILTER (
                            WHERE cm.calculated_at >= NOW() - make_interval(days => 60)
                              AND cm.calculated_at < NOW() - make_interval(days => 30)
                        ),
                        0.0
                    ) AS previous_pass_rate
                FROM calculated_metric cm
                WHERE cm.application_id::text = :app_id
                """
            ),
            {"app_id": app_id},
        )
        trend_row = trend_result.mappings().first() or {}
        current_pass_rate = float(trend_row.get("current_pass_rate") or 0.0)
        previous_pass_rate = float(trend_row.get("previous_pass_rate") or 0.0)
        trend_delta = round(current_pass_rate - previous_pass_rate, 6)
        trend_velocity = round(max(0.0, min((trend_delta + 1.0) / 2.0, 1.0)), 6)

        score = round(
            (peer_score * self.PEER_WEIGHT)
            + (reg_density * self.REG_DENSITY_WEIGHT)
            + (trend_velocity * self.TREND_VELOCITY_WEIGHT),
            6,
        )

        return {
            "app_id": app_id,
            "tier": target_tier,
            "peer_count": len(peer_ids),
            "score": score,
            "formula": "peer*0.50 + reg_density*0.30 + trend_velocity*0.20",
            "components": {
                "peer_score": peer_score,
                "reg_density": reg_density,
                "trend_velocity": trend_velocity,
                "trend_delta": trend_delta,
                "current_pass_rate": round(current_pass_rate, 6),
                "previous_pass_rate": round(previous_pass_rate, 6),
            },
        }

    async def get_risk_tier(self, app_id: str) -> dict:
        """Current risk tier with NIST score + domain floor applied."""
        app_result = await self._db.execute(
            text(
                """
                SELECT
                    a.id::text AS id,
                    a.domain AS domain
                FROM application a
                WHERE a.id::text = :app_id
                """
            ),
            {"app_id": app_id},
        )
        app_row = app_result.mappings().first()
        if app_row is None:
            raise LookupError("Application not found")

        tier_result = await self._db.execute(
            text(
                """
                SELECT
                    tce.new_tier AS new_tier,
                    tce.changed_at AS changed_at
                FROM tier_change_event tce
                WHERE tce.application_id::text = :app_id
                ORDER BY tce.changed_at DESC
                LIMIT 1
                """
            ),
            {"app_id": app_id},
        )
        tier_row = tier_result.mappings().first()

        raw_tier = self._normalize_tier(tier_row.get("new_tier") if tier_row is not None else None)
        source = "tier_change_event" if tier_row is not None else "default_low_no_events"

        domain = app_row.get("domain")
        effective_tier, domain_floor = self._effective_tier(raw_tier=raw_tier, domain=domain)

        changed_at = tier_row.get("changed_at") if tier_row is not None else None
        if isinstance(changed_at, datetime):
            changed_at = changed_at.isoformat()

        return {
            "app_id": app_id,
            "domain": domain,
            "tier_raw": raw_tier,
            "tier_effective": effective_tier,
            "domain_floor": domain_floor,
            "last_changed_at": changed_at,
            "source": source,
        }

    async def get_recommended_controls(self, app_id: str) -> list[dict]:
        """Controls recommended based on gap analysis + peer benchmarks."""
        gaps = await self.get_gap_analysis(app_id)
        if not gaps:
            return []

        peer_metric_map: dict[str, dict] = {}
        peer_count = 0
        try:
            benchmarks = await self.get_peer_benchmarks(app_id)
            peer_count = int(benchmarks.get("peer_count") or 0)
            for metric in benchmarks.get("metrics", []):
                metric_name = metric.get("metric_name")
                if metric_name:
                    peer_metric_map[str(metric_name)] = metric
        except ValueError:
            # Recommendations can still be produced from direct gap evidence.
            peer_count = 0

        grouped: dict[str, dict] = {}
        for gap in gaps:
            control_id = str(gap.get("control_id") or "")
            if not control_id:
                continue

            item = grouped.setdefault(
                control_id,
                {
                    "control_id": gap.get("control_id"),
                    "control_code": gap.get("control_code"),
                    "control_title": gap.get("control_title"),
                    "domain": gap.get("domain"),
                    "tier": gap.get("tier"),
                    "measurement_mode": gap.get("measurement_mode"),
                    "priority": "MEDIUM",
                    "severity_score": 0,
                    "reasons": [],
                    "metric_gaps": [],
                },
            )

            metric_name = str(gap.get("metric_name") or "")
            benchmark = peer_metric_map.get(metric_name)
            peer_percentile = (
                float(benchmark["percentile"])
                if benchmark is not None and benchmark.get("percentile") is not None
                else None
            )

            result = str(gap.get("result") or "").upper()
            if result == "FAIL":
                item["severity_score"] += 2
                item["priority"] = "HIGH"
            elif result == "INSUFFICIENT_DATA":
                item["severity_score"] += 1

            if peer_percentile is not None and peer_percentile < 50.0:
                item["severity_score"] += 1

            item["metric_gaps"].append(
                {
                    "metric_name": metric_name,
                    "result": result,
                    "gap_type": gap.get("gap_type"),
                    "value": gap.get("value"),
                    "calculated_at": gap.get("calculated_at"),
                    "peer_percentile": peer_percentile,
                    "peer_average": benchmark.get("peer_average") if benchmark else None,
                }
            )

        recommendations: list[dict] = []
        for control_id, item in grouped.items():
            metric_gaps = item["metric_gaps"]
            has_fail = any(mg.get("result") == "FAIL" for mg in metric_gaps)
            has_insufficient = any(mg.get("result") == "INSUFFICIENT_DATA" for mg in metric_gaps)
            has_peer_lag = any(
                (mg.get("peer_percentile") is not None and mg["peer_percentile"] < 50.0)
                for mg in metric_gaps
            )

            reasons: list[str] = []
            actions: list[str] = []
            if has_fail:
                reasons.append("Control has KPI failures against threshold.")
                actions.append("Prioritize remediation for failing KPI metrics.")
            if has_insufficient:
                reasons.append("Control has insufficient evidence to determine compliance.")
                if str(item.get("measurement_mode") or "").lower() == "manual":
                    actions.append("Submit manual evidence or approve a control calculation proposal.")
                else:
                    actions.append("Improve telemetry coverage for required KPI metrics.")
            if has_peer_lag:
                reasons.append("Application trails peers on one or more related metrics.")
                actions.append("Adopt peer-proven mitigation patterns for lagging metrics.")
            if not actions:
                actions.append("Review control implementation and monitor trend.")

            recommendations.append(
                {
                    "control_id": control_id,
                    "control_code": item.get("control_code"),
                    "control_title": item.get("control_title"),
                    "domain": item.get("domain"),
                    "tier": item.get("tier"),
                    "measurement_mode": item.get("measurement_mode"),
                    "priority": item.get("priority"),
                    "severity_score": item.get("severity_score"),
                    "peer_count": peer_count,
                    "reason": " ".join(reasons),
                    "recommended_actions": actions,
                    "metric_gaps": metric_gaps,
                }
            )

        recommendations.sort(
            key=lambda rec: (
                0 if rec.get("priority") == "HIGH" else 1,
                -int(rec.get("severity_score") or 0),
                str(rec.get("control_code") or ""),
            )
        )
        return recommendations

    async def get_gap_analysis(self, app_id: str) -> list[dict]:
        """Controls assigned but failing or with insufficient data."""
        await self._get_application_profile(app_id)

        latest_query = text(
            """
            SELECT DISTINCT ON (cm.control_id::text, cm.metric_name)
                c.id::text AS control_id,
                c.code AS control_code,
                c.title AS control_title,
                c.domain AS domain,
                c.tier::text AS control_tier,
                c.measurement_mode::text AS measurement_mode,
                cm.metric_name AS metric_name,
                cm.result::text AS result,
                cm.value AS value,
                cm.calculated_at AS calculated_at
            FROM calculated_metric cm
            JOIN control c ON c.id = cm.control_id
            WHERE cm.application_id::text = :app_id
            ORDER BY cm.control_id::text, cm.metric_name, cm.calculated_at DESC
            """
        )
        latest_result = await self._db.execute(latest_query, {"app_id": app_id})
        latest_rows = latest_result.mappings().all()

        gaps: list[dict] = []
        for row in latest_rows:
            status = str(row.get("result") or "").upper()
            if status not in {"FAIL", "INSUFFICIENT_DATA"}:
                continue

            calculated_at = row.get("calculated_at")
            if isinstance(calculated_at, datetime):
                calculated_at = calculated_at.isoformat()

            gaps.append(
                {
                    "control_id": row.get("control_id"),
                    "control_code": row.get("control_code"),
                    "control_title": row.get("control_title"),
                    "domain": row.get("domain"),
                    "tier": row.get("control_tier"),
                    "measurement_mode": row.get("measurement_mode"),
                    "metric_name": row.get("metric_name"),
                    "result": status,
                    "value": row.get("value"),
                    "calculated_at": calculated_at,
                    "gap_type": "threshold_breach" if status == "FAIL" else "insufficient_data",
                    "priority": "HIGH" if status == "FAIL" else "MEDIUM",
                }
            )

        gaps.sort(
            key=lambda item: (
                0 if item["result"] == "FAIL" else 1,
                str(item.get("control_code") or ""),
                str(item.get("metric_name") or ""),
            )
        )
        return gaps

    async def get_compliance_trend(self, app_id: str, window_days: int = 30) -> list[dict]:
        """Rolling compliance trend from metric_reading hypertable."""
        await self._get_application_profile(app_id)

        effective_window = max(1, min(window_days, 365))
        trend_query = text(
            """
            WITH days AS (
                SELECT generate_series(
                    date_trunc('day', NOW() - make_interval(days => :window_days - 1)),
                    date_trunc('day', NOW()),
                    interval '1 day'
                )::date AS day
            ),
            daily AS (
                SELECT
                    date_trunc('day', cm.calculated_at)::date AS day,
                    COUNT(*) FILTER (WHERE cm.result::text = 'PASS')::int AS pass_count,
                    COUNT(*) FILTER (WHERE cm.result::text = 'FAIL')::int AS fail_count,
                    COUNT(*) FILTER (WHERE cm.result::text = 'INSUFFICIENT_DATA')::int AS insufficient_count,
                    COUNT(*) FILTER (WHERE cm.result::text IN ('PASS', 'FAIL'))::int AS evaluated_count
                FROM calculated_metric cm
                WHERE cm.application_id::text = :app_id
                  AND cm.calculated_at >= NOW() - make_interval(days => :window_days)
                GROUP BY date_trunc('day', cm.calculated_at)::date
            )
            SELECT
                d.day::text AS day,
                COALESCE(di.pass_count, 0) AS pass_count,
                COALESCE(di.fail_count, 0) AS fail_count,
                COALESCE(di.insufficient_count, 0) AS insufficient_count,
                COALESCE(di.evaluated_count, 0) AS evaluated_count,
                CASE
                    WHEN COALESCE(di.evaluated_count, 0) = 0 THEN NULL
                    ELSE ROUND((di.pass_count::numeric / di.evaluated_count::numeric), 6)
                END AS compliance_rate
            FROM days d
            LEFT JOIN daily di ON di.day = d.day
            ORDER BY d.day ASC
            """
        )
        result = await self._db.execute(
            trend_query,
            {"app_id": app_id, "window_days": effective_window},
        )

        points: list[dict] = []
        for row in result.mappings().all():
            compliance_rate = row.get("compliance_rate")
            if compliance_rate is not None:
                compliance_rate = float(compliance_rate)

            points.append(
                {
                    "day": row.get("day"),
                    "pass_count": int(row.get("pass_count") or 0),
                    "fail_count": int(row.get("fail_count") or 0),
                    "insufficient_count": int(row.get("insufficient_count") or 0),
                    "evaluated_count": int(row.get("evaluated_count") or 0),
                    "compliance_rate": compliance_rate,
                }
            )
        return points
