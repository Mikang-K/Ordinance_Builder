"""
AuraDB 기존 노드에 새 관계만 MERGE하는 마이그레이션 스크립트.

노드 재적재 없이 LIMITS, REFERENCES, ENFORCES, PENALIZES, APPLIES_BY_ANALOGY,
SUPERIOR_TO 관계를 idempotent하게 구축합니다.

Usage (PowerShell):
    $env:NEO4J_URI      = "neo4j+s://da425acb.databases.neo4j.io"
    $env:NEO4J_USER     = "neo4j"
    $env:NEO4J_PASSWORD = "<password>"

    # 대상 건수만 확인 (실제 변경 없음)
    python -m pipeline.scripts.migrate_relations --dry-run

    # 특정 관계만
    python -m pipeline.scripts.migrate_relations --relations limits,references

    # 전체 실행
    python -m pipeline.scripts.migrate_relations

Options:
    --target    aura|local      (기본: aura — NEO4J_URI 환경변수 사용)
    --relations all|<콤마 목록>  (기본: all)
                가능 값: limits, references, enforces, penalizes,
                         applies_by_analogy, superior_to
    --dry-run                   대상 건수만 출력 후 종료
"""

import argparse
import logging
import time
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("migrate_relations")

# ---------------------------------------------------------------------------
# Dry-run count queries
# ---------------------------------------------------------------------------

_COUNT_LIMITS_CANDIDATES = """
MATCH (lt:LegalTerm)
MATCH (p:Provision)
WHERE size(p.content_text) > 20
  AND p.content_text CONTAINS lt.term_name
  AND NOT (p)-[:LIMITS]->(lt)
RETURN count(*) AS cnt
"""

_COUNT_REFERENCES_CANDIDATES = """
MATCH (src:Provision)
WHERE src.content_text IS NOT NULL
  AND src.content_text =~ '.*제\\d+조.*'
RETURN count(*) AS cnt
"""

_COUNT_ENFORCES_CANDIDATES = """
MATCH (o:Ordinance)-[:BASED_ON]->(s:Statute)
WHERE o.title CONTAINS '시행'
  AND NOT (o)-[:ENFORCES]->(s)
RETURN count(*) AS cnt
"""

_COUNT_PENALIZES_CANDIDATES = """
MATCH (penalty:Provision {is_penalty_clause: true})
WHERE penalty.content_text CONTAINS '위반'
  AND NOT (penalty)-[:PENALIZES]->()
RETURN count(*) AS cnt
"""

_COUNT_ANALOGY_MISSING = """
MATCH (o:Ordinance)-[:CONTAINS]->(p:Provision)
WHERE p.content_text CONTAINS '준용'
MATCH (s:Statute)
WHERE p.content_text CONTAINS s.title
  AND NOT (o)-[:APPLIES_BY_ANALOGY]->(s)
RETURN count(*) AS cnt
"""

_COUNT_SUPERIOR_MISSING = """
MATCH (o:Ordinance)-[:BASED_ON]->(s:Statute {category: '법률'})
WHERE NOT (s)-[:SUPERIOR_TO]->(o)
RETURN count(*) AS cnt
"""

_EXISTING_RELATIONS = """
MATCH ()-[r]->()
WHERE type(r) IN ['LIMITS','REFERENCES','ENFORCES','PENALIZES','APPLIES_BY_ANALOGY','SUPERIOR_TO']
RETURN type(r) AS rel, count(*) AS cnt
"""


def _run_dry_run(driver, relations: set[str]) -> None:
    logger.info("=== DRY-RUN 모드 — 실제 변경 없음 ===")

    with driver.session() as session:
        rows = [dict(r) for r in session.run(_EXISTING_RELATIONS)]
    existing = {r["rel"]: r["cnt"] for r in rows}
    logger.info("현재 존재하는 관계: %s", existing or "없음")

    counts = {}
    with driver.session() as session:
        if "limits" in relations:
            counts["LIMITS"] = session.run(_COUNT_LIMITS_CANDIDATES).single()["cnt"]
        if "references" in relations:
            counts["REFERENCES"] = session.run(_COUNT_REFERENCES_CANDIDATES).single()["cnt"]
        if "enforces" in relations:
            counts["ENFORCES"] = session.run(_COUNT_ENFORCES_CANDIDATES).single()["cnt"]
        if "penalizes" in relations:
            counts["PENALIZES"] = session.run(_COUNT_PENALIZES_CANDIDATES).single()["cnt"]
        if "applies_by_analogy" in relations:
            counts["APPLIES_BY_ANALOGY (미연결)"] = session.run(_COUNT_ANALOGY_MISSING).single()["cnt"]
        if "superior_to" in relations:
            counts["SUPERIOR_TO (미연결)"] = session.run(_COUNT_SUPERIOR_MISSING).single()["cnt"]

    print("\n" + "=" * 55)
    print("  migrate_relations.py DRY-RUN 결과")
    print("=" * 55)
    for rel, cnt in counts.items():
        print(f"  {rel:<30} 예상 처리: {cnt:>8,}건")
    print("=" * 55)
    print("  실행하려면 --dry-run 플래그를 제거하세요.")
    print("=" * 55 + "\n")


def run() -> None:
    parser = argparse.ArgumentParser(description="AuraDB 관계 마이그레이션")
    parser.add_argument("--target", choices=["aura", "local"], default="aura")
    parser.add_argument(
        "--relations",
        default="all",
        help="all 또는 콤마 구분 목록: limits,references,enforces,penalizes,applies_by_analogy,superior_to",
    )
    parser.add_argument("--dry-run", action="store_true", help="건수만 확인")
    args = parser.parse_args()

    all_relations = {"limits", "references", "enforces", "penalizes", "applies_by_analogy", "superior_to"}
    if args.relations == "all":
        relations = all_relations
    else:
        relations = {r.strip().lower() for r in args.relations.split(",")}
        unknown = relations - all_relations
        if unknown:
            parser.error(f"알 수 없는 관계: {unknown}. 가능 값: {all_relations}")

    # 환경변수 또는 pipeline.config에서 연결 정보 로드
    from pipeline.config import config as pipeline_config
    from neo4j import GraphDatabase

    uri  = os.getenv("NEO4J_URI")      or pipeline_config.neo4j_uri
    user = os.getenv("NEO4J_USER")     or pipeline_config.neo4j_user
    pwd  = os.getenv("NEO4J_PASSWORD") or pipeline_config.neo4j_password

    logger.info("DB 연결: %s (target=%s)", uri, args.target)
    driver = GraphDatabase.driver(uri, auth=(user, pwd))

    if args.dry_run:
        _run_dry_run(driver, relations)
        driver.close()
        return

    # 실제 마이그레이션
    from pipeline.loaders.neo4j_loader import Neo4jLoader

    # Neo4jLoader를 같은 연결로 초기화하기 위해 환경변수 임시 설정
    os.environ.setdefault("NEO4J_URI",      uri)
    os.environ.setdefault("NEO4J_USER",     user)
    os.environ.setdefault("NEO4J_PASSWORD", pwd)

    start = time.time()
    total_created = 0

    with Neo4jLoader() as loader:
        if "limits" in relations:
            logger.info("=== Phase A: LIMITS ===")
            loader.build_limits_relationships()

        if "references" in relations:
            logger.info("=== Phase B: REFERENCES ===")
            loader.build_references_relationships()

        if "enforces" in relations:
            logger.info("=== Phase C: ENFORCES ===")
            loader.build_enforces_relationships()

        if "penalizes" in relations:
            logger.info("=== Phase D: PENALIZES ===")
            loader.build_penalizes_relationships()

        if "applies_by_analogy" in relations:
            logger.info("=== Phase E: APPLIES_BY_ANALOGY 재확인 ===")
            loader.build_applies_by_analogy_relationships()

        if "superior_to" in relations:
            logger.info("=== Phase F: SUPERIOR_TO 재확인 ===")
            loader.build_superior_to_relationships()

    elapsed = time.time() - start
    logger.info("마이그레이션 완료 — %.1f초", elapsed)

    # 최종 관계 수 확인
    with driver.session() as session:
        rows = [dict(r) for r in session.run(_EXISTING_RELATIONS)]
    driver.close()

    print("\n" + "=" * 55)
    print("  migrate_relations.py 완료")
    print("=" * 55)
    for r in rows:
        print(f"  {r['rel']:<30} {r['cnt']:>10,}건")
    print(f"  총 소요 시간: {elapsed:.1f}초")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    run()
