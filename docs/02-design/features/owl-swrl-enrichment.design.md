# Design: OWL 온톨로지 보강 + SWRL 추론 구현 (owl-swrl-enrichment)

**작성일**: 2026-05-08  
**상태**: Design  
**단계**: Design  
**아키텍처**: Option C — 실용적 균형

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | `ordinance.rdf`는 구조 뼈대만 있고 OWL 시맨틱(레이블·역관계·전이성·SWRL)이 없어 Protégé 추론기 활용 불가. graph-relation-expansion 6개 관계가 AuraDB에 미적용 상태. SWRL 추론 패턴이 앱에 전혀 없어 위임 체계·위계·벌칙 체인 기반 법률 검증 불가 |
| **WHO** | legal_checker (간접 충돌·벌칙 체인), graph_retriever (위임 상속 경로), 온톨로지 관리자 |
| **RISK** | SUPERIOR_TO 체인 물질화 시 AuraDB 용량 초과 → dry-run 확인 후 결정 / Cypher path 쿼리 타임아웃 → LIMIT + 키워드 인덱스 / SWRL XML 파서 오류 → 네임스페이스 선언 검증 |
| **SUCCESS** | OWL 모든 속성에 rdfs:label/comment 존재 / SWRL 4규칙 OWL·Cypher 양쪽 구현 / AuraDB 6개 관계 MERGE 완료 / 기존 워크플로우 회귀 없음 |
| **SCOPE** | `ordinance.rdf`, `pipeline/scripts/migrate_relations.py`, `app/db/base.py`, `app/db/neo4j_db.py`, `app/db/mock_db.py`, `app/graph/nodes/legal_checker.py`, `app/graph/nodes/graph_retriever.py`, `app/prompts/legal_checker.py` |

---

## 1. 아키텍처 개요

### 1.1 Option C 핵심 원칙

- **OWL**: 완전한 시맨틱 선언 (label·comment·inverseOf·Transitive·SWRL) — 설계 명세서 역할
- **Cypher**: SWRL 규칙을 multi-hop path query로 구현 — 새 관계 타입 추가 없음
- **물질화 여부**: SUPERIOR_TO 전이 체인은 dry-run 건수 확인 후 결정
- **기존 패턴 준수**: `base.py` 추상 메서드 → `neo4j_db.py` 구현 패턴 유지

### 1.2 레이어별 변경 범위

```
[ordinance.rdf]          ← rdfs:label(ko/en)·comment·inverseOf·Transitive·SWRL 4규칙
        ↓
[migrate_relations.py]   ← 실행: AuraDB 기존 노드에 6개 관계 MERGE (S2 — 운영 작업)
        ↓
[base.py]                ← 4개 추상 메서드 추가
                            get_delegation_limits, get_hierarchy_chain,
                            get_conflict_chain, get_penalty_extension
[neo4j_db.py]            ← 4개 Cypher path query 구현
[mock_db.py]             ← 4개 stub 추가
        ↓
[graph_retriever.py]     ← get_delegation_limits → legal_basis 병합 (선택적, try/except)
[legal_checker.py]       ← get_hierarchy_chain·get_conflict_chain·get_penalty_extension
                            3개 메서드 결과를 프롬프트에 추가
[legal_checker.py prompt] ← 3개 섹션 추가
```

---

## 2. OWL 보강 설계 (`ordinance.rdf`)

### 2.1 네임스페이스 선언 추가

현재 `<rdf:RDF>` 요소에 다음 namespace를 추가해야 SWRL 구문이 유효합니다:

```xml
xmlns:swrl="http://www.w3.org/2003/11/swrl#"
xmlns:swrla="http://swrl.stanford.edu/ontologies/3.3/swrla.owl#"
xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"   <!-- 이미 존재하지만 확인 필요 -->
```

### 2.2 ObjectProperty 보강 템플릿

```xml
<owl:ObjectProperty rdf:about="...#위임하다">
    <rdfs:label xml:lang="ko">위임하다</rdfs:label>
    <rdfs:label xml:lang="en">delegates</rdfs:label>
    <rdfs:comment>상위법률이 조례 제정 권한을 위임함.
        Neo4j: DELEGATES (Statute → Ordinance)
        활용처: graph_retriever Phase 1 (DELEGATES 경로 최우선 탐색)
    </rdfs:comment>
    <owl:inverseOf rdf:resource="...#위임근거를_가지다"/>
</owl:ObjectProperty>
```

### 2.3 13개 ObjectProperty 보강 목록

| OWL 속성명 | 영문 레이블 | inverseOf | 특수 선언 | Neo4j 관계 |
|---|---|---|---|---|
| `위임하다` | delegates | `위임근거를_가지다` | — | DELEGATES |
| `위임근거를_가지다` | hasLegalBasis | `위임하다` | — | BASED_ON |
| `우위에_있다` | isSuperiorTo | `하위에_있다` (신규) | **Transitive** | SUPERIOR_TO |
| `상충하다` | conflictsWith | — | Symmetric 고려 | CONFLICTS_WITH |
| `준용하다` | appliesByAnalogy | — | — | APPLIES_BY_ANALOGY |
| `포함하다` | contains | — | Transitive | CONTAINS |
| `정의하다` | defines | — | — | DEFINES |
| `제한하다` | limits | — | — | LIMITS |
| `인용하다` | references | — | — | REFERENCES |
| `집행하다` | enforces | — | — | ENFORCES |
| `제재하다` | penalizes | — | — | PENALIZES |
| `수행주체이다` | hasAgent | — | — | (앱 미사용) |
| `유사하다` | isSimilarTo | — | Symmetric | SIMILAR_TO |

> `하위에_있다` (inferiorTo, INFERIOR_TO) 는 `우위에_있다`의 역관계로 새로 선언.

### 2.4 TransitiveObjectProperty 선언

```xml
<!-- 우위에_있다 — 법적 위계 전이성: 헌법 > 법률 > 시행령 > 조례 -->
<owl:TransitiveObjectProperty rdf:about="...#우위에_있다"/>

<!-- 포함하다 — 조문구조 포함 전이성: Statute > Provision > Paragraph > ... -->
<owl:TransitiveObjectProperty rdf:about="...#포함하다"/>
```

### 2.5 SWRL 4규칙 XML 구조

#### Rule 1 — 위임 상속 (DelegationInheritance)
```xml
<swrl:Imp rdf:about="...#DelegationInheritance">
    <rdfs:label>위임 상속: 상위법이 위임한 조례의 제한 범위를 상위법도 포괄함</rdfs:label>
    <swrla:enabled rdf:datatype="xsd:boolean">true</swrla:enabled>
    <swrl:body>
        <swrl:AtomList>
            <rdf:first>
                <swrl:ObjectPropertyAtom>
                    <swrl:propertyPredicate rdf:resource="...#위임하다"/>
                    <swrl:argument1><swrl:Variable rdf:about="urn:swrl:var#s"/></swrl:argument1>
                    <swrl:argument2><swrl:Variable rdf:about="urn:swrl:var#o"/></swrl:argument2>
                </swrl:ObjectPropertyAtom>
            </rdf:first>
            <rdf:rest>
                <swrl:AtomList>
                    <rdf:first>
                        <swrl:ObjectPropertyAtom>
                            <swrl:propertyPredicate rdf:resource="...#포함하다"/>
                            <swrl:argument1><swrl:Variable rdf:about="urn:swrl:var#o"/></swrl:argument1>
                            <swrl:argument2><swrl:Variable rdf:about="urn:swrl:var#p"/></swrl:argument2>
                        </swrl:ObjectPropertyAtom>
                    </rdf:first>
                    <rdf:rest>
                        <swrl:AtomList>
                            <rdf:first>
                                <swrl:ObjectPropertyAtom>
                                    <swrl:propertyPredicate rdf:resource="...#제한하다"/>
                                    <swrl:argument1><swrl:Variable rdf:about="urn:swrl:var#p"/></swrl:argument1>
                                    <swrl:argument2><swrl:Variable rdf:about="urn:swrl:var#lt"/></swrl:argument2>
                                </swrl:ObjectPropertyAtom>
                            </rdf:first>
                            <rdf:rest rdf:resource="http://www.w3.org/1999/02/22-rdf-syntax-ns#nil"/>
                        </swrl:AtomList>
                    </rdf:rest>
                </swrl:AtomList>
            </rdf:rest>
        </swrl:AtomList>
    </swrl:body>
    <swrl:head>
        <swrl:AtomList>
            <rdf:first>
                <swrl:ObjectPropertyAtom>
                    <!-- 간접 제한 — Cypher에서 3홉 path로 구현 -->
                    <swrl:propertyPredicate rdf:resource="...#제한하다"/>
                    <swrl:argument1><swrl:Variable rdf:about="urn:swrl:var#s"/></swrl:argument1>
                    <swrl:argument2><swrl:Variable rdf:about="urn:swrl:var#lt"/></swrl:argument2>
                </swrl:ObjectPropertyAtom>
            </rdf:first>
            <rdf:rest rdf:resource="http://www.w3.org/1999/02/22-rdf-syntax-ns#nil"/>
        </swrl:AtomList>
    </swrl:head>
</swrl:Imp>
```

> Rule 2 (위계 전이성), Rule 3 (충돌 연쇄), Rule 4 (벌칙 범위 확장)는 동일 패턴으로 선언.
> Rule 2는 `owl:TransitiveObjectProperty` 선언으로 커버되므로 SWRL에서는 설명 주석으로 대체 가능.

---

## 3. AuraDB 적용 설계 (S2 — 운영 작업)

### 3.1 dry-run 실행 순서

```powershell
# Step 1: 현재 관계 건수 + 신규 예상 건수 확인
$env:NEO4J_URI      = "neo4j+s://da425acb.databases.neo4j.io"
$env:NEO4J_USER     = "neo4j"
$env:NEO4J_PASSWORD = "<password>"
python -m pipeline.scripts.migrate_relations --dry-run

# Step 2: SUPERIOR_TO 전이 체인 건수 별도 확인
# (dry-run 결과에서 SUPERIOR_TO 기존 건수 < 100,000이면 물질화 고려)
```

### 3.2 실행 판단 기준

| 조건 | 결정 |
|------|------|
| 모든 관계 예상 건수 < 500,000 | 전체 실행 `python -m pipeline.scripts.migrate_relations` |
| 특정 관계 건수 초과 | 관계 분할 실행 `--relations limits,references` 등 |
| SUPERIOR_TO 기존 건수 < 50,000 | 위계 전이성 물질화 고려 (S3 `get_hierarchy_chain` 결과 보완) |

---

## 4. DB 레이어 설계 (S3)

### 4.1 신규 추상 메서드 4개 (`app/db/base.py`)

| 메서드 | SWRL 규칙 | 반환 키 |
|--------|-----------|---------|
| `get_delegation_limits(keywords, limit=10)` | Rule 1 위임 상속 | `statute_id`, `statute_title`, `term_name`, `definition`, `provision_article` |
| `get_hierarchy_chain(keywords, max_depth=3, limit=10)` | Rule 2 위계 전이성 | `statute_id`, `statute_title`, `statute_category`, `ordinance_id`, `ordinance_title`, `depth` |
| `get_conflict_chain(keywords, limit=10)` | Rule 3 충돌 연쇄 | `statute_article`, `statute_content`, `ordinance_article`, `ordinance_content`, `conflict_term` |
| `get_penalty_extension(keywords, limit=10)` | Rule 4 벌칙 범위 확장 | `src_article`, `ext_article`, `ext_content` |

### 4.2 Cypher 구현 설계 (`app/db/neo4j_db.py`)

```cypher
-- get_delegation_limits (Rule 1: 위임 상속)
MATCH (s:Statute)-[:DELEGATES]->(o:Ordinance)
WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw)
MATCH (o)-[:CONTAINS]->(p:Provision)-[:LIMITS]->(lt:LegalTerm)
RETURN DISTINCT
       s.id           AS statute_id,
       s.title        AS statute_title,
       lt.term_name   AS term_name,
       lt.definition  AS definition,
       p.article_no   AS provision_article
LIMIT $limit

-- get_hierarchy_chain (Rule 2: 위계 전이성)
MATCH path = (s:Statute)-[:SUPERIOR_TO*1..$max_depth]->(o:Ordinance)
WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw OR s.title CONTAINS kw)
RETURN DISTINCT
       s.id           AS statute_id,
       s.title        AS statute_title,
       s.category     AS statute_category,
       o.id           AS ordinance_id,
       o.title        AS ordinance_title,
       length(path)   AS depth
ORDER BY depth, s.title
LIMIT $limit

-- get_conflict_chain (Rule 3: 충돌 연쇄)
MATCH (s:Statute)-[:SUPERIOR_TO]->(o:Ordinance)
WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw)
MATCH (s)-[:CONTAINS]->(sp:Provision)-[:LIMITS]->(lt:LegalTerm)
MATCH (o)-[:CONTAINS]->(op:Provision)-[:LIMITS]->(lt)
RETURN DISTINCT
       sp.article_no  AS statute_article,
       sp.content_text AS statute_content,
       op.article_no  AS ordinance_article,
       op.content_text AS ordinance_content,
       lt.term_name   AS conflict_term
LIMIT $limit

-- get_penalty_extension (Rule 4: 벌칙 범위 확장)
MATCH (p1:Provision)-[:PENALIZES]->(p2:Provision)-[:PENALIZES]->(p3:Provision)
WHERE ANY(kw IN $keywords WHERE p1.content_text CONTAINS kw)
RETURN DISTINCT
       p1.article_no  AS src_article,
       p3.article_no  AS ext_article,
       p3.content_text AS ext_content
LIMIT $limit
```

### 4.3 MockGraphDB 스텁

```python
def get_delegation_limits(self, keywords, limit=10):
    return []  # LIMITS + DELEGATES 파이프라인 구축 후에만 값 반환

def get_hierarchy_chain(self, keywords, max_depth=3, limit=10):
    return []  # SUPERIOR_TO 파이프라인 구축 후에만 값 반환

def get_conflict_chain(self, keywords, limit=10):
    return []  # SUPERIOR_TO + LIMITS 파이프라인 구축 후에만 값 반환

def get_penalty_extension(self, keywords, limit=10):
    return []  # PENALIZES 파이프라인 구축 후에만 값 반환
```

---

## 5. 워크플로우 통합 설계 (S4)

### 5.1 graph_retriever.py — 위임 상속 경로 병합

기존 APPLIES_BY_ANALOGY 추가 패턴과 동일하게 try/except로 선택적 추가:

```python
# S3 이후 — DELEGATES → LIMITS 3홉 경로로 legal_basis 보강 (Rule 1)
try:
    delegation_results = db.get_delegation_limits(keywords=keywords)
    existing = {(r["statute_id"], r.get("provision_article")) for r in legal_basis}
    for r in delegation_results:
        key = (r["statute_id"], r.get("provision_article"))
        if key not in existing:
            legal_basis.append({
                "statute_id": r["statute_id"],
                "statute_title": r["statute_title"],
                "provision_article": r.get("provision_article", ""),
                "provision_content": f"[위임 상속 용어] {r['term_name']}: {r.get('definition', '')}",
                "relation_type": "DELEGATION_CHAIN",
            })
            existing.add(key)
except Exception as e:
    logger.debug("위임 상속 경로 생략: %s", e)
```

### 5.2 legal_checker.py — 3개 SWRL 쿼리 추가

기존 `superior_provisions`, `penalty_chain` 이후에 추가:

```python
# Rule 2: 위계 전이성 — 조례가 속하는 위계 체계 전체 파악
hierarchy_chain: list[dict] = []
if db and keywords:
    try:
        hierarchy_chain = db.get_hierarchy_chain(keywords=keywords)
    except Exception as exc:
        logger.debug("get_hierarchy_chain 생략: %s", exc)

# Rule 3: 충돌 연쇄 — 동일 법률 용어를 상위법과 조례가 동시 제한 시 충돌 가능성
conflict_chain: list[dict] = []
if db and keywords:
    try:
        conflict_chain = db.get_conflict_chain(keywords=keywords)
    except Exception as exc:
        logger.debug("get_conflict_chain 생략: %s", exc)

# Rule 4: 벌칙 범위 확장 — 2단계 벌칙 체인으로 간접 제재 범위 파악
penalty_extension: list[dict] = []
if db and keywords:
    try:
        penalty_extension = db.get_penalty_extension(keywords=keywords)
    except Exception as exc:
        logger.debug("get_penalty_extension 생략: %s", exc)
```

### 5.3 legal_checker 프롬프트 — 3개 섹션 추가 (`app/prompts/legal_checker.py`)

`build_legal_checker_human` 시그니처 확장:

```python
def build_legal_checker_human(
    draft_text: str,
    legal_basis: list,
    legal_terms: list | None = None,
    superior_provisions: list | None = None,   # 기존 (SUPERIOR_TO 조항)
    penalty_chain: list | None = None,          # 기존 (직접 PENALIZES)
    hierarchy_chain: list | None = None,        # 신규 Rule 2
    conflict_chain: list | None = None,         # 신규 Rule 3
    penalty_extension: list | None = None,      # 신규 Rule 4
) -> str:
```

신규 프롬프트 섹션:

```
## 위계 체계 (SWRL Rule 2 — 위계 전이성)
  [헌법] → [○○법률] (depth=2) → [현재 조례 영역]
  검토: 위계 상단 법령의 기본권·위임 범위 준수 여부

## 동일 용어 충돌 위험 (SWRL Rule 3 — 충돌 연쇄)
  상위법 제○조 LIMITS [용어명] ↔ 조례 제○조 LIMITS [용어명]
  검토: 동일 용어에 대한 상위법·조례 간 정의 충돌

## 간접 제재 범위 (SWRL Rule 4 — 벌칙 범위 확장)
  제재조항1 → 제재조항2 → 간접제재대상
  검토: 다단계 벌칙 체계의 적정성
```

---

## 6. 데이터 플로우

```
[사용자 채팅 입력]
      ↓
[graph_retriever]
  ├── find_legal_basis()           기존 DELEGATES·BASED_ON·키워드
  ├── get_analogy_applications()   기존 APPLIES_BY_ANALOGY (graph-relation-expansion)
  └── get_delegation_limits()      신규 Rule 1 (DELEGATES→CONTAINS→LIMITS 3홉)
      → legal_basis 에 병합
      ↓
[drafting_agent / legal_checker]
  legal_checker 추가 쿼리:
  ├── get_superior_statute_provisions()  기존 (SUPERIOR_TO 조항)
  ├── get_penalty_chain()                기존 (직접 PENALIZES)
  ├── get_hierarchy_chain()              신규 Rule 2
  ├── get_conflict_chain()               신규 Rule 3
  └── get_penalty_extension()            신규 Rule 4
      → build_legal_checker_human() 프롬프트에 7개 섹션 포함
```

---

## 7. 인터페이스 계약

### 7.1 `get_delegation_limits` 반환 스키마

```python
[
    {
        "statute_id": str,
        "statute_title": str,
        "term_name": str,
        "definition": str,
        "provision_article": str,
    }
]
```

### 7.2 `get_hierarchy_chain` 반환 스키마

```python
[
    {
        "statute_id": str,
        "statute_title": str,
        "statute_category": str,   # '법률', '시행령', '부령' 등
        "ordinance_id": str,
        "ordinance_title": str,
        "depth": int,              # 위계 단계 수 (1 = 직접 상위)
    }
]
```

### 7.3 `get_conflict_chain` 반환 스키마

```python
[
    {
        "statute_article": str,
        "statute_content": str,
        "ordinance_article": str,
        "ordinance_content": str,
        "conflict_term": str,      # 충돌하는 법률 용어명
    }
]
```

### 7.4 `get_penalty_extension` 반환 스키마

```python
[
    {
        "src_article": str,    # 원 벌칙 조항
        "ext_article": str,    # 2단계 간접 제재 대상 조항
        "ext_content": str,
    }
]
```

---

## 8. 테스트 계획

| 레벨 | 항목 | 방법 |
|------|------|------|
| L1 — OWL 구문 검증 | SWRL XML 파싱 오류 없음 | Protégé 열기 또는 `python -c "from rdflib import Graph; g=Graph(); g.parse('ordinance.rdf')"` |
| L1 — OWL 내용 검증 | 모든 속성에 rdfs:label 존재 | rdflib 쿼리로 레이블 없는 속성 개수 = 0 확인 |
| L2 — AuraDB MERGE 결과 | 6개 관계 건수 > 0 | `migrate_relations.py` 출력 확인 |
| L2 — SWRL Cypher 성능 | 4개 메서드 < 3초 | `time python -c "from app.db.neo4j_db import Neo4jGraphDB; ..."` |
| L3 — 워크플로우 회귀 없음 | legal_checker 정상 실행 | 기존 draft로 법률 검증 수행 + 오류 없음 확인 |
| L3 — SWRL 섹션 프롬프트 반영 | 프롬프트에 위계·충돌·벌칙 섹션 포함 | `build_legal_checker_human` 출력 문자열 검증 |

---

## 9. 위험 및 대응

| 위험 | 대응 |
|------|------|
| SWRL AtomList 중첩 XML 오류 | rdflib 파싱 테스트로 사전 검증 |
| `get_hierarchy_chain` `*1..3` 홉 전체 스캔 | `keywords` 파라미터로 조례 필터링 선행 + LIMIT |
| `get_conflict_chain` LIMITS 관계 미구축 시 빈 결과 | try/except → 빈 리스트 반환 (기존 패턴 유지) |
| AuraDB migrate 중단 시 재실행 | MERGE idempotent → 재실행 안전 |

---

## 10. 의존성

- **선행 조건**: graph-relation-expansion S1~S4 완료 (이미 완료됨)
- **runtime 의존성**: `rdflib` (OWL 검증용, pipeline 단계에서만 사용), `neo4j` 드라이버 (기존)
- **새 pip 패키지**: `rdflib` (파이프라인 검증 전용 — app runtime에는 불필요)

---

## 11. 구현 가이드

### 11.1 구현 순서

```
S1: ordinance.rdf 보강
  1. <rdf:RDF> 요소에 swrl·swrla 네임스페이스 추가
  2. 13개 ObjectProperty에 rdfs:label(ko/en) + rdfs:comment 추가
  3. inverseOf 선언: 위임하다↔위임근거를_가지다, 우위에_있다·하위에_있다 신규
  4. TransitiveObjectProperty: 우위에_있다, 포함하다
  5. SWRL 4규칙 XML 블록 추가
  6. rdflib 파싱 테스트

S2: AuraDB 적용 (운영 작업)
  1. PowerShell $env: 환경변수 설정
  2. --dry-run 실행 → 건수 확인
  3. 전체 실행 → 완료 확인

S3: DB 레이어
  1. base.py: 4개 추상 메서드 + 독스트링
  2. neo4j_db.py: 4개 Cypher 구현
  3. mock_db.py: 4개 stub
  4. Python import 테스트

S4: 워크플로우 통합
  1. graph_retriever.py: get_delegation_limits 추가
  2. legal_checker.py: 3개 SWRL 메서드 호출 추가
  3. legal_checker prompt: 3개 섹션 추가 + 시그니처 확장
  4. CLAUDE.md: §OWL 온톨로지 보강 내역 기록
```

### 11.2 핵심 파일 목록

| 파일 | 변경 유형 | 예상 라인 수 |
|------|----------|------------|
| `ordinance.rdf` | 수정 | +200~250줄 (label·comment·SWRL) |
| `app/db/base.py` | 수정 | +60줄 |
| `app/db/neo4j_db.py` | 수정 | +80줄 |
| `app/db/mock_db.py` | 수정 | +25줄 |
| `app/graph/nodes/graph_retriever.py` | 수정 | +15줄 |
| `app/graph/nodes/legal_checker.py` | 수정 | +30줄 |
| `app/prompts/legal_checker.py` | 수정 | +40줄 |
| `CLAUDE.md` | 수정 | +15줄 |

### 11.3 Session Guide

| 모듈 | 세션 | 예상 시간 | 독립 실행 가능 |
|------|------|----------|--------------|
| module-1: OWL 보강 | S1 | 1.5h | 독립 가능 (코드 무관) |
| module-2: AuraDB 적용 | S2 | 0.5h | S1 이후 권장 (검증 기반) |
| module-3: DB 레이어 | S3 | 0.75h | module-2 이후 권장 |
| module-4: 워크플로우 통합 | S4 | 0.75h | module-3 완료 후 |

**권장 분할**: S1+S2 → S3+S4 (2세션)

```
# 세션별 실행
/pdca do owl-swrl-enrichment --scope module-1,module-2
/pdca do owl-swrl-enrichment --scope module-3,module-4
```
