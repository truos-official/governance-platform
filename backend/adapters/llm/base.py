from abc import ABC, abstractmethod


class LLMAdapter(ABC):
    """Abstract base class for large language model backends."""

    @abstractmethod
    async def complete(self, prompt: str, system: str | None, max_tokens: int) -> str:
        """Generate a text completion for the given prompt."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return a vector embedding for the given text."""
