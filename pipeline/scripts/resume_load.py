"""
Resume script: runs Phase 4 (relationships) and Phase 5 (embeddings) only.

- Phase 4 steps are skipped if their relationship/label count is already > 0.
- Phase 5 is always idempotent (skips already-embedded Provision nodes).

Usage:
    cd d:/Project/Ordinance_Builder
    python -m pipeline.scripts.resume_load
"""

import logging

from neo4j import GraphDatabase

from pipeline.api.law_api_client import LawApiClient
from pipeline.config import config
from pipeline.loaders.neo4j_loader import Neo4jLoader
from pipeline.transform.schema_mapper import map_legal_term

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("resume_load")


def _count_relationships(driver, rel_type: str) -> int:
    with driver.session() as session:
        result = session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS cnt")
        return result.single()["cnt"]


def _count_labeled_nodes(driver, label: str) -> int:
    with driver.session() as session:
        result = session.run(f"MATCH (n:{label}) RETURN count(n) AS cnt")
        return result.single()["cnt"]


_CHUNK_SIZE = 500  # commit to Neo4j every N provisions


def _embed_all_provisions(loader: Neo4jLoader) -> None:
    """Embed Provision nodes that have content_text but no embedding (idempotent).

    Processes in chunks of _CHUNK_SIZE so progress is saved incrementally —
    safe to interrupt and resume at any time.
    """
    _FETCH_UNEMBEDDED = """
    MATCH (p:Provision)
    WHERE p.content_text IS NOT NULL AND p.embedding IS NULL
    RETURN p.id AS id, p.content_text AS text
    """
    with loader._driver.session() as session:
        rows = [dict(r) for r in session.run(_FETCH_UNEMBEDDED)]

    if not rows:
        logger.info("No unembedded provisions found — skipping Phase 5")
        return

    pairs = [(r["id"], r["text"]) for r in rows]
    total = len(pairs)
    logger.info("Phase 5: embedding %d provisions (chunk size=%d)...", total, _CHUNK_SIZE)

    for i in range(0, total, _CHUNK_SIZE):
        chunk = pairs[i : i + _CHUNK_SIZE]
        loader.embed_provisions_batch(chunk)
        logger.info("Phase 5 progress: %d / %d (%.1f%%)", min(i + _CHUNK_SIZE, total), total, min(i + _CHUNK_SIZE, total) / total * 100)


def _load_legal_terms(loader: Neo4jLoader) -> None:
    """Fetch and upsert LegalTerm nodes from API (idempotent via MERGE)."""
    import time
    client = LawApiClient()
    seen: set[str] = set()
    count = 0
    for keyword in config.domain_keywords:
        summaries = client.search_legal_terms(keyword)
        for s in summaries:
            if s.term_name not in seen:
                seen.add(s.term_name)
                details = client.get_legal_term_detail(s.mst)
                if details:
                    nodes = [map_legal_term(d) for d in details]
                    loader.upsert_legal_terms(nodes)
                    count += len(nodes)
                time.sleep(config.api_request_delay)
    logger.info("LegalTerm load: %d nodes upserted", count)


def run() -> None:
    driver = GraphDatabase.driver(
        config.neo4j_uri, auth=(config.neo4j_user, config.neo4j_password)
    )

    # ── Phase 1.5 status check ─────────────────────────────────────────
    legal_term_count = _count_labeled_nodes(driver, "LegalTerm")
    legal_terms_done = legal_term_count > 0
    logger.info(
        "  %-25s %7d  %s",
        "LegalTerm",
        legal_term_count,
        "✓ done" if legal_terms_done else "✗ missing",
    )

    # ── Phase 4 status check ───────────────────────────────────────────
    logger.info("=== Checking Phase 4 relationship counts ===")
    phase4_steps = [
        ("BASED_ON",           "based_on"),
        ("SUPERIOR_TO",        "superior_to"),
        ("SIMILAR_TO",         "similar_to"),
        ("DELEGATES",          "delegates"),
        ("APPLIES_BY_ANALOGY", "applies_by_analogy"),
        ("DEFINES",            "defines"),
        ("CONFLICTS_WITH",     "conflicts_with"),
    ]
    label_steps = [
        ("RightsSubject", "legal_term_subtypes"),
        ("LegalAction",   "legal_term_subtypes"),
        ("LegalObject",   "legal_term_subtypes"),
    ]

    rel_counts = {}
    for rel_type, _ in phase4_steps:
        cnt = _count_relationships(driver, rel_type)
        rel_counts[rel_type] = cnt
        status = "✓ done" if cnt > 0 else "✗ missing"
        logger.info("  %-25s %7d  %s", rel_type, cnt, status)

    label_counts = {}
    for label, _ in label_steps:
        cnt = _count_labeled_nodes(driver, label)
        label_counts[label] = cnt
    subtypes_done = all(label_counts[l] > 0 for l, _ in label_steps)
    logger.info("  %-25s %s", "LegalTerm subtypes", "✓ done" if subtypes_done else "✗ missing")

    driver.close()

    # ── Phase 1.5 execution (skip if already done) ─────────────────────
    with Neo4jLoader() as loader:
        if not legal_terms_done:
            logger.info("=== Phase 1.5: loading LegalTerm nodes ===")
            _load_legal_terms(loader)
        else:
            logger.info("LegalTerm: skipped (%d nodes already exist)", legal_term_count)

    # ── Phase 4 execution (skip if already done) ───────────────────────
    with Neo4jLoader() as loader:
        logger.info("=== Phase 4: building missing relationships ===")

        if rel_counts["BASED_ON"] == 0:
            logger.info("Running BASED_ON...")
            loader.build_based_on_relationships()
        else:
            logger.info("BASED_ON: skipped")

        if rel_counts["SUPERIOR_TO"] == 0:
            logger.info("Running SUPERIOR_TO...")
            loader.build_superior_to_relationships()
        else:
            logger.info("SUPERIOR_TO: skipped")

        if rel_counts["SIMILAR_TO"] == 0:
            logger.info("Running SIMILAR_TO...")
            loader.build_similar_to_relationships()
        else:
            logger.info("SIMILAR_TO: skipped")

        if rel_counts["DELEGATES"] == 0:
            logger.info("Running DELEGATES...")
            loader.build_delegates_relationships()
        else:
            logger.info("DELEGATES: skipped")

        if rel_counts["APPLIES_BY_ANALOGY"] == 0:
            logger.info("Running APPLIES_BY_ANALOGY...")
            loader.build_applies_by_analogy_relationships()
        else:
            logger.info("APPLIES_BY_ANALOGY: skipped")

        if rel_counts["DEFINES"] == 0:
            logger.info("Running DEFINES...")
            loader.build_defines_relationships()
        else:
            logger.info("DEFINES: skipped")

        if not subtypes_done:
            logger.info("Running LegalTerm subtypes...")
            loader.build_legal_term_subtypes()
        else:
            logger.info("LegalTerm subtypes: skipped")

        if rel_counts["CONFLICTS_WITH"] == 0:
            logger.info("Running CONFLICTS_WITH...")
            loader.build_conflicts_with_relationships()
        else:
            logger.info("CONFLICTS_WITH: skipped")

        # ── Phase 5: embed provisions ──────────────────────────────────
        logger.info("=== Phase 5: embedding provisions ===")
        _embed_all_provisions(loader)

    logger.info("Resume complete.")


if __name__ == "__main__":
    run()
