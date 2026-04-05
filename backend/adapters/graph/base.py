from abc import ABC, abstractmethod


class GraphAdapter(ABC):
    """Abstract base class for RDF graph / triplestore backends."""

    @abstractmethod
    async def query(self, sparql: str) -> list[dict]:
        """Execute a SPARQL SELECT query and return result bindings."""

    @abstractmethod
    async def insert_triple(
        self,
        subject: str,
        predicate: str,
        object: str,
        annotations: dict | None,
    ) -> bool:
        """Insert an RDF triple with optional RDF-Star annotations. Returns True on success."""

    @abstractmethod
    async def delete_triple(self, subject: str, predicate: str, object: str) -> bool:
        """Delete an RDF triple. Returns True on success."""
