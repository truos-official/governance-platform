from abc import ABC, abstractmethod
from typing import Any


class GraphAdapter(ABC):
    """
    ABC for RDF graph adapters.
    Relationships carry RDF-star provenance metadata:
    effective_from, effective_to, confidence_score, asserted_by, reviewed_by, version.
    """

    @abstractmethod
    def query(self, sparql: str) -> list[dict]: ...

    @abstractmethod
    def update(self, sparql: str) -> None: ...

    @abstractmethod
    def describe_node(self, uri: str) -> dict: ...


class GraphDBAdapter(GraphAdapter):
    """
    SPARQL adapter for GraphDB Free on aigov-graphdb-vm (172.210.64.73:7200).
    Nodes: Regulation, Requirement, Control, Application, TaxonomyTerm.
    Relationships: IMPLIES, OVERLAPS, SUPERSEDES, CONFLICTS_WITH,
                   HAS_REQUIREMENT, SATISFIED_BY, PARTIALLY_SATISFIED_BY,
                   DEPENDS_ON, ADOPTS, SCOPED_TO, EQUIVALENT_TO, SUBTYPE_OF, MAPS_TO.
    Phase 2.3: load RDF ontology.
    Phase 2.7: implement SPARQL adapter.
    """

    def __init__(self, endpoint: str = "http://172.210.64.73:7200", repository: str = "governance"):
        # Phase 2: initialise SPARQLWrapper
        self._endpoint = endpoint
        self._repository = repository
        self._sparql_url = f"{endpoint}/repositories/{repository}"

    def query(self, sparql: str) -> list[dict]:
        raise NotImplementedError("Phase 2.7")

    def update(self, sparql: str) -> None:
        raise NotImplementedError("Phase 2.7")

    def describe_node(self, uri: str) -> dict:
        raise NotImplementedError("Phase 2.7")
