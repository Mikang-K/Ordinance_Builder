# Plan: OWL 온톨로지 보강 + SWRL 추론 구현 (owl-swrl-enrichment)

**작성일**: 2026-05-08  
**상태**: Planning  
**단계**: Plan

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **문제** | `ordinance.rdf`는 클래스·속성 구조만 존재하고 rdfs:label·rdfs:comment가 없어 Protégé에서 가독성이 낮으며, inverseOf·TransitiveProperty 등 OWL 시맨틱이 선언되지 않아 추론기가 암묵적 지식을 도출하지 못함. 또한 graph-relation-expansion에서 추가한 6개 관계가 AuraDB 현재 데이터에 아직 적용되지 않았고, SWRL로 표현 가능한 위임 상속·위계 전이성·충돌 연쇄·벌칙 범위 확장 추론이 앱에서 전혀 활용되지 않고 있음 |
| **해결** | ① `ordinance.rdf`에 rdfs:label(한/영)·rdfs:comment·inverseOf·TransitiveProperty·SWRL 규칙 추가 → ② `migrate_relations.py`로 AuraDB에 6개 관계 MERGE → ③ SWRL 4패턴을 Cypher 다중 홉 쿼리로 구현해 앱 DB 레이어에 추가 → ④ legal_checker·graph_retriever에 연결 |
| **기능 UX 효과** | 법률 검증 시 2-3단계 위계·위임 체계를 자동 추적해 간접 충돌 감지 / 벌칙 조항 범위를 체인으로 확장해 누락 제재 경고 / QA 패널 답변에 위계 추론 근거 포함 |
| **핵심 가치** | OWL 온톨로지를 설계 문서 → 실행 가능한 추론 명세서로 격상하고, neosemantics 없이도 SWRL 의미론을 Cypher로 완전 구현 |

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | graph-relation-expansion으로 관계 골격은 완성됐지만 OWL 자체의 시맨틱 풍부함(레이블·역관계·추론 규칙)이 없어 법령 그래프의 잠재력이 설계 문서 수준에 머물고 있음 |
| **WHO** | legal_checker (간접 충돌 감지), graph_retriever (위임·위계 경로 탐색), 온톨로지 유지보수 담당자 |
| **RISK** | ① 위계 전이성 물질화(SUPERIOR_TO 체인) 시 AuraDB 8GB 용량 초과 가능 → 건수 확인 후 결정 ② SWRL Cypher 쿼리의 다중 홉 스캔이 느릴 수 있음 → `LIMIT`·인덱스로 제어 ③ neosemantics 미설치로 RDF 직접 임포트 불가 → Cypher-only 전략으로 대응 |
| **SUCCESS** | OWL 모든 속성에 rdfs:label/comment 존재 / SWRL 4규칙 OWL 파일에 선언 + Cypher 구현 완료 / AuraDB 6개 관계 MERGE 완료 / 기존 워크플로우 회귀 없음 |
| **SCOPE** | `ordinance.rdf`, `pipeline/scripts/migrate_relations.py`, `app/db/base.py`, `app/db/neo4j_db.py`, `app/db/mock_db.py`, `app/graph/nodes/legal_checker.py`, `app/graph/nodes/graph_retriever.py`. 프론트엔드 변경 없음 |

---

## 1. 현황 분석

### 1.1 OWL 현재 상태

| 항목 | 현재 | 목표 |
|------|------|------|
| ObjectProperty 수 | 13개 (구조 선언만) | 13개 + 레이블·주석·시맨틱 속성 |
| rdfs:label | 없음 | 한국어·영어 쌍 |
| rdfs:comment | 없음 | Neo4j 관계 매핑 + 활용처 명시 |
| inverseOf | 없음 | 위임하다↔위임근거를_가지다, 집행하다↔역집행, 우위에_있다 역관계 |
| TransitiveProperty | 없음 | 우위에_있다 (법적 위계 체계 전이성) |
| SWRL 규칙 | 없음 | 4개 규칙 선언 |

### 1.2 SWRL 4패턴 정의

| 규칙명 | SWRL 표현 | Cypher 구현 전략 |
|--------|-----------|-----------------|
| **위임 상속** | `위임하다(?s, ?o) ∧ 포함하다(?o, ?p) ∧ 제한하다(?p, ?lt) → 위임하다(?s, ?lt_scope)` | `(s)-[:DELEGATES]->(o)-[:CONTAINS]->(p)-[:LIMITS]->(lt)` 3홉 경로 |
| **위계 전이성** | `우위에_있다(?a, ?b) ∧ 우위에_있다(?b, ?c) → 우위에_있다(?a, ?c)` | Cypher `MATCH (a)-[:SUPERIOR_TO*2..4]->(c)` 물질화 or 경로 쿼리 |
| **충돌 연쇄** | `우위에_있다(?s, ?o) ∧ 제한하다(?p, ?lt) ∧ 포함하다(?s, ?sp) ∧ 제한하다(?sp, ?lt) → 상충하다(?o, ?s)` | legal_checker에서 SUPERIOR_TO + LIMITS 조합 쿼리 |
| **벌칙 범위 확장** | `제재하다(?p1, ?p2) ∧ 제재하다(?p2, ?p3) → 제재하다(?p1, ?p3)` | `(p1)-[:PENALIZES*2]->(p3)` 2홉 경로 |

### 1.3 AuraDB 적용 현황

| 관계 | 파이프라인 빌더 | AuraDB 실제 적재 |
|------|----------------|-----------------|
| LIMITS | ✓ (graph-relation-expansion) | **미실행** |
| REFERENCES | ✓ | **미실행** |
| ENFORCES | ✓ | **미실행** |
| PENALIZES | ✓ | **미실행** |
| APPLIES_BY_ANALOGY | ✓ (기존) | **미실행 (재확인 필요)** |
| SUPERIOR_TO | ✓ (기존) | **미실행 (재확인 필요)** |

---

## 2. 요구사항 정의

### 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-01 | `ordinance.rdf` 모든 ObjectProperty에 rdfs:label(한/영) + rdfs:comment 추가 | 필수 |
| FR-02 | inverseOf 선언: 위임하다↔위임근거를_가지다 / 우위에_있다 역관계 / 집행하다 역관계 | 필수 |
| FR-03 | TransitiveObjectProperty 선언: 우위에_있다 | 필수 |
| FR-04 | SWRL 4규칙 OWL 파일에 형식 선언 | 필수 |
| FR-05 | AuraDB — `migrate_relations.py` 실행해 6개 관계 MERGE + 결과 확인 | 필수 |
| FR-06 | DB 레이어 — 위임 상속 경로 메서드 `get_delegation_limits()` 추가 | 중요 |
| FR-07 | DB 레이어 — 위계 전이성 쿼리 `get_hierarchy_chain()` 추가 | 중요 |
| FR-08 | DB 레이어 — 충돌 연쇄 감지 `get_conflict_chain()` 추가 | 중요 |
| FR-09 | DB 레이어 — 벌칙 범위 확장 `get_penalty_extension()` 추가 | 보통 |
| FR-10 | legal_checker — FR-06~09 결과를 프롬프트에 반영 | 중요 |
| FR-11 | graph_retriever — 위임 상속 경로를 legal_basis에 병합 | 중요 |

### 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NFR-01 | SWRL Cypher 쿼리 응답 < 3초 (LIMIT + 인덱스 활용) |
| NFR-02 | AuraDB 8GB 한도 유지 (위계 전이성 물질화 전 건수 확인 필수) |
| NFR-03 | 기존 워크플로우 응답 회귀 없음 (try/except 패턴 유지) |

---

## 3. 기술 설계 방향

### 3.1 OWL 보강 구조 (S1)

```xml
<!-- inverseOf 예시 -->
<owl:ObjectProperty rdf:about="#위임하다">
  <rdfs:label xml:lang="ko">위임하다</rdfs:label>
  <rdfs:label xml:lang="en">delegates</rdfs:label>
  <rdfs:comment>상위법률이 조례 제정 권한을 위임함 (Neo4j: DELEGATES)</rdfs:comment>
  <owl:inverseOf rdf:resource="#위임근거를_가지다"/>
</owl:ObjectProperty>

<!-- Transitive 예시 -->
<owl:TransitiveObjectProperty rdf:about="#우위에_있다"/>

<!-- SWRL 위계 전이성 규칙 예시 -->
<swrl:Imp rdf:about="#HierarchyTransitivity">
  <swrl:body>
    <swrl:AtomList>
      <swrl:ObjectPropertyAtom>
        <swrl:propertyPredicate rdf:resource="#우위에_있다"/>
        <swrl:argument1 rdf:resource="urn:swrl:var#a"/>
        <swrl:argument2 rdf:resource="urn:swrl:var#b"/>
      </swrl:ObjectPropertyAtom>
      <!-- ... b 우위에_있다 c -->
    </swrl:AtomList>
  </swrl:body>
  <swrl:head><!-- a 우위에_있다 c --></swrl:head>
</swrl:Imp>
```

### 3.2 Cypher SWRL 구현 패턴 (S3)

```cypher
-- 위임 상속 (get_delegation_limits)
MATCH (s:Statute)-[:DELEGATES]->(o:Ordinance)
WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw)
MATCH (o)-[:CONTAINS]->(p:Provision)-[:LIMITS]->(lt:LegalTerm)
RETURN DISTINCT s.title, lt.term_name, lt.definition
LIMIT 10

-- 위계 전이성 (get_hierarchy_chain — 2홉까지 물질화 여부 확인 후 결정)
MATCH path = (s:Statute {category: '법률'})-[:SUPERIOR_TO*1..3]->(o:Ordinance)
WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw)
RETURN DISTINCT s.id, s.title, length(path) AS depth, o.title
ORDER BY depth
LIMIT 10

-- 충돌 연쇄 (get_conflict_chain)
MATCH (s:Statute)-[:SUPERIOR_TO]->(o:Ordinance)
WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw)
MATCH (s)-[:CONTAINS]->(sp:Provision)
MATCH (o)-[:CONTAINS]->(op:Provision)-[:LIMITS]->(lt:LegalTerm)
MATCH (sp)-[:LIMITS]->(lt)
RETURN DISTINCT sp.article_no, op.article_no, lt.term_name
LIMIT 10

-- 벌칙 범위 확장 (get_penalty_extension — 2홉)
MATCH (p1:Provision)-[:PENALIZES]->(p2:Provision)-[:PENALIZES]->(p3:Provision)
WHERE ANY(kw IN $keywords WHERE p1.content_text CONTAINS kw)
RETURN DISTINCT p1.article_no, p3.article_no, p3.content_text
LIMIT 10
```

---

## 4. 구현 계획 (4 세션)

### S1 — OWL 보강 (`ordinance.rdf`)

| 작업 | 파일 | 내용 |
|------|------|------|
| 레이블·주석 추가 | `ordinance.rdf` | 13개 ObjectProperty에 rdfs:label(ko/en) + rdfs:comment |
| inverseOf 선언 | `ordinance.rdf` | 위임하다↔위임근거를_가지다, 우위에_있다 역관계 추가 |
| TransitiveProperty 선언 | `ordinance.rdf` | 우위에_있다 `owl:TransitiveObjectProperty` |
| SWRL 규칙 4개 | `ordinance.rdf` | SWRL XML 블록 추가 (swrla: 네임스페이스 선언 필요) |

**예상 소요**: 1~1.5시간

### S2 — AuraDB 관계 적용

| 작업 | 방법 | 주의사항 |
|------|------|---------|
| dry-run으로 건수 확인 | `migrate_relations.py --dry-run` | SUPERIOR_TO 건수 확인 후 물질화 여부 결정 |
| 6개 관계 MERGE | `migrate_relations.py` | `$env:NEO4J_PASSWORD` 설정 필수 |
| 결과 Cypher 확인 | AuraDB Browser | `MATCH ()-[r]->() WHERE type(r) IN [...]` |

**예상 소요**: 30분 (실행 대기 포함)

### S3 — DB 레이어 확장

| 작업 | 파일 |
|------|------|
| 4개 추상 메서드 추가 | `app/db/base.py` |
| 4개 Cypher 구현 | `app/db/neo4j_db.py` |
| 4개 stub 추가 | `app/db/mock_db.py` |

**예상 소요**: 45분

### S4 — 워크플로우 통합

| 작업 | 파일 |
|------|------|
| `get_delegation_limits` → `legal_basis` 병합 | `app/graph/nodes/graph_retriever.py` |
| `get_hierarchy_chain` + `get_conflict_chain` + `get_penalty_extension` → 프롬프트 | `app/graph/nodes/legal_checker.py` + `app/prompts/legal_checker.py` |
| CLAUDE.md §OWL 보강 내용 기록 | `CLAUDE.md` |

**예상 소요**: 45분

---

## 5. 위험 및 대응

| 위험 | 가능성 | 대응 |
|------|--------|------|
| 위계 전이성 물질화 시 AuraDB 용량 초과 | 중 | dry-run 건수 < 10만 건이면 물질화, 초과 시 경로 쿼리만 사용 |
| SWRL Cypher 쿼리 타임아웃 | 중 | `LIMIT $limit` + 키워드 인덱스 보장 |
| `migrate_relations.py` 실행 중 API rate-limit | 저 | 관계 유형별 분할 실행 (`--relations limits,references`) |
| SWRL XML 파싱 오류 (Protégé 버전 불일치) | 저 | swrl:/swrla: 네임스페이스 선언 확인 후 검증 |

---

## 6. 성공 지표

| 지표 | 측정 방법 |
|------|-----------|
| OWL 모든 ObjectProperty에 rdfs:label 존재 | Protégé 클래스 창에서 레이블 표시 확인 |
| SWRL 규칙 4개 OWL 파일 내 존재 | `grep -c "swrl:Imp" ordinance.rdf` ≥ 4 |
| AuraDB 6개 관계 MERGE 완료 | `MATCH ()-[r]->() WHERE type(r) IN [...] RETURN count(*)` > 0 |
| 4개 Cypher SWRL 메서드 응답 < 3초 | local Neo4j 기준 수동 측정 |
| 기존 워크플로우 회귀 없음 | docker logs 에러 0건 |
