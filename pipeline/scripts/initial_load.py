"""
Initial data load script (run once).

Loads:
0. Create Neo4j vector indexes (IF NOT EXISTS — safe to re-run)
1. MANDATORY_STATUTES – core statutes required regardless of domain keyword
2. Domain-keyword statutes – statutes matching DOMAIN_KEYWORDS
3. Domain-keyword ordinances – ordinances matching DOMAIN_KEYWORDS
4. Build graph relationships (BASED_ON, SUPERIOR_TO, SIMILAR_TO, …)
5. Embed all Provision nodes in bulk (skips already-embedded nodes)

Usage:
    cd d:/Project/Ordinance_Builder
    python -m pipeline.scripts.initial_load
"""

import logging
import time

from pipeline.api.law_api_client import LawApiClient
from pipeline.config import config
from pipeline.loaders.neo4j_loader import Neo4jLoader
from pipeline.transform.schema_mapper import map_ordinance, map_statute

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("initial_load")


def load_statute(mst: str, client: LawApiClient, loader: Neo4jLoader, detail_link: str = "") -> bool:
    """Fetch full statute and upsert into Neo4j. Returns True on success."""
    full = client.get_statute_full(mst, detail_link)
    if not full:
        logger.warning("failed to fetch statute MST=%s", mst)
        return False
    statute_node, provision_nodes, para_nodes, item_nodes, subitem_nodes = map_statute(full)
    loader.upsert_statute(statute_node, provision_nodes, para_nodes, item_nodes, subitem_nodes)
    time.sleep(config.api_request_delay)
    return True


def load_ordinance(
    mst: str, client: LawApiClient, loader: Neo4jLoader,
    detail_link: str = "", region_name_fallback: str = "",
) -> bool:
    """Fetch full ordinance and upsert into Neo4j. Returns True on success."""
    full = client.get_ordinance_full(mst, detail_link)
    if not full:
        logger.warning("failed to fetch ordinance MST=%s", mst)
        return False
    # XML may omit <자치단체명>; fall back to the region from the list search
    if not full.region_name and region_name_fallback:
        full.region_name = region_name_fallback
    ordinance_node, provision_nodes, para_nodes, item_nodes, subitem_nodes = map_ordinance(full)
    loader.upsert_ordinance(ordinance_node, provision_nodes, para_nodes, item_nodes, subitem_nodes)
    time.sleep(config.api_request_delay)
    return True


def _embed_all_provisions(loader: Neo4jLoader) -> None:
    """
    Fetch all Provision nodes that have content_text but no embedding, then
    embed them in bulk.  Using `embedding IS NULL` makes this idempotent —
    re-running the script won't re-embed nodes that are already embedded.
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
    logger.info("Phase 5: embedding %d provisions...", len(pairs))
    loader.embed_provisions_batch(pairs)


def run() -> None:
    start = time.time()
    client = LawApiClient()

    with Neo4jLoader() as loader:
        statute_count = 0
        ordinance_count = 0
        seen_statute_msts: set[str] = set()
        seen_ordinance_msts: set[str] = set()

        # ── 0. Create vector indexes ───────────────────────────────────
        logger.info("=== Phase 0: creating vector indexes ===")
        loader.create_vector_indexes()

        # ── 1. Mandatory statutes ──────────────────────────────────────
        logger.info("=== Phase 1: mandatory statutes (%d) ===", len(config.mandatory_statutes))
        for name in config.mandatory_statutes:
            summaries = client.search_statutes(name)
            for s in summaries:
                if s.title == name and s.mst not in seen_statute_msts:
                    seen_statute_msts.add(s.mst)
                    if load_statute(s.mst, client, loader, s.detail_link):
                        statute_count += 1

        # ── 2. Domain-keyword statutes ─────────────────────────────────
        logger.info("=== Phase 2: domain-keyword statutes (%d keywords) ===", len(config.domain_keywords))
        for keyword in config.domain_keywords:
            summaries = client.search_statutes(keyword)
            for s in summaries:
                if s.mst not in seen_statute_msts:
                    seen_statute_msts.add(s.mst)
                    if load_statute(s.mst, client, loader, s.detail_link):
                        statute_count += 1

        # ── 3. Domain-keyword ordinances ───────────────────────────────
        logger.info("=== Phase 3: domain-keyword ordinances (%d keywords) ===", len(config.domain_keywords))
        for keyword in config.domain_keywords:
            summaries = client.search_ordinances(keyword)
            for o in summaries:
                if o.mst not in seen_ordinance_msts:
                    seen_ordinance_msts.add(o.mst)
                    if load_ordinance(o.mst, client, loader, o.detail_link, o.region_name):
                        ordinance_count += 1

        # ── 4. Build relationships ─────────────────────────────────────
        logger.info("=== Phase 4: building relationships ===")
        loader.build_based_on_relationships()              # must run first; others derive from it
        loader.build_superior_to_relationships()
        loader.build_similar_to_relationships()
        loader.build_delegates_relationships()             # OWL: 위임하다 (inverse of BASED_ON)
        loader.build_applies_by_analogy_relationships()   # OWL: 준용하다
        loader.build_defines_relationships()              # OWL: 정의하다
        loader.build_legal_term_subtypes()                # OWL: 권리주체/법적행위/객체 labels
        loader.build_conflicts_with_relationships()       # OWL: 상충하다 (last — depends on all above)

        # ── 5. Bulk-embed all Provision nodes ─────────────────────────
        logger.info("=== Phase 5: embedding provisions ===")
        _embed_all_provisions(loader)

    elapsed = time.time() - start
    logger.info(
        "Initial load complete in %.1fs — %d statutes, %d ordinances",
        elapsed, statute_count, ordinance_count,
    )


if __name__ == "__main__":
    run()
