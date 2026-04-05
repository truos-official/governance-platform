import json

from azure.servicebus import ServiceBusMessage
from azure.servicebus.aio import ServiceBusClient

from .base import QueueAdapter


class ServiceBusAdapter(QueueAdapter):
    """QueueAdapter implementation backed by Azure Service Bus."""

    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def send(self, queue_name: str, message: dict) -> bool:
        """Serialise message as JSON and send it to the named queue."""
        async with ServiceBusClient.from_connection_string(self._connection_string) as client:
            async with client.get_queue_sender(queue_name) as sender:
                await sender.send_messages(ServiceBusMessage(json.dumps(message)))
        return True

    async def receive(self, queue_name: str, max_messages: int) -> list[dict]:
        """Receive up to max_messages messages, complete each, and return parsed bodies."""
        results: list[dict] = []
        async with ServiceBusClient.from_connection_string(self._connection_string) as client:
            async with client.get_queue_receiver(queue_name) as receiver:
                messages = await receiver.receive_messages(
                    max_message_count=max_messages,
                    max_wait_time=5,
                )
                for msg in messages:
                    body = b"".join(msg.body)
                    results.append(json.loads(body))
                    await receiver.complete_message(msg)
        return results
