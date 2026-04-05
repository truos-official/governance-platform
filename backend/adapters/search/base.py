from abc import ABC, abstractmethod


class SearchAdapter(ABC):
    """Abstract base class for full-text and vector search backends."""

    @abstractmethod
    async def search(self, query: str, filters: dict | None, top: int) -> list[dict]:
        """Execute a search query and return ranked result documents."""

    @abstractmethod
    async def index_document(self, id: str, document: dict) -> bool:
        """Index or overwrite a document. Returns True on success."""

    @abstractmethod
    async def delete_document(self, id: str) -> bool:
        """Delete a document by ID. Returns True on success."""
