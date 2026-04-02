"""
KPI calculator — Phase 4.4/4.5.

Pull model: calculated on-demand when dashboard loads. Not pre-scheduled.

For each control assigned to an application:
  1. Identify linked KPI definition (control_metric_definition table)
  2. Pull latest metric_reading values from TimescaleDB hypertable
  3. Evaluate threshold and produce: PASS / FAIL / INSUFFICIENT_DATA
  4. Write to calculated_metric; propose control_calculation_proposal if manual

28 OTEL metrics span 8 groups (Section 10).
Only production-environment metrics are accepted.
"""


class KPICalculator:
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

    def calculate_for_application(self, app_id: str) -> list[dict]:
        """
        Phase 4.4.
        Returns list of {control_id, metric_name, result, value, threshold, evidence_ts}.
        """
        raise NotImplementedError("Phase 4.4")

    def _evaluate_metric(self, metric_name: str, value: float, threshold: dict) -> str:
        """Returns PASS / FAIL based on threshold definition."""
        raise NotImplementedError("Phase 4.4")
