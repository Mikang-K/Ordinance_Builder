"""
Neo4j implementation of GraphDBInterface.

Replaces MockGraphDB when real data is loaded via the pipeline.
Swap in workflow.py:  db = Neo4jGraphDB(...)
"""

import logging
from typing import Any

from neo4j import GraphDatabase

from app.core.embedder import get_embedder
from app.db.base import GraphDBInterface

logger = logging.getLogger(__name__)


class Neo4jGraphDB(GraphDBInterface):
    """
    GraphDBInterface backed by a live Neo4j instance.

    Cypher queries mirror the schema defined in CLAUDE.md §4.
    """

    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self._driver.close()

    # ------------------------------------------------------------------
    # GraphDBInterface implementation
    # ------------------------------------------------------------------

    def find_legal_basis(
        self,
        keywords: list[str],
        support_type: str,
    ) -> list[dict[str, Any]]:
        """
        Find statute provisions relevant to the given keywords.

        Priority:
        1. DELEGATES path (OWL: 위임하다): statutes that explicitly delegated authority
           to an ordinance — highest legal grounding.
        2. BASED_ON path: ordinance references a statute by title mention.
        3. Keyword fallback: direct provision text scan when graph has no results.
        """
        all_keywords = [kw for kw in keywords + [support_type] if kw]

        delegates_query = """
        MATCH (s:Statute)-[:DELEGATES]->(o:Ordinance)
        WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw)
        MATCH (s)-[:CONTAINS]->(p:Provision)
        WHERE ANY(kw IN $keywords WHERE p.content_text CONTAINS kw)
        RETURN DISTINCT
               s.id           AS statute_id,
               s.title        AS statute_title,
               p.article_no   AS provision_article,
               p.content_text AS provision_content,
               'DELEGATES'    AS relation_type
        LIMIT 5
        """

        based_on_query = """
        MATCH (o:Ordinance)-[:BASED_ON]->(s:Statute)-[:CONTAINS]->(p:Provision)
        WHERE ANY(kw IN $keywords WHERE p.content_text CONTAINS kw
                  OR o.title CONTAINS kw)
        RETURN DISTINCT
               s.id           AS statute_id,
               s.title        AS statute_title,
               p.article_no   AS provision_article,
               p.content_text AS provision_content,
               'BASED_ON'     AS relation_type
        LIMIT 5
        """

        fallback_query = """
        MATCH (s:Statute)-[:CONTAINS]->(p:Provision)
        WHERE ANY(kw IN $keywords WHERE p.content_text CONTAINS kw)
        RETURN DISTINCT
               s.id           AS statute_id,
               s.title        AS statute_title,
               p.article_no   AS provision_article,
               p.content_text AS provision_content,
               'KEYWORD_MATCH' AS relation_type
        LIMIT 5
        """

        provision_vector_query = """
        CALL db.index.vector.queryNodes('idx_provision_embedding', 5, $embedding)
        YIELD node AS p, score
        MATCH (s:Statute)-[:CONTAINS]->(p)
        RETURN DISTINCT
               s.id           AS statute_id,
               s.title        AS statute_title,
               p.article_no   AS provision_article,
               p.content_text AS provision_content,
               'VECTOR_MATCH'  AS relation_type
        LIMIT 5
        """

        with self._driver.session() as session:
            result = session.run(delegates_query, keywords=all_keywords)
            rows = [dict(r) for r in result]
            if rows:
                return rows
            result = session.run(based_on_query, keywords=all_keywords)
            rows = [dict(r) for r in result]
            if rows:
                return rows
            result = session.run(fallback_query, keywords=all_keywords)
            rows = [dict(r) for r in result]
            if rows:
                return rows
            # 4. Provision vector search
            try:
                embedding = get_embedder().embed_query(" ".join(all_keywords))
                result = session.run(provision_vector_query, embedding=embedding)
                return [dict(r) for r in result]
            except Exception as exc:  # noqa: BLE001
                logger.warning("Provision vector search failed: %s", exc)
            return []

    def find_similar_ordinances(
        self,
        region: str,
        keywords: list[str],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Find semantically similar ordinances from other regions.

        Priority:
        1. Vector index search on idx_ordinance_embedding (semantic similarity)
        2. SIMILAR_TO relationship traversal (pre-computed during pipeline)
        3. Keyword title scan (final fallback when no embeddings/relationships exist)
        """
        vector_query = """
        CALL db.index.vector.queryNodes('idx_ordinance_embedding', $limit, $embedding)
        YIELD node AS o, score
        WHERE o.region_name <> $region
        RETURN o.id          AS ordinance_id,
               o.region_name AS region_name,
               o.title       AS title,
               score         AS similarity_score,
               '벡터 유사도 기반 추천' AS relevance_reason
        ORDER BY score DESC
        LIMIT $limit
        """

        similar_to_query = """
        MATCH (src:Ordinance)
        WHERE src.region_name = $region
          AND ANY(kw IN $keywords WHERE src.title CONTAINS kw)
        MATCH (src)-[:SIMILAR_TO]-(o:Ordinance)
        WHERE o.region_name <> $region
        RETURN DISTINCT
               o.id          AS ordinance_id,
               o.region_name AS region_name,
               o.title       AS title,
               0.0           AS similarity_score,
               'SIMILAR_TO 관계 기반 추천' AS relevance_reason
        LIMIT $limit
        """

        keyword_query = """
        MATCH (o:Ordinance)
        WHERE o.region_name <> $region
          AND ANY(kw IN $keywords WHERE o.title CONTAINS kw)
        RETURN o.id          AS ordinance_id,
               o.region_name AS region_name,
               o.title       AS title,
               0.0           AS similarity_score,
               head([kw IN $keywords WHERE o.title CONTAINS kw]) + ' 관련 유사 조례'
                             AS relevance_reason
        LIMIT $limit
        """

        query_text = " ".join(keywords) if keywords else region

        with self._driver.session() as session:
            # 1. Vector search
            try:
                embedding = get_embedder().embed_query(query_text)
                result = session.run(
                    vector_query, embedding=embedding, region=region, limit=limit
                )
                rows = [dict(r) for r in result]
                if rows:
                    return rows
            except Exception as exc:  # noqa: BLE001
                logger.warning("Vector search failed, falling back: %s", exc)

            # 2. SIMILAR_TO relationship traversal
            result = session.run(similar_to_query, region=region, keywords=keywords, limit=limit)
            rows = [dict(r) for r in result]
            if rows:
                return rows

            # 3. Keyword title scan
            result = session.run(keyword_query, region=region, keywords=keywords, limit=limit)
            return [dict(r) for r in result]

    def get_limiting_provisions(
        self,
        legal_term: str,
    ) -> list[dict[str, Any]]:
        """
        Return provisions that restrict the given legal term (LIMITS relationship).

        Falls back to a text-match if no LIMITS edges exist.
        """
        query = """
        MATCH (p:Provision)
        WHERE p.is_penalty_clause = true
          AND p.content_text CONTAINS $term
        RETURN p.article_no      AS article_no,
               p.content_text    AS content_text,
               p.is_penalty_clause AS is_penalty_clause
        LIMIT 10
        """
        with self._driver.session() as session:
            result = session.run(query, term=legal_term)
            return [dict(r) for r in result]

    def get_similar_ordinance_provisions(
        self,
        ordinance_ids: list[str],
    ) -> list[dict[str, Any]]:
        """
        Fetch all provisions from the given ordinances.

        Returns up to 50 provisions ordered by ordinance then article number,
        so the article_interviewer can surface per-article examples without
        additional DB calls.
        """
        if not ordinance_ids:
            return []
        query = """
        MATCH (o:Ordinance)-[:CONTAINS]->(p:Provision)
        WHERE o.id IN $ids
        RETURN o.id           AS ordinance_id,
               o.region_name  AS region_name,
               o.title        AS ordinance_title,
               p.article_no   AS article_no,
               p.content_text AS content_text
        ORDER BY o.id, p.article_no
        LIMIT 50
        """
        with self._driver.session() as session:
            result = session.run(query, ids=ordinance_ids)
            return [dict(r) for r in result]

    def get_legal_conflicts(
        self,
        ordinance_id: str,
    ) -> list[dict[str, Any]]:
        """
        Return CONFLICTS_WITH relationships for the given ordinance.

        OWL: 상충하다 — Ordinance → Provision (of superior Statute).
        Used by LegalChecker node to surface potential legal risks.
        """
        query = """
        MATCH (o:Ordinance {id: $ordinance_id})-[c:CONFLICTS_WITH]->(sp:Provision)
        MATCH (s:Statute)-[:CONTAINS]->(sp)
        RETURN o.id              AS ordinance_id,
               c.source_article  AS ordinance_article,
               sp.article_no     AS statute_article,
               s.title           AS statute_title,
               sp.content_text   AS conflict_content,
               c.confidence      AS confidence
        ORDER BY s.title
        """
        with self._driver.session() as session:
            result = session.run(query, ordinance_id=ordinance_id)
            return [dict(r) for r in result]
