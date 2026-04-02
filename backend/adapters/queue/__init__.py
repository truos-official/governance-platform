from abc import ABC, abstractmethod
from typing import Any, Callable


class QueueAdapter(ABC):
    """ABC for message queue adapters."""

    @abstractmethod
    def send(self, queue: str, message: dict) -> None: ...

    @abstractmethod
    def receive(self, queue: str, max_messages: int = 10) -> list[dict]: ...

    @abstractmethod
    def complete_message(self, message_id: str) -> None: ...


class ServiceBusAdapter(QueueAdapter):
    """
    Azure Service Bus Basic tier — aigov-bus (eastus).
    Primary queue: governance-events.
    Phase 2.8: implement full adapter.
    NOTE: Service Bus not yet provisioned (Phase 1 Step B).
    """

    GOVERNANCE_EVENTS_QUEUE = "governance-events"

    def __init__(self, connection_string: str):
        # Phase 2: initialise azure-servicebus ServiceBusClient
        self._connection_string = connection_string

    def send(self, queue: str, message: dict) -> None:
        raise NotImplementedError("Phase 2.8 — aigov-bus not yet provisioned")

    def receive(self, queue: str, max_messages: int = 10) -> list[dict]:
        raise NotImplementedError("Phase 2.8")

    def complete_message(self, message_id: str) -> None:
        raise NotImplementedError("Phase 2.8")
