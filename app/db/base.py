from abc import ABC, abstractmethod
from typing import Any


class GraphDBInterface(ABC):
    """
    Abstract interface for the graph database.

    Both MockGraphDB and the future Neo4jGraphDB implement this contract.
    Swapping backends requires changing only one line in workflow.py.
    """

    @abstractmethod
    def find_legal_basis(
        self,
        keywords: list[str],
        support_type: str,
    ) -> list[dict[str, Any]]:
        """
        Return statute provisions relevant to the given keywords and support type.

        Neo4j Cypher equivalent:
            MATCH (s:Statute)-[:CONTAINS]->(p:Provision)
            WHERE ANY(kw IN $keywords WHERE p.content_text CONTAINS kw)
            RETURN s.id, s.title, p.article_no, p.content_text

        Returns list of dicts with keys:
            statute_id, statute_title, provision_article,
            provision_content, relation_type
        """
        ...

    @abstractmethod
    def find_similar_ordinances(
        self,
        region: str,
        keywords: list[str],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Return ordinances from other regions that are similar to the target.

        Neo4j Cypher equivalent:
            MATCH (o1:Ordinance {region_name: $region})-[:SIMILAR_TO]->(o2)
            WHERE ANY(kw IN $keywords WHERE o2.title CONTAINS kw)
            RETURN o2.id, o2.region_name, o2.title

        Returns list of dicts with keys:
            ordinance_id, region_name, title, relevance_reason
        """
        ...

    @abstractmethod
    def get_limiting_provisions(
        self,
        legal_term: str,
    ) -> list[dict[str, Any]]:
        """
        Return provisions that restrict the given legal term (LIMITS relationship).

        Neo4j Cypher equivalent:
            MATCH (p:Provision)-[:LIMITS]->(lt:LegalTerm {term_name: $term})
            RETURN p.article_no, p.content_text, p.is_penalty_clause

        Returns list of dicts with keys:
            article_no, content_text, is_penalty_clause
        """
        ...

    @abstractmethod
    def get_similar_ordinance_provisions(
        self,
        ordinance_ids: list[str],
    ) -> list[dict[str, Any]]:
        """
        Return provision content for the given ordinance IDs.

        Used to surface real-world examples during the article interview phase.

        Neo4j Cypher equivalent:
            MATCH (o:Ordinance)-[:CONTAINS]->(p:Provision)
            WHERE o.id IN $ids
            RETURN o.id, o.region_name, o.title, p.article_no, p.content_text

        Returns list of dicts with keys:
            ordinance_id, region_name, ordinance_title, article_no, content_text
        """
        ...

    @abstractmethod
    def find_legal_terms(
        self,
        keywords: list[str],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Return LegalTerm nodes relevant to the given keywords.

        Primary path  — DEFINES (Provision → LegalTerm):
            MATCH (p:Provision)-[:DEFINES]->(lt:LegalTerm)
            WHERE ANY(kw IN $keywords WHERE lt.term_name CONTAINS kw)

        Returns list of dicts with keys:
            term_name, definition, source_statute
        """
        ...

    @abstractmethod
    def get_legal_conflicts(
        self,
        ordinance_id: str,
    ) -> list[dict[str, Any]]:
        """
        Return CONFLICTS_WITH relationships for the given ordinance.

        OWL: 상충하다 — identifies ordinance provisions potentially conflicting
        with penalty/restriction provisions in the referenced superior statutes.

        Returns list of dicts with keys:
            ordinance_id, ordinance_article, statute_article,
            statute_title, conflict_content, confidence
        """
        ...

    @abstractmethod
    def vector_search_provisions(
        self,
        embedding: list[float],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Semantic search over Provision nodes using a pre-computed embedding.

        Neo4j Cypher equivalent:
            CALL db.index.vector.queryNodes('idx_provision_embedding', $limit, $embedding)
            YIELD node AS p, score
            MATCH (s:Statute)-[:CONTAINS]->(p)
            RETURN s.id, s.title, p.article_no, p.content_text, 'VECTOR_MATCH', score

        Returns list of dicts with keys:
            statute_id, statute_title, provision_article,
            provision_content, relation_type ('VECTOR_MATCH')
        """
        ...

    @abstractmethod
    def vector_search_ordinances(
        self,
        embedding: list[float],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Semantic search over Ordinance nodes using a pre-computed embedding.

        Neo4j Cypher equivalent:
            CALL db.index.vector.queryNodes('idx_ordinance_embedding', $limit, $embedding)
            YIELD node AS o, score
            RETURN o.id, o.region_name, o.title, score, '벡터 유사도 기반 추천'

        Returns list of dicts with keys:
            ordinance_id, region_name, title,
            similarity_score, relevance_reason
        """
        ...
