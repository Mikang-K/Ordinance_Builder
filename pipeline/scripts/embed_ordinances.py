"""
Embed unembedded Ordinance nodes in AuraDB.

Skips Provision nodes (too large for 8GB AuraDB limit).
Uses the same Gemini embedding-001 model as the rest of the pipeline.
Idempotent: only processes nodes where embedding IS NULL.

Usage:
    python -m pipeline.scripts.embed_ordinances           # all unembedded
    python -m pipeline.scripts.embed_ordinances --type 설치·운영  # type filter
    python -m pipeline.scripts.embed_ordinances --dry-run  # count only
"""

import argparse
import logging
import time

from pipeline.config import config
from pipeline.loaders.neo4j_loader import Neo4jLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("embed_ordinances")

_FETCH_UNEMBEDDED = """
MATCH (o:Ordinance)
WHERE o.embedding IS NULL
RETURN o.id AS id, o.title AS title, o.region_name AS region_name
"""

_FETCH_UNEMBEDDED_BY_KEYWORDS = """
MATCH (o:Ordinance)
WHERE o.embedding IS NULL AND any(kw IN $keywords WHERE o.title CONTAINS kw)
RETURN o.id AS id, o.title AS title, o.region_name AS region_name
"""

_SET_ORDINANCE_EMBEDDING = """
MATCH (o:Ordinance {id: $id})
SET o.embedding = $embedding
"""


def run(ordinance_type: str | None = None, dry_run: bool = False) -> None:
    keywords: list[str] = []
    if ordinance_type:
        keywords = config.ordinance_type_keywords.get(ordinance_type, [])
        if not keywords:
            logger.warning("No keywords found for type '%s'", ordinance_type)

    with Neo4jLoader() as loader:
        rows = _fetch_unembedded(loader, keywords)

        total = len(rows)
        batches = (total + config.embedding_batch_size - 1) // config.embedding_batch_size
        est_hours = (batches * config.embedding_request_delay) / 3600
        est_cost = total * 3072 * 0.00000001  # rough Gemini embedding-001 estimate

        logger.info("Ordinances to embed: %d", total)
        logger.info(
            "Estimated time: ~%.1f hours (batch=%d, delay=%.1fs)",
            est_hours, config.embedding_batch_size, config.embedding_request_delay,
        )
        logger.info("Estimated cost: ~$%.3f (Gemini embedding-001)", est_cost)

        if dry_run:
            logger.info("--dry-run: exiting without embedding")
            return

        if total == 0:
            logger.info("No unembedded Ordinance nodes found — nothing to do")
            return

        confirm = input("Continue? (y/N): ").strip().lower()
        if confirm not in ("y", "yes"):
            logger.info("Aborted by user")
            return

        _embed_batch(loader, rows)


def _fetch_unembedded(loader: Neo4jLoader, keywords: list[str]) -> list[dict]:
    with loader._driver.session() as session:
        if keywords:
            rows = [dict(r) for r in session.run(_FETCH_UNEMBEDDED_BY_KEYWORDS, keywords=keywords)]
        else:
            rows = [dict(r) for r in session.run(_FETCH_UNEMBEDDED)]
    return rows


def _embed_batch(loader: Neo4jLoader, rows: list[dict]) -> None:
    embedder = loader._get_embedder()
    done = 0
    start = time.time()

    for i in range(0, len(rows), config.embedding_batch_size):
        batch = rows[i : i + config.embedding_batch_size]
        texts = [f"{r['title']} {r['region_name'] or ''}" for r in batch]

        vectors = Neo4jLoader._embed_documents_with_retry(embedder, texts)

        with loader._driver.session() as session:
            for row, vec in zip(batch, vectors):
                session.run(_SET_ORDINANCE_EMBEDDING, id=row["id"], embedding=vec)

        done += len(batch)
        elapsed = time.time() - start
        logger.info("Embedded %d / %d (%.1fs elapsed)", done, len(rows), elapsed)

        if i + config.embedding_batch_size < len(rows):
            time.sleep(config.embedding_request_delay)

    logger.info("embed_ordinances complete: %d nodes embedded in %.1fs", done, time.time() - start)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Embed unembedded Ordinance nodes")
    parser.add_argument("--type", default=None, help="Filter by ordinance type keywords")
    parser.add_argument("--dry-run", action="store_true", help="Count only, do not embed")
    args = parser.parse_args()
    run(ordinance_type=args.type, dry_run=args.dry_run)
