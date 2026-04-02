from abc import ABC, abstractmethod
from typing import Any


class SearchAdapter(ABC):
    """ABC for all search adapters. Phase 2 implements AzureAISearchAdapter."""

    @abstractmethod
    def hybrid_search(self, query: str, top: int = 10, filters: dict | None = None) -> list[dict]:
        """BM25 + vector + semantic ranker. Primary search path."""

    @abstractmethod
    def index_document(self, index: str, document: dict) -> None:
        """Upsert a single document into the named index."""

    @abstractmethod
    def delete_document(self, index: str, doc_id: str) -> None: ...


class AzureAISearchAdapter(SearchAdapter):
    """
    Hybrid BM25 + vector + semantic ranker against aigov-search (Central US, Basic SKU).
    Phase 2.5: define index schema.
    Phase 2.10-2.13: seed 59 controls + 140 requirements.
    """

    def __init__(self, endpoint: str, api_key: str, index_name: str = "governance-catalog"):
        # Phase 2: initialise azure-search-documents SearchClient
        self._endpoint = endpoint
        self._api_key = api_key
        self._index_name = index_name

    def hybrid_search(self, query: str, top: int = 10, filters: dict | None = None) -> list[dict]:
        raise NotImplementedError("Phase 2.5")

    def index_document(self, index: str, document: dict) -> None:
        raise NotImplementedError("Phase 2.10")

    def delete_document(self, index: str, doc_id: str) -> None:
        raise NotImplementedError("Phase 2")
