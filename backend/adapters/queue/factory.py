import os

from .base import QueueAdapter
from .service_bus import ServiceBusAdapter


def get_queue_adapter() -> QueueAdapter:
    """Return a ServiceBusAdapter configured from environment variables.

    Required env vars:
      SERVICE_BUS_CONNECTION_STRING — Azure Service Bus connection string
    """
    connection_string = os.getenv("SERVICE_BUS_CONNECTION_STRING")
    if not connection_string:
        raise ValueError("SERVICE_BUS_CONNECTION_STRING environment variable is not set")
    return ServiceBusAdapter(connection_string=connection_string)
