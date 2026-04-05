import os
from typing import Literal

from azure.identity import DefaultAzureCredential

from .azure_monitor import AzureMonitorAdapter
from .base import TelemetryAdapter
from .redis_adapter import RedisAdapter


def get_telemetry_adapter(
    source: Literal["azure_monitor", "redis"],
) -> TelemetryAdapter:
    """Return a TelemetryAdapter for the given source.

    source="azure_monitor":
      Required env vars: AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP
      Credentials resolved via DefaultAzureCredential.

    source="redis":
      Required env var: REDIS_URL — e.g. redis://:password@redis:6379/0
    """
    if source == "azure_monitor":
        subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        resource_group = os.getenv("AZURE_RESOURCE_GROUP")
        if not subscription_id:
            raise ValueError("AZURE_SUBSCRIPTION_ID environment variable is not set")
        if not resource_group:
            raise ValueError("AZURE_RESOURCE_GROUP environment variable is not set")
        return AzureMonitorAdapter(
            subscription_id=subscription_id,
            resource_group=resource_group,
            credential=DefaultAzureCredential(),
        )

    if source == "redis":
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise ValueError("REDIS_URL environment variable is not set")
        return RedisAdapter(connection_string=redis_url)

    raise ValueError(f"Unknown telemetry source: {source!r}. Expected 'azure_monitor' or 'redis'.")
