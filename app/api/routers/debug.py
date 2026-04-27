"""
Debug endpoints — verify Neo4j connectivity and query results.
Not intended for production use.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from neo4j import GraphDatabase

from app.core.config import settings
from app.core.embedder import get_embedder
from app.db.neo4j_db import Neo4jGraphDB

router = APIRouter(prefix="/api/v1/debug", tags=["debug"])


def _get_db() -> Neo4jGraphDB:
    return Neo4jGraphDB(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)


@router.get("/db")
def debug_db(
    keywords: Annotated[str, Query(description="쉼표로 구분된 키워드 (예: 청년,창업,지원)")] = "청년,창업,지원",
    region: Annotated[str, Query(description="지역명 (예: 서울특별시 강남구)")] = "서울특별시",
):
    """
    Run find_legal_basis and find_similar_ordinances with given keywords
    and return raw results for inspection.
    """
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    support_type = kw_list[-1] if kw_list else ""

    db = _get_db()
    try:
        legal_basis = db.find_legal_basis(keywords=kw_list, support_type=support_type)
        similar_ordinances = db.find_similar_ordinances(
            region=region, keywords=kw_list, limit=5
        )
    finally:
        db.close()

    return {
        "db_type": type(db).__name__,
        "query": {"keywords": kw_list, "region": region},
        "legal_basis_count": len(legal_basis),
        "legal_basis": legal_basis,
        "similar_ordinances_count": len(similar_ordinances),
        "similar_ordinances": similar_ordinances,
    }


@router.get("/vector")
def debug_vector(
    query: Annotated[str, Query(description="임베딩 검색 쿼리 (예: 청년 창업 지원)")] = "청년 창업 지원",
    region: Annotated[str, Query(description="제외할 지역명")] = "서울특별시",
    limit: Annotated[int, Query(description="반환 결과 수")] = 5,
):
    """
    Directly test the vector index for both Ordinance and Provision nodes.
    Returns embedding dimension, index hit count, and top results.
    """
    # 1. Generate embedding
    try:
        embedding = get_embedder().embed_query(query)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Embedder failed: {exc}") from exc

    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    try:
        with driver.session() as session:
            # 2. Query Ordinance vector index
            ordinance_rows = [
                dict(r)
                for r in session.run(
                    """
                    MATCH (o:Ordinance)
                    WHERE o.embedding IS NOT NULL AND o.region_name <> $region
                    WITH o, vector.similarity.cosine(o.embedding, $embedding) AS score
                    RETURN o.id AS id, o.title AS title, o.region_name AS region_name,
                           score AS similarity_score
                    ORDER BY score DESC
                    LIMIT $limit
                    """,
                    embedding=embedding,
                    region=region,
                    limit=limit,
                )
            ]

            # 3. Query Provision vector index
            provision_rows = [
                dict(r)
                for r in session.run(
                    """
                    MATCH (p:Provision)
                    WHERE p.embedding IS NOT NULL
                    WITH p, vector.similarity.cosine(p.embedding, $embedding) AS score
                    MATCH (s:Statute)-[:CONTAINS]->(p)
                    RETURN p.id AS id, p.article_no AS article_no,
                           s.title AS statute_title, score AS similarity_score,
                           left(p.content_text, 120) AS content_preview
                    ORDER BY score DESC
                    LIMIT $limit
                    """,
                    embedding=embedding,
                    limit=limit,
                )
            ]

            # 4. Check embedding coverage
            coverage = dict(
                session.run(
                    """
                    MATCH (o:Ordinance)
                    RETURN
                      count(o) AS total_ordinances,
                      count(o.embedding) AS embedded_ordinances
                    """
                ).single()
            )
            provision_coverage = dict(
                session.run(
                    """
                    MATCH (p:Provision)
                    RETURN
                      count(p) AS total_provisions,
                      count(p.embedding) AS embedded_provisions
                    """
                ).single()
            )
    finally:
        driver.close()

    return {
        "query": query,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dimensions": len(embedding),
        "coverage": {**coverage, **provision_coverage},
        "ordinance_vector_results": ordinance_rows,
        "provision_vector_results": provision_rows,
    }


@router.get("/legal-terms")
def debug_legal_terms(
    keywords: Annotated[str, Query(description="쉼표로 구분된 키워드 (예: 청년,창업,보조금)")] = "청년,창업,보조금",
    limit: Annotated[int, Query(description="반환 결과 수")] = 10,
):
    """
    Test find_legal_terms() — verify LegalTerm nodes are loaded and queryable.
    """
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    db = _get_db()
    try:
        terms = db.find_legal_terms(keywords=kw_list, limit=limit)
    finally:
        db.close()

    return {
        "query": {"keywords": kw_list},
        "legal_terms_count": len(terms),
        "legal_terms": terms,
    }


@router.get("/db/stats")
def debug_db_stats():
    """Return node/relationship counts for each label in Neo4j."""
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    try:
        with driver.session() as session:
            node_counts = {
                row["label"]: row["count"]
                for row in session.run(
                    "MATCH (n) UNWIND labels(n) AS label "
                    "RETURN label, count(*) AS count ORDER BY count DESC"
                )
            }
            rel_counts = {
                row["type"]: row["count"]
                for row in session.run(
                    "MATCH ()-[r]->() "
                    "RETURN type(r) AS type, count(*) AS count ORDER BY count DESC"
                )
            }
    finally:
        driver.close()

    return {
        "neo4j_uri": settings.NEO4J_URI,
        "nodes": node_counts,
        "relationships": rel_counts,
        "total_nodes": sum(node_counts.values()),
        "total_relationships": sum(rel_counts.values()),
    }
