"""
Risk tier engine — Phase 4.3.

Scoring:
  NIST RMF base score (weighted sum of 8 core metrics from Group 1, Section 10)
  + domain floor rule (some domains have a minimum tier regardless of score)

Three tiers: LOW / MEDIUM / HIGH.
Tier changes are immutable — written to tier_change_event table.
KPI is calculated on-demand (pull model, not scheduled).

Inputs come from metric_reading (TimescaleDB hypertable).
"""


class TierEngine:
    TIERS = ("LOW", "MEDIUM", "HIGH")

    # Domain floor rules: certain domains cannot be below a minimum tier
    DOMAIN_FLOOR = {
        "healthcare": "MEDIUM",
        "criminal_justice": "HIGH",
        "financial": "MEDIUM",
    }

    def calculate_tier(self, app_id: str, metrics: dict) -> str:
        """
        Phase 4.3.
        Returns one of: LOW, MEDIUM, HIGH.
        Writes immutable tier_change_event if tier has changed.
        """
        raise NotImplementedError("Phase 4.3")

    def _nist_score(self, metrics: dict) -> float:
        """Weighted sum of 8 mandatory core metrics (Group 1)."""
        raise NotImplementedError("Phase 4.3")

    def _apply_domain_floor(self, raw_tier: str, domain: str) -> str:
        floor = self.DOMAIN_FLOOR.get(domain)
        if floor is None:
            return raw_tier
        tier_index = {t: i for i, t in enumerate(self.TIERS)}
        return self.TIERS[max(tier_index[raw_tier], tier_index[floor])]
