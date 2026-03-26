"""
Incremental update script (run periodically, e.g. weekly via cron).

Only re-loads statutes and ordinances whose enforcement_date has changed
since the last sync. Unchanged records are skipped for efficiency.

Usage:
    cd d:/Project/Ordinance_Builder
    python -m pipeline.scripts.incremental_update

Cron example (weekly, Monday 02:00):
    0 2 * * 1 cd /path/to/project && python -m pipeline.scripts.incremental_update
"""

import logging
import time

from pipeline.api.law_api_client import LawApiClient
from pipeline.config import config
from pipeline.loaders.neo4j_loader import Neo4jLoader
from pipeline.scripts.initial_load import load_ordinance, load_statute
from pipeline.sync.change_detector import ChangeDetector, ChangeStatus
from pipeline.transform.schema_mapper import map_ordinance, map_statute

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("incremental_update")


def run() -> None:
    start = time.time()
    client = LawApiClient()

    statute_updated = 0
    statute_skipped = 0
    ordinance_updated = 0
    ordinance_skipped = 0

    with Neo4jLoader() as loader:
        detector = ChangeDetector(loader)

        # ── Statutes ───────────────────────────────────────────────────
        logger.info("Checking statutes for changes...")
        all_statute_summaries = []
        for keyword in config.domain_keywords + config.mandatory_statutes:
            all_statute_summaries.extend(client.search_statutes(keyword))

        # Deduplicate by MST
        seen: set[str] = set()
        unique_statutes = []
        for s in all_statute_summaries:
            if s.mst not in seen:
                seen.add(s.mst)
                unique_statutes.append(s)

        statute_results = detector.detect_statute_changes(unique_statutes)
        for result in statute_results:
            if result.status == ChangeStatus.UNCHANGED:
                statute_skipped += 1
                continue
            if load_statute(result.summary.mst, client, loader, result.summary.detail_link):
                statute_updated += 1

        # ── Ordinances ─────────────────────────────────────────────────
        logger.info("Checking ordinances for changes...")
        all_ordinance_summaries = []
        for keyword in config.domain_keywords:
            all_ordinance_summaries.extend(client.search_ordinances(keyword))

        seen_ord: set[str] = set()
        unique_ordinances = []
        for o in all_ordinance_summaries:
            if o.mst not in seen_ord:
                seen_ord.add(o.mst)
                unique_ordinances.append(o)

        ordinance_results = detector.detect_ordinance_changes(unique_ordinances)
        for result in ordinance_results:
            if result.status == ChangeStatus.UNCHANGED:
                ordinance_skipped += 1
                continue
            if load_ordinance(result.summary.mst, client, loader, result.summary.detail_link):
                ordinance_updated += 1

        # Rebuild relationships only if something changed
        if statute_updated + ordinance_updated > 0:
            logger.info("Rebuilding relationships...")
            loader.build_superior_to_relationships()
            loader.build_similar_to_relationships()
            loader.build_based_on_relationships()

    elapsed = time.time() - start
    logger.info(
        "Incremental update done in %.1fs — "
        "statutes: %d updated, %d skipped | "
        "ordinances: %d updated, %d skipped",
        elapsed,
        statute_updated, statute_skipped,
        ordinance_updated, ordinance_skipped,
    )


if __name__ == "__main__":
    run()
