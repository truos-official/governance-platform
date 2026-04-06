import inspect

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
        self,
        query: str,
        filters: dict | None,
        top: int,
        *,
        skip: int = 0,
        order_by: list[str] | None = None,
        include_total_count: bool = False,
    ) -> tuple[list[dict], int | None]:
        """Search index and return (documents, total_count)."""
        odata_filter: str | None = None
        if filters:
            clauses = [f"{k} eq '{v}'" for k, v in filters.items()]
            odata_filter = " and ".join(clauses)

        results: list[dict] = []
        total_count: int | None = None
        async with self._client:
            pager = await self._client.search(
                search_text=query,
                filter=odata_filter,
                top=top,
                skip=skip,
                order_by=order_by,
                include_total_count=include_total_count,
                select="*",
            )
            if include_total_count:
                maybe_count = pager.get_count()
                if inspect.isawaitable(maybe_count):
                    maybe_count = await maybe_count
                if maybe_count is not None:
                    total_count = int(maybe_count)

            async for result in pager:
                doc = dict(result)
                doc["id"] = result.get("id") or result.get("@search.score")
                doc["score"] = result.get("@search.score")
                results.append(doc)

        return results, total_count

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
