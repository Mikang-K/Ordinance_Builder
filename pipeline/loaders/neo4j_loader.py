"""
Neo4j loader: upserts Statute, Provision, and Ordinance nodes using MERGE.

Design principles:
- MERGE on stable IDs → safe to re-run (idempotent)
- On statute update: delete old provisions → create fresh ones
  (provision structure can change between revisions)
- Batch provision creation with UNWIND for performance
- SIMILAR_TO relationships computed from vector similarity (gemini-embedding-001)
"""

import logging
import time
from dataclasses import asdict

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from neo4j import GraphDatabase

from pipeline.config import config
from pipeline.transform.schema_mapper import (
    ItemNode,
    LegalTermNode,
    OrdinanceNode,
    ParagraphNode,
    ProvisionNode,
    StatuteNode,
    SubItemNode,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

_UPSERT_STATUTE = """
MERGE (s:Statute {id: $id})
ON CREATE SET s.created_at = datetime()
SET s.title = $title,
    s.category = $category,
    s.enforcement_date = $enforcement_date,
    s.promulgation_date = $promulgation_date,
    s.last_synced = datetime()
"""

_DELETE_STATUTE_PROVISIONS = """
MATCH (s:Statute {id: $statute_id})-[:CONTAINS]->(p:Provision)
DETACH DELETE p
"""

_CREATE_PROVISIONS_BATCH = """
UNWIND $provisions AS prov
MERGE (p:Provision {id: prov.id})
SET p.article_no      = prov.article_no,
    p.article_title   = prov.article_title,
    p.content_text    = prov.content_text,
    p.is_penalty_clause = prov.is_penalty_clause
WITH p, prov
MATCH (s:Statute {id: prov.statute_id})
MERGE (s)-[:CONTAINS]->(p)
"""

_UPSERT_ORDINANCE = """
MERGE (o:Ordinance {id: $id})
ON CREATE SET o.created_at = datetime()
SET o.title            = $title,
    o.region_name      = $region_name,
    o.enforcement_date = $enforcement_date,
    o.last_synced      = datetime()
"""

_DELETE_ORDINANCE_PROVISIONS = """
MATCH (o:Ordinance {id: $ordinance_id})-[:CONTAINS]->(p:Provision)
DETACH DELETE p
"""

_CREATE_ORDINANCE_PROVISIONS_BATCH = """
UNWIND $provisions AS prov
MERGE (p:Provision {id: prov.id})
SET p.article_no      = prov.article_no,
    p.article_title   = prov.article_title,
    p.content_text    = prov.content_text,
    p.is_penalty_clause = prov.is_penalty_clause
WITH p, prov
MATCH (o:Ordinance {id: prov.statute_id})
MERGE (o)-[:CONTAINS]->(p)
"""

_CREATE_VECTOR_INDEX_ORDINANCE = """
CREATE VECTOR INDEX idx_ordinance_embedding IF NOT EXISTS
FOR (o:Ordinance) ON (o.embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 3072, `vector.similarity_function`: 'cosine'}}
"""

_CREATE_VECTOR_INDEX_PROVISION = """
CREATE VECTOR INDEX idx_provision_embedding IF NOT EXISTS
FOR (p:Provision) ON (p.embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 3072, `vector.similarity_function`: 'cosine'}}
"""

_SET_ORDINANCE_EMBEDDING = """
MATCH (o:Ordinance {id: $id})
SET o.embedding = $embedding
"""

_SET_PROVISION_EMBEDDING = """
UNWIND $items AS item
MATCH (p:Provision {id: item.id})
SET p.embedding = item.embedding
"""

_VECTOR_SIMILAR_TO = """
MATCH (candidate:Ordinance)
WHERE candidate.id <> $ordinance_id AND candidate.embedding IS NOT NULL
WITH candidate, vector.similarity.cosine(candidate.embedding, $embedding) AS score
WHERE score >= $threshold
ORDER BY score DESC
LIMIT $top_k
MATCH (src:Ordinance {id: $ordinance_id})
MERGE (src)-[r:SIMILAR_TO]-(candidate)
ON CREATE SET r.score = score, r.method = 'vector'
ON MATCH  SET r.score = score
"""

_FETCH_ORDINANCE_EMBEDDINGS = """
MATCH (o:Ordinance)
WHERE o.embedding IS NOT NULL
RETURN o.id AS id, o.embedding AS embedding
"""

_BUILD_SUPERIOR_TO = """
MATCH (o:Ordinance)-[:BASED_ON]->(s:Statute {category: '법률'})
CALL (o, s) {
    MERGE (s)-[:SUPERIOR_TO]->(o)
} IN TRANSACTIONS OF 500 ROWS
"""

_BUILD_SIMILAR_TO = """
MATCH (o1:Ordinance)
CALL (o1) {
    MATCH (o2:Ordinance)
    WHERE o1.id < o2.id
      AND o1.title CONTAINS split(o2.title, ' ')[2]
    MERGE (o1)-[:SIMILAR_TO]-(o2)
} IN TRANSACTIONS OF 100 ROWS
"""

_BUILD_BASED_ON = """
MATCH (s:Statute)
WHERE size(s.title) >= 4
CALL (s) {
    MATCH (o:Ordinance)-[:CONTAINS]->(p:Provision)
    WHERE p.content_text CONTAINS s.title
    MERGE (o)-[:BASED_ON]->(s)
} IN TRANSACTIONS OF 50 ROWS
"""

# ---------------------------------------------------------------------------
# Article sub-structure: Paragraph (항), Item (호), SubItem (목)
# ---------------------------------------------------------------------------

_CREATE_PARAGRAPHS_BATCH = """
UNWIND $paragraphs AS para
MERGE (pg:Paragraph {id: para.id})
SET pg.seq          = para.seq,
    pg.content_text = para.content_text
WITH pg, para
MATCH (p:Provision {id: para.provision_id})
MERGE (p)-[:CONTAINS]->(pg)
"""

_CREATE_ITEMS_BATCH = """
UNWIND $items AS it
MERGE (i:Item {id: it.id})
SET i.seq          = it.seq,
    i.content_text = it.content_text
WITH i, it
MATCH (pg:Paragraph {id: it.paragraph_id})
MERGE (pg)-[:CONTAINS]->(i)
"""

_CREATE_SUBITEMS_BATCH = """
UNWIND $subitems AS si
MERGE (s:SubItem {id: si.id})
SET s.seq          = si.seq,
    s.content_text = si.content_text
WITH s, si
MATCH (i:Item {id: si.item_id})
MERGE (i)-[:CONTAINS]->(s)
"""

# Ontology-derived relationship builders
# (also available standalone in migrate_schema.py)

_BUILD_DELEGATES = """
MATCH (o:Ordinance)-[:BASED_ON]->(s:Statute)
MERGE (s)-[:DELEGATES]->(o)
"""

_BUILD_APPLIES_BY_ANALOGY = """
MATCH (o:Ordinance)-[:CONTAINS]->(p:Provision)
WHERE p.content_text CONTAINS '준용'
WITH o, p
MATCH (s:Statute)
WHERE p.content_text CONTAINS s.title
  AND NOT (o)-[:APPLIES_BY_ANALOGY]->(s)
MERGE (o)-[:APPLIES_BY_ANALOGY]->(s)
"""

_BUILD_DEFINES = """
MATCH (p:Provision)
WHERE p.article_title CONTAINS '정의' OR p.article_no = '제2조'
WITH p
MATCH (lt:LegalTerm)
WHERE p.content_text CONTAINS lt.term_name
MERGE (p)-[:DEFINES]->(lt)
"""

_BUILD_CONFLICTS_WITH = """
MATCH (o:Ordinance)-[:BASED_ON]->(s:Statute)-[:CONTAINS]->(sp:Provision)
WHERE sp.is_penalty_clause = true
MATCH (o)-[:CONTAINS]->(op:Provision)
WHERE op.is_penalty_clause = false
  AND ANY(kw IN ['금지', '제한', '초과', '위반']
          WHERE op.content_text CONTAINS kw AND sp.content_text CONTAINS kw)
MERGE (o)-[r:CONFLICTS_WITH]->(sp)
ON CREATE SET r.source_article = op.article_no,
              r.target_article = sp.article_no,
              r.confidence = 'heuristic'
"""

_LABEL_RIGHTS_SUBJECTS = """
MATCH (lt:LegalTerm)
WHERE lt.term_name IN ['청년', '소상공인', '중소기업', '지방자치단체',
                       '창업자', '사업주', '근로자', '수급자']
SET lt:RightsSubject
"""

_LABEL_LEGAL_ACTIONS = """
MATCH (lt:LegalTerm)
WHERE lt.term_name IN ['보조금', '지원금', '창업', '고용', '취업',
                       '보조사업', '일자리']
SET lt:LegalAction
"""

_LABEL_LEGAL_OBJECTS = """
MATCH (lt:LegalTerm)
WHERE lt.term_name IN ['산업단지', '위원회', '규칙', '조례']
SET lt:LegalObject
"""

_UPSERT_LEGAL_TERMS_BATCH = """
UNWIND $terms AS t
MERGE (lt:LegalTerm {term_name: t.term_name})
SET lt.definition  = t.definition,
    lt.synonyms    = t.synonyms,
    lt.last_synced = datetime()
"""


# ---------------------------------------------------------------------------
# Loader class
# ---------------------------------------------------------------------------

class Neo4jLoader:
    """
    Loads statute and ordinance data into Neo4j using MERGE (upsert) semantics.

    Usage:
        with Neo4jLoader() as loader:
            loader.upsert_statute(statute_node, provision_nodes)
    """

    def __init__(self):
        self._driver = GraphDatabase.driver(
            config.neo4j_uri,
            auth=(config.neo4j_user, config.neo4j_password),
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._driver.close()

    def close(self):
        self._driver.close()

    # ------------------------------------------------------------------
    # Statute
    # ------------------------------------------------------------------

    def upsert_statute(
        self,
        statute: StatuteNode,
        provisions: list[ProvisionNode],
        paragraphs: list[ParagraphNode] | None = None,
        items: list[ItemNode] | None = None,
        subitems: list[SubItemNode] | None = None,
    ) -> None:
        """
        Upsert a statute and replace all its provisions (and sub-structure).

        Steps:
        1. MERGE Statute node (create or update properties)
        2. DELETE existing provisions — DETACH DELETE cascades to Paragraph/Item/SubItem
        3. Batch-CREATE new provisions + CONTAINS relationships
        4. Batch-CREATE Paragraph / Item / SubItem hierarchy (if present)
        """
        with self._driver.session() as session:
            session.run(_UPSERT_STATUTE, **asdict(statute))
            session.run(_DELETE_STATUTE_PROVISIONS, statute_id=statute.id)

            if provisions:
                prov_dicts = [asdict(p) for p in provisions]
                session.run(_CREATE_PROVISIONS_BATCH, provisions=prov_dicts)

            if paragraphs:
                session.run(_CREATE_PARAGRAPHS_BATCH, paragraphs=[asdict(p) for p in paragraphs])
            if items:
                session.run(_CREATE_ITEMS_BATCH, items=[asdict(i) for i in items])
            if subitems:
                session.run(_CREATE_SUBITEMS_BATCH, subitems=[asdict(s) for s in subitems])

        logger.info(
            "upserted statute '%s' (%s): %d provisions, %d paragraphs, %d items, %d subitems",
            statute.title, statute.id, len(provisions),
            len(paragraphs or []), len(items or []), len(subitems or []),
        )

    # ------------------------------------------------------------------
    # Ordinance
    # ------------------------------------------------------------------

    def upsert_ordinance(
        self,
        ordinance: OrdinanceNode,
        provisions: list[ProvisionNode],
        paragraphs: list[ParagraphNode] | None = None,
        items: list[ItemNode] | None = None,
        subitems: list[SubItemNode] | None = None,
    ) -> None:
        """Upsert an ordinance and replace all its articles (and sub-structure)."""
        with self._driver.session() as session:
            session.run(_UPSERT_ORDINANCE, **asdict(ordinance))
            session.run(_DELETE_ORDINANCE_PROVISIONS, ordinance_id=ordinance.id)

            if provisions:
                prov_dicts = [asdict(p) for p in provisions]
                session.run(_CREATE_ORDINANCE_PROVISIONS_BATCH, provisions=prov_dicts)

            if paragraphs:
                session.run(_CREATE_PARAGRAPHS_BATCH, paragraphs=[asdict(p) for p in paragraphs])
            if items:
                session.run(_CREATE_ITEMS_BATCH, items=[asdict(i) for i in items])
            if subitems:
                session.run(_CREATE_SUBITEMS_BATCH, subitems=[asdict(s) for s in subitems])

        logger.info(
            "upserted ordinance '%s' [%s]: %d articles, %d paragraphs, %d items, %d subitems",
            ordinance.title, ordinance.region_name, len(provisions),
            len(paragraphs or []), len(items or []), len(subitems or []),
        )

        # Generate and persist embedding for the Ordinance node
        embed_text = f"{ordinance.title} {ordinance.region_name}"
        try:
            vector = self._embed_query_with_retry(self._get_embedder(), embed_text)
            with self._driver.session() as session:
                session.run(_SET_ORDINANCE_EMBEDDING, id=ordinance.id, embedding=vector)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to embed ordinance %s: %s", ordinance.id, exc)

    # ------------------------------------------------------------------
    # Relationship builders (run after bulk load)
    # ------------------------------------------------------------------

    def build_superior_to_relationships(self) -> None:
        """
        Create SUPERIOR_TO edges from all 법률-category statutes to all ordinances.
        Represents legal hierarchy: 법률 > 조례.
        """
        with self._driver.session() as session:
            result = session.run(_BUILD_SUPERIOR_TO)
            summary = result.consume()
        logger.info(
            "SUPERIOR_TO: created %d relationships",
            summary.counters.relationships_created,
        )

    # ------------------------------------------------------------------
    # Embedding methods
    # ------------------------------------------------------------------

    def _get_embedder(self):
        """Lazy-initialize the GoogleGenerativeAIEmbeddings singleton."""
        if not hasattr(self, "_embedder"):
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            self._embedder = GoogleGenerativeAIEmbeddings(
                model=config.embedding_model,
                google_api_key=config.google_api_key,
            )
        return self._embedder

    def _embed_texts_batched(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts in batches to respect rate limits."""
        embedder = self._get_embedder()
        results: list[list[float]] = []
        for i in range(0, len(texts), config.embedding_batch_size):
            batch = texts[i : i + config.embedding_batch_size]
            results.extend(self._embed_documents_with_retry(embedder, batch))
            if i + config.embedding_batch_size < len(texts):
                time.sleep(config.embedding_request_delay)
        return results

    @staticmethod
    def _embed_documents_with_retry(embedder, texts: list[str]) -> list[list[float]]:
        """Call embed_documents with exponential backoff on 429 RESOURCE_EXHAUSTED."""
        def _is_rate_limit(exc: BaseException) -> bool:
            return "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)

        @retry(
            retry=retry_if_exception(_is_rate_limit),
            wait=wait_exponential(multiplier=2, min=60, max=300),
            stop=stop_after_attempt(6),
            reraise=True,
        )
        def _call():
            return embedder.embed_documents(texts)

        return _call()

    @staticmethod
    def _embed_query_with_retry(embedder, text: str) -> list[float]:
        """Call embed_query with exponential backoff on 429 RESOURCE_EXHAUSTED."""
        def _is_rate_limit(exc: BaseException) -> bool:
            return "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)

        @retry(
            retry=retry_if_exception(_is_rate_limit),
            wait=wait_exponential(multiplier=2, min=60, max=300),
            stop=stop_after_attempt(6),
            reraise=True,
        )
        def _call():
            return embedder.embed_query(text)

        return _call()

    def create_vector_indexes(self) -> None:
        """
        Create Neo4j 5.x vector indexes for Ordinance and Provision nodes.
        Uses IF NOT EXISTS — safe to call on every run.
        """
        with self._driver.session() as session:
            session.run(_CREATE_VECTOR_INDEX_ORDINANCE)
            session.run(_CREATE_VECTOR_INDEX_PROVISION)
        logger.info("Vector indexes created (or already exist)")

    def embed_provisions_batch(self, provision_ids_and_texts: list[tuple[str, str]]) -> None:
        """
        Generate and persist embeddings for a batch of Provision nodes.

        Args:
            provision_ids_and_texts: list of (provision_id, content_text) tuples.
                Only provisions with non-null content_text should be passed.
        """
        if not provision_ids_and_texts:
            return
        ids   = [t[0] for t in provision_ids_and_texts]
        texts = [t[1] for t in provision_ids_and_texts]
        vectors = self._embed_texts_batched(texts)
        items = [{"id": pid, "embedding": vec} for pid, vec in zip(ids, vectors)]
        with self._driver.session() as session:
            session.run(_SET_PROVISION_EMBEDDING, items=items)
        logger.info("Embedded %d provisions", len(items))

    # ------------------------------------------------------------------
    # Relationship builders (run after bulk load)
    # ------------------------------------------------------------------

    def build_similar_to_relationships(self) -> None:
        """
        Create SIMILAR_TO edges between ordinances using vector similarity.

        Strategy:
        - Fetch all Ordinance nodes that already have an embedding property
        - For each, query the vector index for the top-10 nearest neighbours
        - MERGE SIMILAR_TO edge where cosine score >= config.similar_to_threshold
        """
        with self._driver.session() as session:
            rows = [dict(r) for r in session.run(_FETCH_ORDINANCE_EMBEDDINGS)]

        if not rows:
            logger.warning(
                "No ordinance embeddings found — skipping SIMILAR_TO build. "
                "Run upsert_ordinance() before calling this method."
            )
            return

        created = 0
        for row in rows:
            with self._driver.session() as session:
                summary = session.run(
                    _VECTOR_SIMILAR_TO,
                    ordinance_id=row["id"],
                    embedding=row["embedding"],
                    top_k=10,
                    threshold=config.similar_to_threshold,
                ).consume()
                created += summary.counters.relationships_created

        logger.info("SIMILAR_TO (vector): created/updated %d relationships", created)

    def build_based_on_relationships(self) -> None:
        """
        Create BASED_ON edges from Ordinance to Statute by scanning ordinance
        provision texts for statute title mentions.

        Strategy: if any Provision of an Ordinance contains a Statute's title string,
        that Ordinance is considered BASED_ON that Statute.
        MERGE ensures idempotency on repeated runs.
        """
        with self._driver.session() as session:
            result = session.run(_BUILD_BASED_ON)
            summary = result.consume()
        logger.info(
            "BASED_ON: created %d relationships",
            summary.counters.relationships_created,
        )

    def build_delegates_relationships(self) -> None:
        """
        OWL: 위임하다 — Statute → Ordinance.
        Derived from BASED_ON (inverse direction). Run after build_based_on_relationships.
        """
        with self._driver.session() as session:
            result = session.run(_BUILD_DELEGATES)
            summary = result.consume()
        logger.info("DELEGATES: created %d relationships", summary.counters.relationships_created)

    def build_applies_by_analogy_relationships(self) -> None:
        """
        OWL: 준용하다 — Ordinance → Statute.
        Detects '준용' keyword in provision text to find referenced statutes.
        """
        with self._driver.session() as session:
            result = session.run(_BUILD_APPLIES_BY_ANALOGY)
            summary = result.consume()
        logger.info("APPLIES_BY_ANALOGY: created %d relationships", summary.counters.relationships_created)

    def build_defines_relationships(self) -> None:
        """
        OWL: 정의하다 — Provision → LegalTerm.
        Connects definition articles (제2조 / 정의 조항) to matching LegalTerm nodes.
        """
        with self._driver.session() as session:
            result = session.run(_BUILD_DEFINES)
            summary = result.consume()
        logger.info("DEFINES: created %d relationships", summary.counters.relationships_created)

    def build_conflicts_with_relationships(self) -> None:
        """
        OWL: 상충하다 — Ordinance → Provision (of Statute).
        Heuristic: ordinance provisions with restriction keywords that co-occur
        with penalty provisions in the referenced statute.
        Run last — depends on BASED_ON being built first.
        """
        with self._driver.session() as session:
            result = session.run(_BUILD_CONFLICTS_WITH)
            summary = result.consume()
        logger.info("CONFLICTS_WITH: created %d relationships", summary.counters.relationships_created)

    def upsert_legal_terms(self, terms: list[LegalTermNode]) -> None:
        """
        Upsert LegalTerm nodes from API data.

        MERGE on term_name (UNIQUE constraint) — safe to re-run.
        Sets definition and synonyms on each node.
        """
        if not terms:
            return
        term_dicts = [
            {"term_name": t.term_name, "definition": t.definition, "synonyms": t.synonyms}
            for t in terms
        ]
        with self._driver.session() as session:
            session.run(_UPSERT_LEGAL_TERMS_BATCH, terms=term_dicts)
        logger.info("upserted %d LegalTerm nodes", len(terms))

    def build_legal_term_subtypes(self) -> None:
        """
        OWL: 권리주체 / 법적행위 / 객체 subtype labels on LegalTerm nodes.
        Multi-label approach: a node can be both LegalTerm and RightsSubject.
        """
        with self._driver.session() as session:
            for cypher, label in [
                (_LABEL_RIGHTS_SUBJECTS, "RightsSubject"),
                (_LABEL_LEGAL_ACTIONS, "LegalAction"),
                (_LABEL_LEGAL_OBJECTS, "LegalObject"),
            ]:
                result = session.run(cypher)
                summary = result.consume()
                logger.info("%s: labeled %d nodes", label, summary.counters.labels_added)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_statute_enforcement_date(self, mst: str) -> str | None:
        """Return the stored enforcement_date for a statute, or None if not found."""
        with self._driver.session() as session:
            result = session.run(
                "MATCH (s:Statute {id: $id}) RETURN s.enforcement_date AS dt",
                id=mst,
            )
            record = result.single()
            return record["dt"] if record else None

    def get_ordinance_enforcement_date(self, mst: str) -> str | None:
        """Return the stored enforcement_date for an ordinance, or None if not found."""
        with self._driver.session() as session:
            result = session.run(
                "MATCH (o:Ordinance {id: $id}) RETURN o.enforcement_date AS dt",
                id=mst,
            )
            record = result.single()
            return record["dt"] if record else None
