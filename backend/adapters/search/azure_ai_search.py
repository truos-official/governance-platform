from azure.core.credentials import AzureKeyCredential, TokenCredential
from azure.search.documents.aio import SearchClient

from .base import SearchAdapter


class AzureAISearchAdapter(SearchAdapter):
    """SearchAdapter implementation backed by Azure AI Search."""

    def __init__(
        self,
        endpoint: str,
        index_name: str,
        credential: AzureKeyCredential | TokenCredential,
    ) -> None:
        self._client = SearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=credential,
        )

    async def search(
        self, query: str, filters: dict | None, top: int
    ) -> list[dict]:
        """Search the index and return documents with id, score, and all fields."""
        odata_filter: str | None = None
        if filters:
            clauses = [f"{k} eq '{v}'" for k, v in filters.items()]
            odata_filter = " and ".join(clauses)

        results: list[dict] = []
        async with self._client:
            async for result in await self._client.search(
                search_text=query,
                filter=odata_filter,
                top=top,
                select="*",
            ):
                doc = dict(result)
                doc["id"] = result.get("id") or result.get("@search.score")
                doc["score"] = result.get("@search.score")
                results.append(doc)

        return results

    async def index_document(self, id: str, document: dict) -> bool:
        """Upload (upsert) a single document. Returns True if the operation succeeded."""
        async with self._client:
            results = await self._client.upload_documents(documents=[document])
        return results[0].succeeded

    async def delete_document(self, id: str) -> bool:
        """Delete a document by its id field. Returns True if the operation succeeded."""
        async with self._client:
            results = await self._client.delete_documents(documents=[{"id": id}])
        return results[0].succeeded
