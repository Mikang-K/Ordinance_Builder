# Design: 그래프 관계 확장 — OWL 기반 6개 관계 추가·활성화 (graph-relation-expansion)

**작성일**: 2026-05-08  
**상태**: Design  
**단계**: Design  
**아키텍처**: Option C — 실용적 균형

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | 법령 그래프의 LIMITS·REFERENCES·ENFORCES·PENALIZES가 비어 있어 legal_checker와 drafting_agent가 텍스트 매칭에 의존. 그래프 관계를 풍부히 해야 진짜 GraphRAG 효과 발생 |
| **WHO** | drafting_agent·legal_checker·graph_retriever·QA 패널 사용자 |
| **RISK** | REFERENCES 정규식 오탐 / PENALIZES 패턴 오류 / AuraDB rate-limit / legal_checker db 주입 시 회귀 |
| **SUCCESS** | 6개 관계 AuraDB MERGE 완료 / graph_retriever·legal_checker 새 경로 사용 / 기존 워크플로우 회귀 없음 |
| **SCOPE** | `ordinance.rdf`, `pipeline/`, `app/db/`, `app/graph/nodes/`, `app/graph/workflow.py` / 프론트엔드 변경 없음 |

---

## 1. 아키텍처 개요

### 1.1 Option C 핵심 원칙

기존 패턴을 그대로 따르며 새 메서드만 추가한다:
- **파이프라인**: 모듈 상단 Cypher 상수 + `Neo4jLoader` 메서드 패턴
- **앱 DB**: `base.py` 추상 메서드 → `neo4j_db.py` 구현 패턴
- **워크플로우**: `graph_retriever`에 try/except 선택적 경로 / `legal_checker`에 `db` 주입 추가
- **새 모듈 없음**: `RelationService` 등 별도 클래스 도입 불필요

### 1.2 레이어별 변경 범위

```
[ordinance.rdf]         ← 6개 ObjectProperty 추가 (OWL 단일 진실 원천)
        ↓
[neo4j_loader.py]       ← 4개 Cypher 상수 + 4개 builder 메서드 추가
[initial_load.py]       ← Phase 4에 4개 호출 추가
        ↓
[migrate_relations.py]  ← NEW: AuraDB 기존 노드에 관계만 MERGE
        ↓
[base.py]               ← 3개 추상 메서드 추가
                           get_limiting_provisions 구현 업그레이드
[neo4j_db.py]           ← 3개 메서드 구현 + get_limiting_provisions 수정
[mock_db.py]            ← 3개 stub 추가
        ↓
[graph_retriever.py]    ← APPLIES_BY_ANALOGY 경로 추가 (선택적)
[legal_checker.py]      ← db 주입 + SUPERIOR_TO·PENALIZES 컨텍스트 보강
[workflow.py]           ← legal_checker_node에 db=get_db() 주입 1줄
```

---

## 2. OWL 확장 설계

### 2.1 추가할 ObjectProperty (ordinance.rdf)

기존 패턴:
```xml
<owl:ObjectProperty rdf:about="...#위임하다">
    <rdfs:domain rdf:resource="...#상위법률"/>
    <rdfs:range  rdf:resource="...#조례"/>
</owl:ObjectProperty>
```

6개 신규 추가:

| OWL 속성명 | domain | range | Neo4j 타입 |
|---|---|---|---|
| `제한하다` | `조` | `법적개념` | LIMITS |
| `인용하다` | `조` | `조` | REFERENCES |
| `집행하다` | `조례` | `상위법률` | ENFORCES |
| `제재하다` | `조` | `조` | PENALIZES |
| `우위에_있다` | `상위법률` | `조례` | SUPERIOR_TO |
| `유사하다` | `조례` | `조례` | SIMILAR_TO |

> `조` 클래스는 이미 OWL에 정의됨 (`조문구조 > 장 > 조`).
> `유사하다`·`우위에_있다`는 Neo4j에서 이미 구축되지만 OWL에 누락된 관계.

---

## 3. 파이프라인 설계 (neo4j_loader.py)

### 3.1 새 Cypher 상수 4개

**LIMITS** — Provision → LegalTerm (조문이 법률 용어를 제한)
```cypher
MATCH (lt:LegalTerm)
CALL (lt) {
    MATCH (p:Provision)
    WHERE size(p.content_text) > 20
      AND p.content_text CONTAINS lt.term_name
      AND NOT (p)-[:LIMITS]->(lt)
    MERGE (p)-[:LIMITS]->(lt)
} IN TRANSACTIONS OF 50 ROWS
```
- `size(content_text) > 20`: 너무 짧은 조문 제외 (fragment 방지)
- LegalTerm 단위 순회 → 전체 건수 적고 인덱스 활용 가능

**REFERENCES** — Provision → Provision (조문이 같은 부모의 다른 조문을 인용)
```cypher
MATCH (src:Provision)
WHERE src.content_text IS NOT NULL
  AND src.content_text =~ '.*제\\d+조.*'
CALL (src) {
    MATCH (src)<-[:CONTAINS]-(parent)
    MATCH (parent)-[:CONTAINS]->(target:Provision)
    WHERE target.id <> src.id
      AND src.content_text CONTAINS target.article_no
    MERGE (src)-[:REFERENCES]->(target)
} IN TRANSACTIONS OF 100 ROWS
```
- `src.content_text CONTAINS target.article_no`: 예) "제3조" 포함 여부 직접 검사
- 같은 `parent`(Statute/Ordinance) 내 참조만 연결 → 교차 문서 orphan 방지
- `=~ '.*제\\d+조.*'` 사전 필터로 불필요한 CALL 최소화

**ENFORCES** — Ordinance → Statute (시행조례가 법령을 집행)
```cypher
MATCH (o:Ordinance)-[:BASED_ON]->(s:Statute)
WHERE o.title CONTAINS '시행'
MERGE (o)-[:ENFORCES]->(s)
```
- `시행` 포함 타이틀: "○○법 시행조례"처럼 명시적 집행 위임만 선택
- BASED_ON 선행 필수 (initial_load Phase 4 순서 유지)

**PENALIZES** — Provision → Provision (제재 조항이 위반 대상 조항을 참조)
```cypher
MATCH (penalty:Provision {is_penalty_clause: true})
WHERE penalty.content_text CONTAINS '위반'
CALL (penalty) {
    MATCH (penalty)<-[:CONTAINS]-(parent)
    MATCH (parent)-[:CONTAINS]->(target:Provision)
    WHERE target.id <> penalty.id
      AND target.is_penalty_clause = false
      AND penalty.content_text CONTAINS target.article_no
    MERGE (penalty)-[:PENALIZES]->(target)
} IN TRANSACTIONS OF 100 ROWS
```
- `is_penalty_clause=True` 사전 필터 → 오탐 감소
- `CONTAINS '위반'` 이중 필터로 정밀도 향상
- 같은 부모 내 비벌칙 조항만 타겟으로 연결

### 3.2 builder 메서드 시그니처

```python
def build_limits_relationships(self) -> None:
    """OWL: 제한하다 — Provision → LegalTerm"""

def build_references_relationships(self) -> None:
    """OWL: 인용하다 — Provision → Provision (same-parent citations)"""

def build_enforces_relationships(self) -> None:
    """OWL: 집행하다 — Ordinance → Statute (시행 ordinances only)"""

def build_penalizes_relationships(self) -> None:
    """OWL: 제재하다 — Provision → Provision (penalty clause → violated provision)"""
```

### 3.3 initial_load.py Phase 4 추가 순서

```python
# Phase 4: 기존 (순서 유지)
loader.build_based_on_relationships()
loader.build_superior_to_relationships()
loader.build_similar_to_relationships()
loader.build_delegates_relationships()
loader.build_applies_by_analogy_relationships()
loader.build_defines_relationships()
loader.build_legal_term_subtypes()
loader.build_conflicts_with_relationships()

# Phase 4 추가 (신규 — BASED_ON, DEFINES 이후 실행)
loader.build_limits_relationships()        # OWL: 제한하다 (DEFINES 이후)
loader.build_references_relationships()    # OWL: 인용하다
loader.build_enforces_relationships()      # OWL: 집행하다 (BASED_ON 이후)
loader.build_penalizes_relationships()     # OWL: 제재하다 (마지막)
```

---

## 4. 마이그레이션 스크립트 설계 (migrate_relations.py)

### 4.1 스크립트 구조

```
pipeline/scripts/migrate_relations.py

인자:
  --target  aura|local     (기본: aura)
  --relations all|limits,references,enforces,penalizes,applies_by_analogy,superior_to
  --dry-run                건수만 출력, 실제 MERGE 없음

환경변수 (--target aura):
  NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
```

### 4.2 실행 흐름

```
1. Neo4jLoader 초기화 (AuraDB URI)
2. --dry-run이면 각 관계 대상 건수만 MATCH + count() 후 종료
3. 아니면 Phase A~F 순차 실행:
   A. LIMITS          (loader.build_limits_relationships)
   B. REFERENCES      (loader.build_references_relationships)
   C. ENFORCES        (loader.build_enforces_relationships)
   D. PENALIZES       (loader.build_penalizes_relationships)
   E. APPLIES_BY_ANALOGY 재확인 (이미 있으면 skip — idempotent)
   F. SUPERIOR_TO 재확인
4. 각 Phase 후 created 건수 로깅
5. 실행 시간 / 총 관계 수 요약 출력
```

### 4.3 --dry-run 출력 예시

```
[DRY-RUN] migrate_relations.py — AuraDB neo4j+s://da425acb...
  LIMITS 대상 Provision/LegalTerm 쌍:  24,831건 예상
  REFERENCES 대상 인용 패턴 조문:       8,402건 예상
  ENFORCES 대상 시행조례:                 312건 예상
  PENALIZES 대상 벌칙조항:               1,204건 예상
  APPLIES_BY_ANALOGY 미연결 확인:         (기존 존재 여부 체크)
  SUPERIOR_TO 미연결 확인:                (기존 존재 여부 체크)
→ 계속하려면 'y'를 입력하세요:
```

---

## 5. 앱 DB 레이어 설계

### 5.1 base.py 추가 추상 메서드 3개

```python
@abstractmethod
def get_analogy_applications(
    self,
    keywords: list[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    APPLIES_BY_ANALOGY 경로 탐색.
    키워드와 관련된 조례가 준용하는 상위법령 조문 반환.
    
    Returns list of dicts:
        ordinance_title, statute_title, provision_article, provision_content
    """

@abstractmethod
def get_superior_statute_provisions(
    self,
    keywords: list[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    SUPERIOR_TO 경로 탐색.
    키워드 관련 조례에 우위를 갖는 법령 조문 반환.
    legal_checker가 위계 충돌 감지에 활용.
    
    Returns list of dicts:
        statute_title, provision_article, provision_content, relation_type
    """

@abstractmethod
def get_penalty_chain(
    self,
    keywords: list[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    PENALIZES 경로 탐색.
    키워드와 관련된 벌칙 조항과 그 제재 대상 조항 쌍 반환.
    legal_checker가 제재 조항 누락 감지에 활용.
    
    Returns list of dicts:
        penalty_article, penalty_content, target_article, target_content
    """
```

### 5.2 get_limiting_provisions 업그레이드 (neo4j_db.py)

```python
# 현재: 텍스트 매칭만 사용
# 변경: LIMITS 엣지 우선, 없으면 텍스트 매칭 fallback

limits_query = """
MATCH (p:Provision)-[:LIMITS]->(lt:LegalTerm {term_name: $term})
RETURN p.article_no      AS article_no,
       p.content_text    AS content_text,
       p.is_penalty_clause AS is_penalty_clause
LIMIT 10
"""
fallback_query = """
MATCH (p:Provision)
WHERE p.is_penalty_clause = true
  AND p.content_text CONTAINS $term
RETURN p.article_no      AS article_no,
       p.content_text    AS content_text,
       p.is_penalty_clause AS is_penalty_clause
LIMIT 10
"""
# LIMITS 결과 있으면 반환, 없으면 fallback
```

### 5.3 신규 쿼리 구현 (neo4j_db.py)

**get_analogy_applications:**
```cypher
MATCH (o:Ordinance)-[:APPLIES_BY_ANALOGY]->(s:Statute)-[:CONTAINS]->(p:Provision)
WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw)
  AND ANY(kw IN $keywords WHERE p.content_text CONTAINS kw)
RETURN o.title        AS ordinance_title,
       s.title        AS statute_title,
       p.article_no   AS provision_article,
       p.content_text AS provision_content,
       'APPLIES_BY_ANALOGY' AS relation_type
LIMIT $limit
```

**get_superior_statute_provisions:**
```cypher
MATCH (s:Statute)-[:SUPERIOR_TO]->(o:Ordinance)
WHERE ANY(kw IN $keywords WHERE o.title CONTAINS kw)
MATCH (s)-[:CONTAINS]->(p:Provision)
WHERE ANY(kw IN $keywords WHERE p.content_text CONTAINS kw)
RETURN DISTINCT
       s.title        AS statute_title,
       p.article_no   AS provision_article,
       p.content_text AS provision_content,
       'SUPERIOR_TO'  AS relation_type
LIMIT $limit
```

**get_penalty_chain:**
```cypher
MATCH (penalty:Provision {is_penalty_clause: true})-[:PENALIZES]->(target:Provision)
MATCH (parent)-[:CONTAINS]->(penalty)
WHERE ANY(kw IN $keywords WHERE parent.title CONTAINS kw)
RETURN penalty.article_no  AS penalty_article,
       penalty.content_text AS penalty_content,
       target.article_no   AS target_article,
       target.content_text AS target_content
LIMIT $limit
```

---

## 6. 워크플로우 통합 설계

### 6.1 graph_retriever.py 변경

기존 5단계 후 APPLIES_BY_ANALOGY 경로 추가 (try/except — 관계 없어도 계속):

```python
# 기존 legal_basis 조회 후 보강
try:
    analogy_results = db.get_analogy_applications(keywords=keywords)
    if analogy_results:
        legal_basis.extend(analogy_results)
        logger.debug("APPLIES_BY_ANALOGY: %d개 조문 추가", len(analogy_results))
except Exception as e:
    logger.debug("APPLIES_BY_ANALOGY 쿼리 건너뜀: %s", e)
```

> APPLIES_BY_ANALOGY 결과는 기존 `legal_basis` 리스트에 append.
> 상태 스키마 변경 없음.

### 6.2 legal_checker.py 변경

**함수 시그니처 변경:**
```python
# Before
async def legal_checker_node(state, llm) -> dict:

# After
async def legal_checker_node(state, llm, db: GraphDBInterface) -> dict:
```

**추가 컨텍스트 조회:**
```python
info = state.get("ordinance_info") or {}
keywords = [v for k, v in info.items() if v and k in ("purpose", "target_group", "support_type")]

# 신규: 위계·제재 컨텍스트 조회
superior_provisions: list[dict] = []
penalty_chain: list[dict] = []
try:
    superior_provisions = db.get_superior_statute_provisions(keywords=keywords, limit=3)
    penalty_chain = db.get_penalty_chain(keywords=keywords, limit=3)
except Exception as e:
    logger.debug("legal_checker 추가 컨텍스트 건너뜀: %s", e)

human_prompt = build_legal_checker_human(
    draft, legal_basis, legal_terms,
    superior_provisions=superior_provisions,
    penalty_chain=penalty_chain,
)
```

**build_legal_checker_human 업데이트 (prompts/legal_checker.py):**
```python
def build_legal_checker_human(
    draft: str,
    legal_basis: list[dict],
    legal_terms: list[dict],
    superior_provisions: list[dict] | None = None,  # 신규 (기본값 None → 기존 호환)
    penalty_chain: list[dict] | None = None,          # 신규
) -> str:
    ...
    # superior_provisions가 있으면 프롬프트에 "위계 우위 법령 조문" 섹션 추가
    # penalty_chain이 있으면 "제재 조항 체인" 섹션 추가
```

### 6.3 workflow.py 변경 (1줄)

```python
# Before
graph.add_node("legal_checker", partial(legal_checker_node, llm=get_llm("openai")))

# After
graph.add_node("legal_checker", partial(legal_checker_node, llm=get_llm("openai"), db=get_db()))
```

`get_db()`는 이미 `workflow.py`에 노출된 싱글톤 함수.

---

## 7. 데이터 흐름 (변경 후)

```
graph_retriever_node
  ├── find_legal_basis()          → DELEGATES → BASED_ON → keyword → vector
  ├── get_analogy_applications()  → APPLIES_BY_ANALOGY  ← NEW
  ├── find_similar_ordinances()   → vector → SIMILAR_TO → keyword
  └── find_legal_terms()          → DEFINES → fallback

    legal_basis (확장됨)
           ↓
drafting_agent → draft_reviewer → draft_full_text
           ↓
legal_checker_node
  ├── legal_basis, legal_terms from state
  ├── get_superior_statute_provisions()  ← NEW (db 주입)
  ├── get_penalty_chain()                ← NEW (db 주입)
  └── LLM (GPT-4o) structured output → LegalCheckResult
```

---

## 8. 파일별 변경 상세

| 파일 | 변경 유형 | 상세 내용 | 예상 변경량 |
|------|-----------|-----------|-------------|
| `ordinance.rdf` | 수정 | 6개 ObjectProperty 추가 | +60줄 |
| `pipeline/loaders/neo4j_loader.py` | 수정 | 4개 Cypher 상수 + 4개 builder 메서드 | +100줄 |
| `pipeline/scripts/initial_load.py` | 수정 | Phase 4 끝에 4개 호출 추가 | +8줄 |
| `pipeline/scripts/migrate_relations.py` | **신규** | AuraDB 전용 마이그레이션 스크립트 | ~180줄 |
| `app/db/base.py` | 수정 | 3개 추상 메서드 추가 | +60줄 |
| `app/db/neo4j_db.py` | 수정 | 3개 메서드 구현 + get_limiting_provisions 수정 | +90줄 |
| `app/db/mock_db.py` | 수정 | 3개 stub 추가 | +30줄 |
| `app/graph/nodes/graph_retriever.py` | 수정 | APPLIES_BY_ANALOGY 경로 추가 | +12줄 |
| `app/graph/nodes/legal_checker.py` | 수정 | db 파라미터 + 2개 쿼리 호출 | +20줄 |
| `app/prompts/legal_checker.py` | 수정 | build_legal_checker_human 파라미터 추가 | +25줄 |
| `app/graph/workflow.py` | 수정 | legal_checker_node에 db=get_db() 주입 | +1줄 |
| `CLAUDE.md` | 수정 | 관계 타입 표·OWL 매핑·마이그레이션 주의사항 | +30줄 |

**총계**: 수정 11파일 + 신규 1파일 / ~616줄 추가

---

## 9. 위험 요소 및 완화

| 위험 | 완화 방법 | 코드 위치 |
|------|-----------|-----------|
| REFERENCES orphan — 없는 article_no 참조 | 같은 parent 내 target만 MERGE (`MATCH (parent)-[:CONTAINS]->(target)`) | `_BUILD_REFERENCES` |
| PENALIZES 오탐 — "제3조" 일반 언급 | `is_penalty_clause=True` + `CONTAINS '위반'` 이중 필터 | `_BUILD_PENALIZES` |
| AuraDB rate-limit | 기존 tenacity retry 패턴 재사용 (`TransientError`) | `migrate_relations.py` |
| legal_checker 회귀 — db 추가 시 기존 동작 변경 | `superior_provisions`, `penalty_chain` 기본값 `None` / try/except | `legal_checker.py` |
| get_limiting_provisions 결과 변화 | LIMITS 엣지 먼저 시도, 없으면 기존 text-match fallback | `neo4j_db.py` |

---

## 10. 테스트 계획

| 레벨 | 테스트 항목 | 검증 방법 |
|------|------------|-----------|
| L1 (관계 존재 확인) | AuraDB에 6개 관계 1건 이상 | Cypher `MATCH ()-[:LIMITS]->() RETURN count(*)` |
| L1 (회귀) | 기존 7개 관계 손상 없음 | `MATCH ()-[:BASED_ON]->() RETURN count(*)` 등 |
| L2 (쿼리 메서드) | get_analogy_applications 결과 반환 | 단일 키워드 호출 후 빈 리스트 아님 확인 |
| L2 (쿼리 메서드) | get_limiting_provisions LIMITS 엣지 사용 | DEBUG 로그에서 query 경로 확인 |
| L3 (워크플로우) | legal_checker_node가 db 파라미터로 실행 | Cloud Run 로그에서 500 없음 |
| L3 (워크플로우) | graph_retriever에 APPLIES_BY_ANALOGY 결과 포함 | /debug 엔드포인트 legal_basis 필드 확인 |

---

## 11. 구현 가이드

### 11.1 구현 순서

```
Step 1: OWL 확장
  → ordinance.rdf에 6개 ObjectProperty 추가

Step 2: 파이프라인 빌더
  → neo4j_loader.py: 4개 Cypher 상수 + builder 메서드 추가
  → initial_load.py: Phase 4에 4개 호출 추가

Step 3: 마이그레이션 스크립트
  → migrate_relations.py 신규 작성
  → --dry-run으로 AuraDB 대상 건수 확인 후 실행

Step 4: 앱 DB 레이어
  → base.py: 3개 추상 메서드 추가
  → neo4j_db.py: 3개 구현 + get_limiting_provisions 수정
  → mock_db.py: 3개 stub 추가

Step 5: 워크플로우 통합
  → graph_retriever.py: APPLIES_BY_ANALOGY 경로 추가
  → legal_checker.py: db 주입 + 컨텍스트 보강
  → prompts/legal_checker.py: build_legal_checker_human 파라미터 추가
  → workflow.py: legal_checker_node에 db 주입

Step 6: 문서 업데이트
  → CLAUDE.md 관계 표·OWL 매핑·마이그레이션 주의사항 업데이트
```

### 11.2 중요 구현 주의사항

1. **REFERENCES 빌더**: `target.article_no`가 문자열("제3조" 형식)이므로 `CONTAINS` 직접 사용 가능. 별도 정규식 처리 불필요.

2. **ENFORCES**: `BASED_ON` 빌더 실행 후 반드시 실행. 순서 바뀌면 결과 0건.

3. **legal_checker의 db 파라미터**: 기존 `partial(legal_checker_node, llm=...)` 패턴에 `db=get_db()` 추가만 하면 됨. 함수 시그니처는 keyword argument이므로 기존 호출 코드와 호환.

4. **build_legal_checker_human 하위 호환**: `superior_provisions=None`, `penalty_chain=None` 기본값으로 기존 테스트/호출 코드 영향 없음.

5. **migrate_relations.py AuraDB 연결**: 기존 `SKIP_PROVISION_EMBEDDING=true` 패턴처럼 `NEO4J_URI`로 AuraDB 접속. `Neo4jLoader` 재사용.

### 11.3 Session Guide

| 세션 | 모듈 | 파일 |
|------|------|------|
| **S1** | OWL + 파이프라인 | `ordinance.rdf`, `neo4j_loader.py`, `initial_load.py` |
| **S2** | 마이그레이션 | `migrate_relations.py` (신규) |
| **S3** | 앱 DB 레이어 | `base.py`, `neo4j_db.py`, `mock_db.py` |
| **S4** | 워크플로우 + 문서 | `graph_retriever.py`, `legal_checker.py`, `prompts/legal_checker.py`, `workflow.py`, `CLAUDE.md` |
