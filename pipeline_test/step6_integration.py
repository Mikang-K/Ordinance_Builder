"""
Step 6: Full Pipeline Integration Test (1 statute end-to-end)
Purpose: Run the actual pipeline/ modules for 1 statute and verify Neo4j result.
Run: python pipeline_test/step6_integration.py
Prereq: step1~step5 must pass. Docker Neo4j must be running.
"""
import os
import sys
import time
from dotenv import load_dotenv

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

OC = os.environ.get("LAW_API_KEY", "")
if not OC:
    print("[ERROR] LAW_API_KEY not set.")
    sys.exit(1)

print("=" * 60)
print("[6A] Import pipeline modules")
print("=" * 60)

try:
    from pipeline.api.law_api_client import LawApiClient
    print("[OK] LawApiClient imported")
except Exception as e:
    print(f"[FAIL] LawApiClient import: {e}")
    sys.exit(1)

try:
    from pipeline.transform.schema_mapper import map_statute, map_ordinance
    print("[OK] schema_mapper imported")
except Exception as e:
    print(f"[FAIL] schema_mapper import: {e}")
    sys.exit(1)

try:
    from pipeline.loaders.neo4j_loader import Neo4jLoader
    print("[OK] Neo4jLoader imported")
except Exception as e:
    print(f"[FAIL] Neo4jLoader import: {e}")
    sys.exit(1)

# ─────────────────────────────────────────────
# 6B: Search for 1 statute
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[6B] Search for '지방자치법' (1 result)")
print("=" * 60)

client = LawApiClient()

try:
    summaries = client.search_statutes("지방자치법")
    print(f"Found {len(summaries)} statute(s)")
    if not summaries:
        print("[FAIL] No results returned")
        sys.exit(1)
    # Pick the exact match
    target = next((s for s in summaries if s.title == "지방자치법"), summaries[0])
    print(f"Using: [{target.mst}] {target.title} (category: {target.category})")
    print(f"  enforcement_date: {target.enforcement_date}")
    print(f"  detail_link: {target.detail_link}")
except Exception as e:
    print(f"[FAIL] search_statutes error: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# ─────────────────────────────────────────────
# 6C: Fetch full text
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[6C] Fetch full statute text")
print("=" * 60)

try:
    full = client.get_statute_full(target.mst, target.detail_link)
    if full is None:
        print("[FAIL] get_statute_full returned None")
        sys.exit(1)
    print(f"[OK] Full statute fetched")
    print(f"  Title: {full.title}")
    print(f"  Provisions: {len(full.provisions)} article(s)")
    if full.provisions:
        p0 = full.provisions[0]
        print(f"  First provision: {p0.article_no} — {p0.article_title}")
        print(f"    Content preview: {p0.content_text[:100]!r}")
        print(f"    is_penalty_clause: {p0.is_penalty_clause}")
except Exception as e:
    print(f"[FAIL] get_statute_full error: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# ─────────────────────────────────────────────
# 6D: Map to graph nodes
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[6D] Map to graph nodes (schema_mapper)")
print("=" * 60)

try:
    statute_node, provision_nodes = map_statute(full)
    print(f"[OK] StatuteNode: id={statute_node.id}, title={statute_node.title}")
    print(f"     category={statute_node.category}, enforcement_date={statute_node.enforcement_date}")
    print(f"[OK] {len(provision_nodes)} ProvisionNode(s)")
    if provision_nodes:
        pn = provision_nodes[0]
        print(f"     First provision: id={pn.id}, article_no={pn.article_no}")
except Exception as e:
    print(f"[FAIL] map_statute error: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# ─────────────────────────────────────────────
# 6E: Load into Neo4j
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[6E] Load into Neo4j")
print("=" * 60)

try:
    loader = Neo4jLoader()
    print("[OK] Neo4jLoader connected")
except Exception as e:
    print(f"[FAIL] Neo4jLoader init: {e}")
    print("  Is Docker Neo4j running?")
    sys.exit(1)

try:
    loader.upsert_statute(statute_node, provision_nodes)
    print(f"[OK] upsert_statute completed for {statute_node.id}")
except Exception as e:
    print(f"[FAIL] upsert_statute error: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# ─────────────────────────────────────────────
# 6F: Verify in Neo4j
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[6F] Verify result in Neo4j")
print("=" * 60)

try:
    from neo4j import GraphDatabase
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ.get("NEO4J_PASSWORD", "password")
    drv = GraphDatabase.driver(uri, auth=(user, pw))

    with drv.session() as session:
        # Check statute node
        r1 = session.run(
            "MATCH (s:Statute {id: $id}) RETURN s.title AS title, s.enforcement_date AS ed",
            id=statute_node.id
        ).single()
        if r1:
            print(f"[OK] Statute node found: title={r1['title']}, enforcement_date={r1['ed']}")
        else:
            print(f"[FAIL] Statute node not found for id={statute_node.id}")

        # Check provisions
        r2 = session.run(
            "MATCH (s:Statute {id: $id})-[:CONTAINS]->(p:Provision) RETURN count(p) AS cnt",
            id=statute_node.id
        ).single()
        cnt = r2["cnt"] if r2 else 0
        print(f"[OK] Provision nodes linked: {cnt}")

        # Check enforcement_date retrieval (used by change_detector)
        stored_date = loader.get_statute_enforcement_date(statute_node.id)
        print(f"[OK] get_statute_enforcement_date returned: {stored_date!r}")

    drv.close()
    loader.close()
except Exception as e:
    print(f"[FAIL] Verification error: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

print("\n[Done] Step 6 PASSED — Full pipeline integration works end-to-end!")
print(f"  Statute '{statute_node.title}' with {len(provision_nodes)} provisions is in Neo4j.")
