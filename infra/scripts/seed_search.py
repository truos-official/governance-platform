"""
Create and seed Azure AI Search index for the governance catalog.

Creates/updates index: governance-catalog
Seeds documents from local Postgres tables:
  - control
  - requirement (joined to regulation)

Run:
  python infra/scripts/seed_search.py

Environment variables:
  AZURE_SEARCH_ENDPOINT   required (for example https://aigov-search.search.windows.net)
  AZURE_SEARCH_KEY        required (admin key)
  AZURE_SEARCH_INDEX      optional, default: governance-catalog
  DATABASE_URL            optional, default: postgresql+asyncpg://aigov:localdev@localhost:5432/aigov
"""
from __future__ import annotations

import asyncio
import os
from typing import Iterable

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DEFAULT_DB_URL = "postgresql+asyncpg://aigov:localdev@localhost:5432/aigov"
DEFAULT_INDEX_NAME = "governance-catalog"
BATCH_SIZE = 500


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _build_index(index_name: str) -> SearchIndex:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, sortable=True),
        SearchableField(name="code", type=SearchFieldDataType.String, filterable=True, facetable=True, sortable=True),
        SearchableField(name="title", type=SearchFieldDataType.String, filterable=False, sortable=False),
        SearchableField(name="description", type=SearchFieldDataType.String, filterable=False, sortable=False),
        SimpleField(name="type", type=SearchFieldDataType.String, filterable=True, facetable=True, sortable=True),
        SimpleField(name="domain", type=SearchFieldDataType.String, filterable=True, facetable=True, sortable=True),
        SimpleField(name="tier", type=SearchFieldDataType.String, filterable=True, facetable=True, sortable=True),
        SimpleField(name="measurement_mode", type=SearchFieldDataType.String, filterable=True, facetable=True, sortable=True),
        SearchableField(name="source", type=SearchFieldDataType.String, filterable=True, facetable=True, sortable=True),
        SimpleField(name="jurisdiction", type=SearchFieldDataType.String, filterable=True, facetable=True, sortable=True),
    ]

    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name="governance-semantic",
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    content_fields=[SemanticField(field_name="description")],
                    keywords_fields=[SemanticField(field_name="code"), SemanticField(field_name="source")],
                ),
            )
        ]
    )

    return SearchIndex(name=index_name, fields=fields, semantic_search=semantic_search)


def _chunked(items: list[dict], size: int) -> Iterable[list[dict]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


async def _load_documents(db_url: str) -> list[dict]:
    engine = create_async_engine(db_url, echo=False)
    query = text(
        """
        SELECT
            'control_' || c.id::text AS id,
            c.code AS code,
            c.title AS title,
            c.description AS description,
            'control' AS type,
            c.domain AS domain,
            c.tier::text AS tier,
            c.measurement_mode::text AS measurement_mode,
            'UN_AI_Governance_Dataset_v2.xlsx' AS source,
            NULL::text AS jurisdiction
        FROM control c

        UNION ALL

        SELECT
            'requirement_' || r.id::text AS id,
            r.code AS code,
            r.title AS title,
            r.description AS description,
            'requirement' AS type,
            NULL::text AS domain,
            NULL::text AS tier,
            NULL::text AS measurement_mode,
            COALESCE(r.category, 'unknown') AS source,
            reg.jurisdiction AS jurisdiction
        FROM requirement r
        LEFT JOIN regulation reg ON reg.id = r.regulation_id
        ORDER BY type, code
        """
    )

    async with engine.connect() as conn:
        result = await conn.execute(query)
        rows = result.mappings().all()

    await engine.dispose()

    documents: list[dict] = []
    for row in rows:
        documents.append(
            {
                "id": row["id"],
                "code": row["code"],
                "title": row["title"] or "",
                "description": row["description"] or "",
                "type": row["type"],
                "domain": row["domain"],
                "tier": row["tier"],
                "measurement_mode": row["measurement_mode"],
                "source": row["source"] or "unknown",
                "jurisdiction": row["jurisdiction"],
            }
        )

    return documents


def main() -> None:
    search_endpoint = _required_env("AZURE_SEARCH_ENDPOINT")
    search_key = _required_env("AZURE_SEARCH_KEY")
    index_name = os.getenv("AZURE_SEARCH_INDEX", DEFAULT_INDEX_NAME).strip() or DEFAULT_INDEX_NAME
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL).strip() or DEFAULT_DB_URL

    print(f"\nPreparing Azure AI Search index: {index_name}")
    print(f"Search endpoint: {search_endpoint}")

    credential = AzureKeyCredential(search_key)
    index_client = SearchIndexClient(endpoint=search_endpoint, credential=credential)
    index = _build_index(index_name)
    index_client.create_or_update_index(index)
    print("Index created/updated.")

    documents = asyncio.run(_load_documents(db_url))
    print(f"Loaded {len(documents)} catalog documents from Postgres.")

    if not documents:
        print("No documents found. Nothing to upload.")
        return

    search_client = SearchClient(endpoint=search_endpoint, index_name=index_name, credential=credential)

    uploaded = 0
    for batch in _chunked(documents, BATCH_SIZE):
        results = search_client.upload_documents(documents=batch)
        failed = [r.key for r in results if not r.succeeded]
        if failed:
            raise RuntimeError(f"Upload failed for {len(failed)} documents: {failed[:5]}")
        uploaded += len(batch)

    print(f"Uploaded {uploaded} documents.")

    probe = search_client.search(search_text="human oversight", top=3, include_total_count=True)
    probe_docs = list(probe)
    total_count = probe.get_count()
    print(f"Validation query 'human oversight' returned {len(probe_docs)} docs in top results.")
    if total_count is not None:
        print(f"Total estimated matches: {total_count}")


if __name__ == "__main__":
    main()

