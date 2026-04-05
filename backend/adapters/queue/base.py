from abc import ABC, abstractmethod


class QueueAdapter(ABC):
    """Abstract base class for message queue backends."""

    @abstractmethod
    async def send(self, queue_name: str, message: dict) -> bool:
        """Send a message to the named queue. Returns True on success."""

    @abstractmethod
    async def receive(self, queue_name: str, max_messages: int) -> list[dict]:
        """Receive up to max_messages messages from the named queue."""
