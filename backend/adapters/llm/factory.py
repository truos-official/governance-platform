import os

from .azure_openai import AzureOpenAIAdapter
from .base import LLMAdapter

_DEPLOYMENT = "aigov-gpt41"
_MINI_DEPLOYMENT = "aigov-gpt41-mini"


def get_llm_adapter() -> LLMAdapter:
    """Return an AzureOpenAIAdapter configured from environment variables.

    Required env vars:
      AZURE_OPENAI_ENDPOINT  — e.g. https://aigov-oai.openai.azure.com
      AZURE_OPENAI_API_KEY   — Azure OpenAI API key
    """
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")

    if not endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT environment variable is not set")
    if not api_key:
        raise ValueError("AZURE_OPENAI_API_KEY environment variable is not set")

    return AzureOpenAIAdapter(
        endpoint=endpoint,
        api_key=api_key,
        deployment=_DEPLOYMENT,
        mini_deployment=_MINI_DEPLOYMENT,
    )
