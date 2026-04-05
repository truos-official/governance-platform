from datetime import timedelta, timezone, datetime

from azure.monitor.query.aio import MetricsQueryClient
from azure.monitor.query import MetricAggregationType

from .base import TelemetryAdapter

# Maps platform-neutral metric names to Azure Monitor metric names
_METRIC_MAP: dict[str, str] = {
    "ai.model.error_rate": "Percentage Errors",
    "ai.model.latency":    "ServerLatency",
    "ai.model.requests":   "TotalRequests",
    "cpu_percent":         "Percentage CPU",
    "memory_percent":      "Available Memory Bytes",
}


class AzureMonitorAdapter(TelemetryAdapter):
    """TelemetryAdapter implementation backed by Azure Monitor Metrics."""

    def __init__(
        self,
        subscription_id: str,
        resource_group: str,
        credential: object,
    ) -> None:
        self._subscription_id = subscription_id
        self._resource_group = resource_group
        self._client = MetricsQueryClient(credential)  # type: ignore[arg-type]

    def _resource_uri(self, application_id: str) -> str:
        return (
            f"/subscriptions/{self._subscription_id}"
            f"/resourceGroups/{self._resource_group}"
            f"/providers/Microsoft.Insights/components/{application_id}"
        )

    async def get_metric(
        self,
        metric_name: str,
        application_id: str,
        period_days: int,
    ) -> float | None:
        """Query Azure Monitor for a single metric and return its average, or None."""
        az_metric = _METRIC_MAP.get(metric_name, metric_name)
        end = datetime.now(tz=timezone.utc)
        start = end - timedelta(days=period_days)

        response = await self._client.query_resource(
            self._resource_uri(application_id),
            metric_names=[az_metric],
            timespan=(start, end),
            granularity=timedelta(days=period_days),
            aggregations=[MetricAggregationType.AVERAGE],
        )

        for metric in response.metrics:
            for ts in metric.timeseries:
                for dp in ts.data:
                    if dp.average is not None:
                        return dp.average
        return None

    async def get_metrics(
        self,
        metric_names: list[str],
        application_id: str,
        period_days: int,
    ) -> dict[str, float]:
        """Return aggregated values for multiple metrics, omitting those with no data."""
        results: dict[str, float] = {}
        for name in metric_names:
            value = await self.get_metric(name, application_id, period_days)
            if value is not None:
                results[name] = value
        return results
