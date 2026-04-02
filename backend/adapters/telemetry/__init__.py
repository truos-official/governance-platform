from abc import ABC, abstractmethod
from typing import Any


class TelemetryAdapter(ABC):
    """
    ABC for telemetry adapters.
    Platform uses Azure AI Foundry for observability — NOT LangSmith.
    All OTEL metrics must carry mandatory resource attributes:
      service.name, service.version, deployment.environment,
      governance.application_id, governance.division.
    Platform ONLY ingests metrics where deployment.environment == 'production'.
    """

    @abstractmethod
    def emit_metric(self, name: str, value: float, attributes: dict) -> None: ...

    @abstractmethod
    def emit_event(self, name: str, attributes: dict) -> None: ...

    @abstractmethod
    def flush(self) -> None: ...


class AzureFoundryTelemetryAdapter(TelemetryAdapter):
    """
    Routes telemetry to Azure AI Foundry project: aigov-foundry-project.
    Phase 2.9: implement all telemetry source adapters.
    """

    MANDATORY_RESOURCE_ATTRIBUTES = [
        "service.name",
        "service.version",
        "deployment.environment",
        "governance.application_id",
        "governance.division",
    ]

    def __init__(self, connection_string: str):
        self._connection_string = connection_string

    def emit_metric(self, name: str, value: float, attributes: dict) -> None:
        raise NotImplementedError("Phase 2.9")

    def emit_event(self, name: str, attributes: dict) -> None:
        raise NotImplementedError("Phase 2.9")

    def flush(self) -> None:
        raise NotImplementedError("Phase 2.9")
