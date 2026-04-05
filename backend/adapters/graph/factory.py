import os

from .base import GraphAdapter
from .graphdb import GraphDBAdapter

_DEFAULT_ENDPOINT = "http://172.210.64.73:7200"
_DEFAULT_REPOSITORY = "governance"


def get_graph_adapter() -> GraphAdapter:
    """Return a GraphDBAdapter configured from environment variables.

    Env vars (both optional — defaults match docker-compose):
      GRAPHDB_ENDPOINT    — e.g. http://172.210.64.73:7200
      GRAPHDB_REPOSITORY  — repository name (default: governance)
    """
    endpoint = os.getenv("GRAPHDB_ENDPOINT", _DEFAULT_ENDPOINT)
    repository = os.getenv("GRAPHDB_REPOSITORY", _DEFAULT_REPOSITORY)
    return GraphDBAdapter(endpoint=endpoint, repository=repository)
