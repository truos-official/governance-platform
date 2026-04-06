"""
Governance Event Collector - Phase 4.

Receives OTEL events tagged as governance.* events (Group 8)
and processes them independently from the general metrics pipeline.

Phase 4.2 will implement:
  1. Event schema validation
  2. Service Bus publish
  3. Tier recalculation trigger for governance.risk.event
  4. Forwarding to backend /api/v1/telemetry/ingest
"""
from __future__ import annotations

import logging
import signal
import time
from threading import Event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GOVERNANCE_EVENTS = {
    "governance.oversight.override",
    "governance.appeal.submitted",
    "governance.appeal.resolved",
    "governance.fairness.test_result",
    "governance.risk.event",
}

REQUIRED_EVENT_ATTRIBUTES = [
    "governance.application_id",
    "governance.division",
    "service.name",
    "deployment.environment",
]

_shutdown = Event()


def _handle_shutdown(signum: int, _frame) -> None:
    logger.info("Shutdown signal received (%s).", signum)
    _shutdown.set()


def validate_event(event: dict) -> tuple[bool, list[str]]:
    """
    Validate a governance event against the contract.
    Returns (is_valid, list_of_missing_fields).
    Phase 4.2.
    """
    raise NotImplementedError("Phase 4.2")


def route_event(event: dict) -> None:
    """
    Route a validated governance event.
    Phase 4.2.
    """
    raise NotImplementedError("Phase 4.2")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    logger.info("Governance Event Collector starting - Phase 4 stub")
    logger.info("Listening for governance.* OTEL events")

    # Keep the stub container running until Phase 4 logic is implemented.
    while not _shutdown.is_set():
        time.sleep(5)

    logger.info("Governance Event Collector stopped")
