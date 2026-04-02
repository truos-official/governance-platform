"""
Seed catalog — Phase 2.10-2.13.

Loads UN_AI_Governance_Dataset_v2.xlsx from data/ and seeds:
  Phase 2.10: 59 controls -> Azure AI Search (aigov-search)
  Phase 2.11: 140 requirements -> Azure AI Search
  Phase 2.12: 59 controls -> PostgreSQL (aigov-db)
  Phase 2.13: 140 requirements -> PostgreSQL

Run: python infra/scripts/seed_catalog.py --phase 2.10

Authentication: azure-identity DefaultAzureCredential (uses managed identity in ACA,
                developer credential locally via az login).
"""
import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATASET_PATH = Path(__file__).parents[2] / "data" / "UN_AI_Governance_Dataset_v2.xlsx"

FOUNDATION_CONTROLS = ["RM-0", "RM-1", "RM-2", "RO-2", "LC-1", "SE-1", "OM-1", "AA-1", "GL-1", "CO-1"]


def seed_controls_search():
    """Phase 2.10: index 59 controls into aigov-search."""
    raise NotImplementedError("Phase 2.10")


def seed_requirements_search():
    """Phase 2.11: index 140 requirements into aigov-search."""
    raise NotImplementedError("Phase 2.11")


def seed_controls_postgres():
    """Phase 2.12: insert 59 controls into PostgreSQL via SQLAlchemy."""
    raise NotImplementedError("Phase 2.12")


def seed_requirements_postgres():
    """Phase 2.13: insert 140 requirements into PostgreSQL via SQLAlchemy."""
    raise NotImplementedError("Phase 2.13")


PHASES = {
    "2.10": seed_controls_search,
    "2.11": seed_requirements_search,
    "2.12": seed_controls_postgres,
    "2.13": seed_requirements_postgres,
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed governance catalog")
    parser.add_argument("--phase", choices=PHASES.keys(), required=True)
    args = parser.parse_args()

    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    logger.info("Running seed phase %s", args.phase)
    PHASES[args.phase]()
    logger.info("Done.")
