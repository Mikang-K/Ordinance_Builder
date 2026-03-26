"""
Step 5: Neo4j Basic Connection & MERGE
Purpose: Verify Neo4j connection, auth, and that basic Cypher queries work.
Run: python pipeline_test/step5_neo4j_basic.py
Prereq: docker compose up -d (Neo4j must be running)
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD", "password")

try:
    from neo4j import GraphDatabase
except ImportError:
    print("[ERROR] neo4j package not installed.")
    print("  Run: pip install neo4j")
    sys.exit(1)

print("=" * 60)
print("[5A] Neo4j connection test")
print("=" * 60)
print(f"URI:  {NEO4J_URI}")
print(f"User: {NEO4J_USER}")

driver = None
try:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    driver.verify_connectivity()
    print("[OK] Connected to Neo4j")
except Exception as e:
    print(f"[FAIL] Connection error: {e}")
    print("  Is Docker Neo4j running? Try: docker compose up -d")
    sys.exit(1)

# ─────────────────────────────────────────────
# 5B: Basic MERGE
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[5B] Basic MERGE test")
print("=" * 60)

with driver.session() as session:
    result = session.run("""
        MERGE (n:_PipelineTest {id: 'test_001'})
        ON CREATE SET n.created = datetime(), n.value = 'hello'
        SET n.last_run = datetime()
        RETURN n.id AS id, n.value AS value, n.last_run AS ts
    """)
    record = result.single()
    print(f"[OK] Node: id={record['id']}, value={record['value']}")

# ─────────────────────────────────────────────
# 5C: UNWIND batch insert (used in neo4j_loader)
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[5C] UNWIND batch MERGE test (simulates provision insert)")
print("=" * 60)

test_provisions = [
    {"id": f"PROV_TEST_{i}", "article_no": f"제{i}조", "content": f"내용 {i}번"}
    for i in range(1, 6)
]

with driver.session() as session:
    result = session.run("""
        UNWIND $provisions AS prov
        MERGE (p:_PipelineTestProv {id: prov.id})
        SET p.article_no = prov.article_no, p.content = prov.content
        RETURN count(p) AS cnt
    """, provisions=test_provisions)
    cnt = result.single()["cnt"]
    print(f"[OK] Upserted {cnt} provision nodes")

# ─────────────────────────────────────────────
# 5D: Relationship creation
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[5D] Relationship MERGE test")
print("=" * 60)

with driver.session() as session:
    result = session.run("""
        MATCH (n:_PipelineTest {id: 'test_001'})
        MATCH (p:_PipelineTestProv)
        MERGE (n)-[:TEST_CONTAINS]->(p)
        RETURN count(p) AS cnt
    """)
    cnt = result.single()["cnt"]
    print(f"[OK] Created {cnt} TEST_CONTAINS relationships")

# ─────────────────────────────────────────────
# 5E: Cleanup test nodes
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[5E] Cleanup test nodes")
print("=" * 60)

with driver.session() as session:
    session.run("MATCH (n:_PipelineTest) DETACH DELETE n")
    session.run("MATCH (n:_PipelineTestProv) DETACH DELETE n")
    print("[OK] Test nodes deleted")

# ─────────────────────────────────────────────
# 5F: Check existing schema (constraints/indexes)
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[5F] Existing constraints and indexes")
print("=" * 60)

with driver.session() as session:
    try:
        result = session.run("SHOW CONSTRAINTS")
        constraints = list(result)
        if constraints:
            for c in constraints:
                print(f"  Constraint: {dict(c)}")
        else:
            print("  No constraints defined yet")
    except Exception as e:
        print(f"  [WARN] SHOW CONSTRAINTS not supported: {e}")

    try:
        result = session.run("SHOW INDEXES")
        indexes = [dict(r) for r in result if dict(r).get("type") != "LOOKUP"]
        if indexes:
            for idx in indexes:
                print(f"  Index: {idx.get('name')} on {idx.get('labelsOrTypes')}.{idx.get('properties')}")
        else:
            print("  No custom indexes defined yet")
    except Exception as e:
        print(f"  [WARN] SHOW INDEXES not supported: {e}")

driver.close()
print("\n[Done] Step 5 complete. Neo4j is working correctly.")
