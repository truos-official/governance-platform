import redis.asyncio as aioredis

from .base import TelemetryAdapter


class RedisAdapter(TelemetryAdapter):
    """TelemetryAdapter implementation backed by Redis INFO stats."""

    def __init__(self, connection_string: str) -> None:
        self._client: aioredis.Redis = aioredis.from_url(connection_string, decode_responses=True)

    async def get_metric(
        self,
        metric_name: str,
        application_id: str,
        period_days: int,
    ) -> float | None:
        """Return a Redis INFO stat mapped from metric_name, or None if unavailable."""
        info: dict = await self._client.info()

        match metric_name:
            case "cache_hit_rate":
                hits = float(info.get("keyspace_hits", 0))
                misses = float(info.get("keyspace_misses", 0))
                total = hits + misses
                return hits / total if total > 0 else None
            case "connected_clients":
                return float(info.get("connected_clients", 0))
            case "memory_used":
                return float(info.get("used_memory", 0))
            case "uptime_days":
                uptime_seconds = float(info.get("uptime_in_seconds", 0))
                return uptime_seconds / 86400
            case _:
                return None

    async def get_metrics(
        self,
        metric_names: list[str],
        application_id: str,
        period_days: int,
    ) -> dict[str, float]:
        """Return stats for multiple metric names, omitting those with no data."""
        results: dict[str, float] = {}
        for name in metric_names:
            value = await self.get_metric(name, application_id, period_days)
            if value is not None:
                results[name] = value
        return results
