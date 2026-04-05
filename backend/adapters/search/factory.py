import os

from azure.core.credentials import AzureKeyCredential

from .azure_ai_search import AzureAISearchAdapter
from .base import SearchAdapter


def get_search_adapter(index_name: str) -> SearchAdapter:
    """Return an AzureAISearchAdapter configured from environment variables.

    Required env vars:
      AZURE_SEARCH_ENDPOINT  — e.g. https://aigov-search.search.windows.net
      AZURE_SEARCH_KEY       — Admin or query API key
    """
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    key = os.getenv("AZURE_SEARCH_KEY")

    if not endpoint:
        raise ValueError("AZURE_SEARCH_ENDPOINT environment variable is not set")
    if not key:
        raise ValueError("AZURE_SEARCH_KEY environment variable is not set")

    return AzureAISearchAdapter(
        endpoint=endpoint,
        index_name=index_name,
        credential=AzureKeyCredential(key),
    )
