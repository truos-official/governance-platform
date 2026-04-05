from openai import AsyncOpenAI

from .base import LLMAdapter

_EMBEDDING_MODEL = "text-embedding-3-large"


class AzureOpenAIAdapter(LLMAdapter):
    """LLMAdapter implementation backed by Azure OpenAI (AsyncOpenAI v1 API)."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        mini_deployment: str,
    ) -> None:
        self._client = AsyncOpenAI(
            base_url=f"{endpoint.rstrip('/')}/openai/v1/",
            api_key=api_key,
        )
        self._deployment = deployment
        self._mini_deployment = mini_deployment

    async def complete(
        self,
        prompt: str,
        system: str | None,
        max_tokens: int,
        use_mini: bool = False,
    ) -> str:
        """Return a chat completion. Uses mini_deployment if use_mini=True."""
        messages: list[dict[str, str]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        model = self._mini_deployment if use_mini else self._deployment
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    async def embed(self, text: str) -> list[float]:
        """Return a vector embedding using text-embedding-3-large."""
        response = await self._client.embeddings.create(
            model=_EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding
