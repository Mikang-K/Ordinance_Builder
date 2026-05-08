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
            MATCH (p:Provision) WHERE p.embedding IS NOT NULL
            WITH p, vector.similarity.cosine(p.embedding, $embedding) AS score
            MATCH (s:Statute)-[:CONTAINS]->(p)
            RETURN s.id, s.title, p.article_no, p.content_text, 'VECTOR_MATCH', score
            ORDER BY score DESC LIMIT $limit

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
            MATCH (o:Ordinance) WHERE o.embedding IS NOT NULL
            WITH o, vector.similarity.cosine(o.embedding, $embedding) AS score
            RETURN o.id, o.region_name, o.title, score, '벡터 유사도 기반 추천'
            ORDER BY score DESC LIMIT $limit

        Returns list of dicts with keys:
            ordinance_id, region_name, title,
            similarity_score, relevance_reason
        """
        ...

    @abstractmethod
    def get_analogy_applications(
        self,
        keywords: list[str],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Return statute provisions reached via APPLIES_BY_ANALOGY from relevant ordinances.

        OWL: 준용하다 — identifies statutes applied by analogy in similar ordinances.
        Used by graph_retriever to supplement legal_basis with analogy-based grounding.

        Neo4j Cypher equivalent:
            MATCH (o:Ordinance)-[:APPLIES_BY_ANALOGY]->(s:Statute)
            WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw)
            MATCH (s)-[:CONTAINS]->(p:Provision)
            RETURN s.id, s.title, p.article_no, p.content_text, 'APPLIES_BY_ANALOGY'

        Returns list of dicts with keys:
            statute_id, statute_title, provision_article,
            provision_content, relation_type
        """
        ...

    @abstractmethod
    def get_superior_statute_provisions(
        self,
        keywords: list[str],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Return provisions from statutes hierarchically superior to related ordinances.

        OWL: 우위에_있다 — used by legal_checker to verify hierarchy compliance.
        Traverses SUPERIOR_TO (Statute → Ordinance) to surface authoritative provisions.

        Neo4j Cypher equivalent:
            MATCH (s:Statute)-[:SUPERIOR_TO]->(o:Ordinance)
            WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw)
            MATCH (s)-[:CONTAINS]->(p:Provision)
            RETURN s.id, s.title, p.article_no, p.content_text, s.category

        Returns list of dicts with keys:
            statute_id, statute_title, provision_article,
            provision_content, statute_category
        """
        ...

    @abstractmethod
    def get_penalty_chain(
        self,
        keywords: list[str],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Return penalty clause → target provision chains for keyword-matched provisions.

        OWL: 제재하다 — used by legal_checker to verify penalty scope coverage.
        Traverses PENALIZES (Provision → Provision) to surface sanctioned violations.

        Neo4j Cypher equivalent:
            MATCH (penalty:Provision {is_penalty_clause: true})-[:PENALIZES]->(target:Provision)
            WHERE ANY(kw IN $keywords WHERE target.content_text CONTAINS kw)
            RETURN penalty.article_no, penalty.content_text,
                   target.article_no, target.content_text

        Returns list of dicts with keys:
            penalty_article, penalty_content, target_article, target_content
        """
        ...

    @abstractmethod
    def get_delegation_limits(
        self,
        keywords: list[str],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        SWRL Rule 1 — 위임 상속 (DelegationInheritance)

        Return legal terms reachable via DELEGATES → CONTAINS → LIMITS 3-hop path.
        Surfaces the scope of legal restrictions inherited through delegation chains.

        OWL: 위임하다 ∧ 포함하다 ∧ 제한하다 → 간접 제한 범위
        Cypher equivalent:
            MATCH (s:Statute)-[:DELEGATES]->(o:Ordinance)
            WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw)
            MATCH (o)-[:CONTAINS]->(p:Provision)-[:LIMITS]->(lt:LegalTerm)
            RETURN DISTINCT s.id, s.title, lt.term_name, lt.definition, p.article_no

        Returns list of dicts with keys:
            statute_id, statute_title, term_name, definition, provision_article
        """
        ...

    @abstractmethod
    def get_hierarchy_chain(
        self,
        keywords: list[str],
        max_depth: int = 3,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        SWRL Rule 2 — 위계 전이성 (HierarchyTransitivity)

        Return the full hierarchy chain above ordinances matching the keywords.
        Complements the TransitiveObjectProperty declaration in ordinance.rdf.

        OWL: 우위에_있다 (TransitiveObjectProperty) → multi-hop superiority
        Cypher equivalent:
            MATCH path = (s:Statute)-[:SUPERIOR_TO*1..$max_depth]->(o:Ordinance)
            WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw OR s.title CONTAINS kw)
            RETURN DISTINCT s.id, s.title, s.category, o.id, o.title, length(path)
            ORDER BY depth, s.title

        Returns list of dicts with keys:
            statute_id, statute_title, statute_category, ordinance_id, ordinance_title, depth
        """
        ...

    @abstractmethod
    def get_conflict_chain(
        self,
        keywords: list[str],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        SWRL Rule 3 — 충돌 연쇄 (ConflictChain)

        Return cases where a superior statute and an ordinance both LIMITS the same
        LegalTerm — indicating a potential definitional conflict.

        OWL: 우위에_있다 ∧ 포함하다 ∧ 제한하다(상위) ∧ 제한하다(하위, 동일 용어) → 상충하다
        Cypher equivalent:
            MATCH (s:Statute)-[:SUPERIOR_TO]->(o:Ordinance)
            WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw)
            MATCH (s)-[:CONTAINS]->(sp:Provision)-[:LIMITS]->(lt:LegalTerm)
            MATCH (o)-[:CONTAINS]->(op:Provision)-[:LIMITS]->(lt)
            RETURN DISTINCT sp.article_no, sp.content_text,
                            op.article_no, op.content_text, lt.term_name

        Returns list of dicts with keys:
            statute_article, statute_content, ordinance_article, ordinance_content, conflict_term
        """
        ...

    @abstractmethod
    def get_penalty_extension(
        self,
        keywords: list[str],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        SWRL Rule 4 — 벌칙 범위 확장 (PenaltyExtension)

        Return 2-hop PENALIZES chains to surface indirect sanction scope.
        Identifies provisions that are indirectly penalized through an intermediary.

        OWL: 제재하다(?p1, ?p2) ∧ 제재하다(?p2, ?p3) → 제재하다(?p1, ?p3)
        Cypher equivalent:
            MATCH (p1:Provision)-[:PENALIZES]->(p2:Provision)-[:PENALIZES]->(p3:Provision)
            WHERE ANY(kw IN $keywords WHERE p1.content_text CONTAINS kw)
            RETURN DISTINCT p1.article_no, p3.article_no, p3.content_text

        Returns list of dicts with keys:
            src_article, ext_article, ext_content
        """
        ...
