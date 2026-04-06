from abc import ABC, abstractmethod


class SearchAdapter(ABC):
    """Abstract base class for full-text and vector search backends."""

    @abstractmethod
    async def search(
        self,
        query: str,
        filters: dict | None,
        top: int,
        *,
        skip: int = 0,
        order_by: list[str] | None = None,
        include_total_count: bool = False,
    ) -> tuple[list[dict], int | None]:
        """Execute a search query and return (documents, total_count)."""

    @abstractmethod
    async def index_document(self, id: str, document: dict) -> bool:
        """Index or overwrite a document. Returns True on success."""

    @abstractmethod
    async def delete_document(self, id: str) -> bool:
        """Delete a document by ID. Returns True on success."""
