import urllib.parse

import httpx

from .base import GraphAdapter


class GraphDBAdapter(GraphAdapter):
    """GraphAdapter implementation backed by a GraphDB triplestore."""

    def __init__(self, endpoint: str, repository: str) -> None:
        self._query_url = f"{endpoint.rstrip('/')}/repositories/{repository}"
        self._update_url = f"{endpoint.rstrip('/')}/repositories/{repository}/statements"

    async def query(self, sparql: str) -> list[dict]:
        """Execute a SPARQL SELECT query and return bindings as a list of dicts."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._query_url,
                headers={
                    "Accept": "application/sparql-results+json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                content=urllib.parse.urlencode({"query": sparql}),
            )
            response.raise_for_status()

        bindings = response.json()["results"]["bindings"]
        return [
            {var: cell["value"] for var, cell in row.items()}
            for row in bindings
        ]

    async def insert_triple(
        self,
        subject: str,
        predicate: str,
        object: str,
        annotations: dict | None,
    ) -> bool:
        """Insert an RDF triple, with optional RDF-Star annotations."""
        if annotations:
            annotation_clauses = " ".join(
                f"<{k}> <{v}>" for k, v in annotations.items()
            )
            sparql = (
                f"INSERT DATA {{ "
                f"<< <{subject}> <{predicate}> <{object}> >> {annotation_clauses} "
                f"}}"
            )
        else:
            sparql = f"INSERT DATA {{ <{subject}> <{predicate}> <{object}> }}"

        return await self._update(sparql)

    async def delete_triple(self, subject: str, predicate: str, object: str) -> bool:
        """Delete an RDF triple."""
        sparql = f"DELETE DATA {{ <{subject}> <{predicate}> <{object}> }}"
        return await self._update(sparql)

    async def _update(self, sparql: str) -> bool:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._update_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                content=urllib.parse.urlencode({"update": sparql}),
            )
        return response.status_code in (200, 204)
