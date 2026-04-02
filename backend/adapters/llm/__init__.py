from abc import ABC, abstractmethod
from typing import Iterator


class LLMAdapter(ABC):
    """ABC for LLM adapters."""

    @abstractmethod
    def complete(self, messages: list[dict], model: str | None = None, **kwargs) -> str: ...

    @abstractmethod
    def complete_stream(self, messages: list[dict], **kwargs) -> Iterator[str]: ...

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...


class AzureOpenAIAdapter(LLMAdapter):
    """
    Points to aigov-openai-dev (eastus, S0).
    Default deployment: aigov-gpt41 (gpt-4.1, 150K TPM).
    Cost-sensitive paths use aigov-gpt41-mini (gpt-4.1-mini, 250K TPM).
    Do NOT use gpt-4o — deployments are gpt-4.1 only per handoff v2 Section 15.
    Observability: Azure AI Foundry (NOT LangSmith).
    """

    DEFAULT_DEPLOYMENT = "aigov-gpt41"
    MINI_DEPLOYMENT = "aigov-gpt41-mini"

    def __init__(self, endpoint: str, api_key: str, deployment: str = DEFAULT_DEPLOYMENT):
        # Phase 2: initialise openai.AzureOpenAI client with azure-identity
        self._endpoint = endpoint
        self._deployment = deployment

    def complete(self, messages: list[dict], model: str | None = None, **kwargs) -> str:
        raise NotImplementedError("Phase 2.6")

    def complete_stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
        raise NotImplementedError("Phase 2.6")

    def embed(self, text: str) -> list[float]:
        raise NotImplementedError("Phase 2.6")
