from abc import ABC, abstractmethod


class TelemetryAdapter(ABC):
    """Abstract base class for telemetry / metrics backends."""

    @abstractmethod
    async def get_metric(
        self,
        metric_name: str,
        application_id: str,
        period_days: int,
    ) -> float | None:
        """Return the aggregated value for a single metric, or None if no data."""

    @abstractmethod
    async def get_metrics(
        self,
        metric_names: list[str],
        application_id: str,
        period_days: int,
    ) -> dict[str, float]:
        """Return aggregated values for multiple metrics keyed by metric name."""
