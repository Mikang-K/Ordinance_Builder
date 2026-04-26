"""
Type-specific ordinance data loader.

Loads statutes and ordinances for a given ordinance type without touching
incremental_update.py or initial_load.py.  Safe to re-run (MERGE idempotent).

Usage:
    python -m pipeline.scripts.type_load --type 설치·운영
    python -m pipeline.scripts.type_load --type 관리·규제
    python -m pipeline.scripts.type_load --type 복지·서비스
    python -m pipeline.scripts.type_load --type all   # all non-지원 types

Environment:
    SKIP_PROVISION_EMBEDDING=true  (default for this script — AuraDB capacity)
    TYPE_FILTER=설치·운영           (alternative to --type flag)
"""

import argparse
import logging
import os
import time

from pipeline.api.law_api_client import LawApiClient
from pipeline.config import config
from pipeline.loaders.neo4j_loader import Neo4jLoader
from pipeline.scripts.initial_load import load_ordinance, load_statute

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("type_load")

SUPPORTED_TYPES = ["설치·운영", "관리·규제", "복지·서비스", "지원"]
NEW_TYPES = ["설치·운영", "관리·규제", "복지·서비스"]  # "all" expands to these


def run(ordinance_type: str) -> None:
    # Force-skip Provision embedding to protect AuraDB 8GB limit
    os.environ.setdefault("SKIP_PROVISION_EMBEDDING", "true")

    types_to_load = NEW_TYPES if ordinance_type == "all" else [ordinance_type]
    logger.info("type_load: starting for types=%s", types_to_load)

    client = LawApiClient()
    with Neo4jLoader() as loader:
        for otype in types_to_load:
            _load_type(otype, client, loader)

    logger.info("type_load: all types complete")


def _load_type(otype: str, client: LawApiClient, loader: Neo4jLoader) -> None:
    start = time.time()
    keywords = config.ordinance_type_keywords.get(otype, [])
    statutes = config.mandatory_statutes_by_type.get(otype, [])

    logger.info("=== [%s] Phase 1: mandatory statutes (%d) ===", otype, len(statutes))
    statute_count = 0
    seen_statute_msts: set[str] = set()
    for name in statutes:
        summaries = client.search_statutes(name)
        for s in summaries:
            if s.title == name and s.mst not in seen_statute_msts:
                seen_statute_msts.add(s.mst)
                if load_statute(s.mst, client, loader, s.detail_link):
                    statute_count += 1

    logger.info("=== [%s] Phase 2: keyword statutes (%d keywords) ===", otype, len(keywords))
    for keyword in keywords:
        summaries = client.search_statutes(keyword)
        for s in summaries:
            if s.mst not in seen_statute_msts:
                seen_statute_msts.add(s.mst)
                if load_statute(s.mst, client, loader, s.detail_link):
                    statute_count += 1

    logger.info("=== [%s] Phase 3: keyword ordinances (%d keywords) ===", otype, len(keywords))
    ordinance_count = 0
    seen_ordinance_msts: set[str] = set()
    for keyword in keywords:
        summaries = client.search_ordinances(keyword)
        for o in summaries:
            if o.mst not in seen_ordinance_msts:
                seen_ordinance_msts.add(o.mst)
                if load_ordinance(o.mst, client, loader, o.detail_link, o.region_name):
                    ordinance_count += 1

    logger.info("=== [%s] Phase 4: rebuilding relationships ===", otype)
    if statute_count + ordinance_count > 0:
        loader.build_based_on_relationships()
        loader.build_superior_to_relationships()
        loader.build_similar_to_relationships()
        loader.build_delegates_relationships()

    elapsed = time.time() - start
    logger.info(
        "[%s] done in %.1fs — %d statutes, %d ordinances loaded",
        otype, elapsed, statute_count, ordinance_count,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load ordinance data for a specific type")
    parser.add_argument(
        "--type",
        required=True,
        choices=SUPPORTED_TYPES + ["all"],
        help="Ordinance type to load, or 'all' for all non-지원 types",
    )
    args = parser.parse_args()

    # Allow TYPE_FILTER env as alternative
    type_arg = os.getenv("TYPE_FILTER") or args.type
    run(type_arg)
