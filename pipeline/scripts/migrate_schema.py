"""
Schema migration script — apply OWL ontology (ordinance.rdf) to Neo4j.

Run once (idempotent) after docker compose up -d, before or after initial_load.
Existing data is preserved; only constraints, indexes, and derived relationships
are added.

Ontology mapping (ordinance.rdf OWL → Neo4j):
  Classes:
    조 (Article)    → Provision  (existing)
    항 (Paragraph)  → Paragraph  (new label)
    호 (Item)       → Item       (new label)
    목 (SubItem)    → SubItem    (new label)
    법적개념        → LegalTerm  (existing)
    권리주체        → LegalTerm:RightsSubject  (multi-label)
    법적행위        → LegalTerm:LegalAction    (multi-label)
    객체            → LegalTerm:LegalObject    (multi-label)

  Relationships:
    위임하다        → DELEGATES            (Statute → Ordinance)
    준용하다        → APPLIES_BY_ANALOGY   (Ordinance → Statute)
    정의하다        → DEFINES              (Provision → LegalTerm)
    상충하다        → CONFLICTS_WITH       (Ordinance → Provision)
    수행주체이다    → HAS_SUBJECT          (LegalAction → RightsSubject)

Usage:
    cd d:/Project/Ordinance_Builder
    python -m pipeline.scripts.migrate_schema
"""

import logging

from neo4j import GraphDatabase

from pipeline.config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("migrate_schema")

# ---------------------------------------------------------------------------
# Constraints — IF NOT EXISTS makes them idempotent
# ---------------------------------------------------------------------------

_CONSTRAINTS = [
    # Existing nodes (ensure they are declared)
    "CREATE CONSTRAINT statute_id IF NOT EXISTS FOR (s:Statute) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT provision_id IF NOT EXISTS FOR (p:Provision) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT ordinance_id IF NOT EXISTS FOR (o:Ordinance) REQUIRE o.id IS UNIQUE",
    "CREATE CONSTRAINT legal_term_name IF NOT EXISTS FOR (lt:LegalTerm) REQUIRE lt.term_name IS UNIQUE",
    # New article-structure nodes (OWL: 항, 호, 목)
    "CREATE CONSTRAINT paragraph_id IF NOT EXISTS FOR (pg:Paragraph) REQUIRE pg.id IS UNIQUE",
    "CREATE CONSTRAINT item_id IF NOT EXISTS FOR (it:Item) REQUIRE it.id IS UNIQUE",
    "CREATE CONSTRAINT subitem_id IF NOT EXISTS FOR (si:SubItem) REQUIRE si.id IS UNIQUE",
]

# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

_INDEXES = [
    "CREATE INDEX provision_article_no IF NOT EXISTS FOR (p:Provision) ON (p.article_no)",
    "CREATE INDEX paragraph_seq IF NOT EXISTS FOR (pg:Paragraph) ON (pg.seq)",
    "CREATE INDEX item_seq IF NOT EXISTS FOR (it:Item) ON (it.seq)",
]

_FULLTEXT_INDEXES = [
    (
        "provision_fulltext",
        "CREATE FULLTEXT INDEX provision_fulltext IF NOT EXISTS "
        "FOR (p:Provision) ON EACH [p.content_text, p.article_title]",
    ),
    (
        "paragraph_fulltext",
        "CREATE FULLTEXT INDEX paragraph_fulltext IF NOT EXISTS "
        "FOR (pg:Paragraph) ON EACH [pg.content_text]",
    ),
]

# ---------------------------------------------------------------------------
# Relationship builders (ontology-derived)
# ---------------------------------------------------------------------------

# 위임하다: Statute → Ordinance (inverse of BASED_ON, which already exists)
_BUILD_DELEGATES = """
MATCH (o:Ordinance)-[:BASED_ON]->(s:Statute)
MERGE (s)-[:DELEGATES]->(o)
"""

# 준용하다: Ordinance → Statute (text pattern: '준용')
_BUILD_APPLIES_BY_ANALOGY = """
MATCH (o:Ordinance)-[:CONTAINS]->(p:Provision)
WHERE p.content_text CONTAINS '준용'
WITH o, p
MATCH (s:Statute)
WHERE p.content_text CONTAINS s.title
  AND NOT (o)-[:APPLIES_BY_ANALOGY]->(s)
MERGE (o)-[:APPLIES_BY_ANALOGY]->(s)
"""

# 정의하다: Provision → LegalTerm
# Targets definition articles (article_title '정의' or article_no '제2조')
_BUILD_DEFINES = """
MATCH (p:Provision)
WHERE p.article_title CONTAINS '정의' OR p.article_no = '제2조'
WITH p
MATCH (lt:LegalTerm)
WHERE p.content_text CONTAINS lt.term_name
MERGE (p)-[:DEFINES]->(lt)
"""

# 상충하다: Ordinance → Provision (heuristic: penalty provision + shared keywords)
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

# LegalTerm subtype labeling (OWL: 권리주체, 법적행위, 객체)
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

# HAS_SUBJECT: LegalAction → RightsSubject (co-occurrence heuristic)
_BUILD_HAS_SUBJECT = """
MATCH (la:LegalAction), (rs:RightsSubject)
WHERE EXISTS {
    MATCH (p:Provision)
    WHERE p.content_text CONTAINS la.term_name
      AND p.content_text CONTAINS rs.term_name
}
MERGE (la)-[:HAS_SUBJECT]->(rs)
"""


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run() -> None:
    driver = GraphDatabase.driver(
        config.neo4j_uri,
        auth=(config.neo4j_user, config.neo4j_password),
    )

    try:
        with driver.session() as session:
            # 1. Constraints
            logger.info("=== Applying constraints ===")
            for cypher in _CONSTRAINTS:
                session.run(cypher)
                logger.info("  OK: %s", cypher[:60])

            # 2. Indexes
            logger.info("=== Applying indexes ===")
            for cypher in _INDEXES:
                session.run(cypher)
                logger.info("  OK: %s", cypher[:60])

            for name, cypher in _FULLTEXT_INDEXES:
                session.run(cypher)
                logger.info("  OK fulltext: %s", name)

            # 3. Ontology-derived relationships (only if data exists)
            logger.info("=== Building ontology relationships ===")

            result = session.run(_BUILD_DELEGATES)
            summary = result.consume()
            logger.info("DELEGATES: +%d", summary.counters.relationships_created)

            result = session.run(_BUILD_APPLIES_BY_ANALOGY)
            summary = result.consume()
            logger.info("APPLIES_BY_ANALOGY: +%d", summary.counters.relationships_created)

            result = session.run(_BUILD_DEFINES)
            summary = result.consume()
            logger.info("DEFINES: +%d", summary.counters.relationships_created)

            # 4. LegalTerm subtype labels
            logger.info("=== Classifying LegalTerm subtypes ===")
            for cypher, label in [
                (_LABEL_RIGHTS_SUBJECTS, "RightsSubject"),
                (_LABEL_LEGAL_ACTIONS, "LegalAction"),
                (_LABEL_LEGAL_OBJECTS, "LegalObject"),
            ]:
                result = session.run(cypher)
                summary = result.consume()
                logger.info("%s: %d nodes labeled", label, summary.counters.labels_added)

            result = session.run(_BUILD_HAS_SUBJECT)
            summary = result.consume()
            logger.info("HAS_SUBJECT: +%d", summary.counters.relationships_created)

            # 5. CONFLICTS_WITH (last — depends on all other relationships)
            result = session.run(_BUILD_CONFLICTS_WITH)
            summary = result.consume()
            logger.info("CONFLICTS_WITH: +%d", summary.counters.relationships_created)

        logger.info("Schema migration complete.")

    finally:
        driver.close()


if __name__ == "__main__":
    run()
