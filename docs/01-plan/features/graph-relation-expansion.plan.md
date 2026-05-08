# Plan: 그래프 관계 확장 — OWL 기반 6개 관계 추가·활성화 (graph-relation-expansion)

**작성일**: 2026-05-08  
**상태**: Planning  
**단계**: Plan

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **문제** | AuraDB에 실제 구동 중인 관계는 7개(CONTAINS·BASED_ON·DELEGATES·SIMILAR_TO·DEFINES·CONFLICTS_WITH·APPLIES_BY_ANALOGY)지만, 스키마에 정의된 LIMITS·REFERENCES는 구현이 없고, APPLIES_BY_ANALOGY·SUPERIOR_TO는 파이프라인에서 만들어지지만 앱에서 전혀 쓰이지 않으며, 신규 관계(ENFORCES·PENALIZES)는 아예 존재하지 않아 법령 그래프가 잠재력을 충분히 활용하지 못하고 있음 |
| **해결** | OWL 온톨로지(`ordinance.rdf`)를 단일 진실 원천으로 삼아 6개 관계를 정식 정의한 뒤, ETL 파이프라인에 빌더를 추가하고, AuraDB 기존 노드에 관계만 MERGE하는 마이그레이션 스크립트를 실행하며, 앱의 쿼리·워크플로우 노드에 연결 |
| **기능 UX 효과** | 초안 생성 시 조문 간 인용 경로·제재 조항 자동 참조 / 법률 검증 시 위계·집행 경로로 충돌 감지 정밀도 향상 / QA 패널 답변에 조문 간 의존 관계 포함 |
| **핵심 가치** | OWL 온톨로지 → Neo4j 스키마 → 앱 쿼리를 완전히 동기화해 그래프 DB의 의미적 풍부함을 실제 서비스 품질로 전환 |

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | 현재 법령 그래프의 절반(LIMITS·REFERENCES·ENFORCES·PENALIZES)이 비어 있어 legal_checker와 drafting_agent가 단순 텍스트 매칭에 의존. 그래프 관계를 풍부히 해야 진짜 그래프 RAG 효과 발생 |
| **WHO** | drafting_agent(초안 생성)·legal_checker(법률 검증)·graph_retriever(법령 검색)·QA 패널 사용자 |
| **RISK** | ① REFERENCES 정규식 오탐(없는 조문 번호 참조) → orphan edge 생성 ② PENALIZES 패턴 매칭 정밀도 낮을 시 잘못된 제재 연결 ③ AuraDB 마이그레이션 스크립트 실행 중 rate-limit |
| **SUCCESS** | 6개 관계 모두 AuraDB에 MERGE 완료 / 앱 graph_retriever·legal_checker가 새 관계 경로 사용 / 기존 워크플로우 회귀 없음 |
| **SCOPE** | `ordinance.rdf`·`pipeline/`·`app/db/`·`app/graph/nodes/` 변경. 프론트엔드 변경 없음 |

---

## 1. 현황 분석

### 1.1 관계 상태 전체 맵

| 관계 (Neo4j) | OWL 속성 | 파이프라인 구축 | 앱 쿼리 | 상태 |
|---|---|---|---|---|
| CONTAINS | `포함하다` | ✓ | ✓ | 완전 구현 |
| BASED_ON | `위임근거를_가지다` | ✓ | ✓ | 완전 구현 |
| DELEGATES | `위임하다` | ✓ | ✓ | 완전 구현 |
| CONFLICTS_WITH | `상충하다` | ✓ | ✓ | 완전 구현 |
| DEFINES | `정의하다` | ✓ | ✓ | 완전 구현 |
| SIMILAR_TO | *(OWL 미정의)* | ✓ | ✓ | 완전 구현 (OWL만 누락) |
| APPLIES_BY_ANALOGY | `준용하다` | **✓** | **✗** | **파이프라인만 구축** |
| SUPERIOR_TO | *(OWL 미정의)* | **✓** | **✗** | **파이프라인만 구축** |
| LIMITS | *(없음)* | **✗** | **✗** | **스키마 정의만 존재** |
| REFERENCES | *(없음)* | **✗** | **✗** | **스키마 정의만 존재** |
| ENFORCES | *(없음)* | **✗** | **✗** | **신규** |
| PENALIZES | *(없음)* | **✗** | **✗** | **신규** |

### 1.2 이번 피처에서 다루는 6개 관계

| 관계 | 방향 | OWL 속성명 (신규) | 구축 방법 | 활용처 |
|------|------|-------------------|-----------|--------|
| **LIMITS** | `Provision → LegalTerm` | `제한하다` | 조문 본문 ∩ LegalTerm명 텍스트 매칭 | graph_retriever — 용어 제한 범위 |
| **REFERENCES** | `Provision → Provision` | `인용하다` | 정규식 `제\d+조` → article_no 매핑 | drafting_agent — 인용 체계 참조 |
| **ENFORCES** | `Ordinance → Statute` | `집행하다` | DELEGATES의 역방향 + "집행" 키워드 조합 | legal_checker — 집행 위임 경로 |
| **PENALIZES** | `Provision → Provision` | `제재하다` | `is_penalty_clause=true` + `제\d+조를? 위반` 패턴 | legal_checker — 제재 조항 연결 |
| **APPLIES_BY_ANALOGY** | `Ordinance → Statute` | `준용하다` *(이미 OWL 존재)* | 이미 구축됨 — 쿼리만 추가 | graph_retriever — 준용 경로 |
| **SUPERIOR_TO** | `Statute → Ordinance` | `우위에_있다` *(신규)* | 이미 구축됨 — 쿼리만 추가 | legal_checker — 위계 검증 |

---

## 2. 요구사항

### 2.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-01 | `ordinance.rdf`에 6개 OWL Object Property 추가 | P0 |
| FR-02 | `neo4j_loader.py`에 LIMITS 빌더 추가 (텍스트 매칭) | P0 |
| FR-03 | `neo4j_loader.py`에 REFERENCES 빌더 추가 (정규식) | P0 |
| FR-04 | `neo4j_loader.py`에 ENFORCES 빌더 추가 | P0 |
| FR-05 | `neo4j_loader.py`에 PENALIZES 빌더 추가 | P0 |
| FR-06 | `pipeline/scripts/migrate_relations.py` 생성 — AuraDB 기존 노드에 새 관계만 MERGE | P0 |
| FR-07 | `app/db/neo4j_db.py`에 APPLIES_BY_ANALOGY 쿼리 추가 | P1 |
| FR-08 | `app/db/neo4j_db.py`에 SUPERIOR_TO 쿼리 추가 | P1 |
| FR-09 | `app/db/neo4j_db.py`에 LIMITS·REFERENCES·ENFORCES·PENALIZES 쿼리 추가 | P1 |
| FR-10 | `app/graph/nodes/graph_retriever.py` — REFERENCES·LIMITS 경로 통합 | P2 |
| FR-11 | `app/graph/nodes/legal_checker.py` — ENFORCES·PENALIZES·SUPERIOR_TO 경로 통합 | P2 |
| FR-12 | `app/db/base.py` 인터페이스 업데이트 | P1 |

### 2.2 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NFR-01 | 마이그레이션 스크립트는 MERGE idempotent — 중단 후 재실행 안전 |
| NFR-02 | REFERENCES 빌더는 존재하지 않는 article_no 참조를 silently skip (orphan 방지) |
| NFR-03 | 마이그레이션 중 AuraDB rate-limit 대응 (배치 처리 + 지수 backoff) |
| NFR-04 | 기존 7개 관계 사용 쿼리 회귀 없음 |
| NFR-05 | `--dry-run` 플래그로 마이그레이션 대상 건수 미리 확인 가능 |

---

## 3. 구현 범위

### 3.1 수정 파일

| 파일 | 변경 유형 | 내용 |
|------|-----------|------|
| `ordinance.rdf` | 수정 | 6개 OWL ObjectProperty 추가 |
| `pipeline/loaders/neo4j_loader.py` | 수정 | LIMITS·REFERENCES·ENFORCES·PENALIZES 빌더 메서드 추가 |
| `pipeline/scripts/initial_load.py` | 수정 | Phase 4에 새 빌더 호출 추가 |
| `pipeline/scripts/migrate_relations.py` | 신규 | AuraDB 전용 관계-only 마이그레이션 |
| `app/db/base.py` | 수정 | 새 쿼리 메서드 인터페이스 정의 |
| `app/db/neo4j_db.py` | 수정 | 6개 관계 쿼리 메서드 구현 |
| `app/graph/nodes/graph_retriever.py` | 수정 | REFERENCES·LIMITS·APPLIES_BY_ANALOGY 경로 추가 |
| `app/graph/nodes/legal_checker.py` | 수정 | ENFORCES·PENALIZES·SUPERIOR_TO 경로 추가 |
| `CLAUDE.md` | 수정 | 관계 타입 표 업데이트, §주의사항에 마이그레이션 방법 추가 |

---

## 4. 설계 방향

### 4.1 OWL → Neo4j 매핑 원칙

`ordinance.rdf`를 단일 진실 원천으로 유지한다. Neo4j 관계 타입명은 OWL ObjectProperty의 한국어 명칭을 영문 대문자로 변환한 규칙을 따른다.

| OWL (한국어) | Neo4j 관계 타입 |
|---|---|
| `위임하다` | DELEGATES |
| `위임근거를_가지다` | BASED_ON |
| `상충하다` | CONFLICTS_WITH |
| `준용하다` | APPLIES_BY_ANALOGY |
| `포함하다` | CONTAINS |
| `정의하다` | DEFINES |
| `제한하다` *(신규)* | LIMITS |
| `인용하다` *(신규)* | REFERENCES |
| `집행하다` *(신규)* | ENFORCES |
| `제재하다` *(신규)* | PENALIZES |
| `우위에_있다` *(신규)* | SUPERIOR_TO |
| `유사하다` *(신규)* | SIMILAR_TO |

### 4.2 각 관계 빌더 알고리즘

**LIMITS (Provision → LegalTerm)**
```
각 LegalTerm.term_name에 대해
  MATCH (p:Provision) WHERE p.content_text CONTAINS term_name
  MERGE (p)-[:LIMITS]->(lt:LegalTerm {term_name: term_name})
```
- 조건: `content_text` 길이 > 20 (너무 짧은 조문 제외)
- 배치: LegalTerm 단위 순회 (전체 수 ~수백 개)

**REFERENCES (Provision → Provision)**
```
각 Provision.content_text에서 정규식 r'제(\d+)조' 추출
  → article_no = 추출된 숫자
  MATCH (target:Provision {article_no: article_no})
  WHERE target.id <> source.id  -- 자기 참조 제외
  MERGE (source)-[:REFERENCES]->(target)
```
- orphan 방지: `WHERE target IS NOT NULL` 필수
- 같은 법령 내 참조만 연결 (Statute 경계 체크)

**ENFORCES (Ordinance → Statute)**
```
MATCH (o:Ordinance)-[:BASED_ON]->(s:Statute)
WHERE o.title CONTAINS '시행' OR o.purpose_text CONTAINS '집행'
MERGE (o)-[:ENFORCES]->(s)
```
- DELEGATES의 역방향 의미이지만 "시행"/"집행" 키워드로 세분

**PENALIZES (Provision → Provision)**
```
MATCH (penalty:Provision {is_penalty_clause: true})
  WHERE penalty.content_text =~ '.*제\\d+조를?\\s*위반.*'
  WITH penalty, apoc.text.regexGroups(content_text, '제(\\d+)조를?\\s*위반')[0][1] AS ref_no
  MATCH (target:Provision {article_no: toInteger(ref_no)})
  MERGE (penalty)-[:PENALIZES]->(target)
```
- APOC 미사용 환경에서는 Python에서 정규식 처리 후 Neo4j에 MERGE

### 4.3 마이그레이션 스크립트 구조

```
pipeline/scripts/migrate_relations.py
  ├── --target aura|local (기본: aura)
  ├── --relations limits,references,enforces,penalizes,all (기본: all)
  ├── --dry-run: 대상 건수만 출력
  └── 실행 순서:
      Phase A: LIMITS (LegalTerm 순회)
      Phase B: REFERENCES (Provision 순회, 배치 1000개)
      Phase C: ENFORCES (Ordinance 순회)
      Phase D: PENALIZES (Provision is_penalty_clause 순회)
      Phase E: APPLIES_BY_ANALOGY 미연결 재확인 (이미 있으면 skip)
      Phase F: SUPERIOR_TO 미연결 재확인
```

### 4.4 앱 통합 — graph_retriever 경로 추가

기존 4단계 fallback 뒤에 2단계 추가:
```
5순위: REFERENCES 역방향 — 이 조항을 인용한 조항 탐색
6순위: LIMITS — 이 법령 용어를 제한하는 조항
```

### 4.5 앱 통합 — legal_checker 경로 추가

기존 CONFLICTS_WITH 외에:
```
- SUPERIOR_TO: 법령이 조례보다 위계 상 우위 → 위반 시 자동 HIGH severity
- ENFORCES: 집행 위임 체인 추적 → 집행 경로 단절 감지
- PENALIZES: 제재 조항이 존재하는지 확인 → 제재 조항 누락 경고
```

---

## 5. 위험 요소 및 대응

| 위험 | 확률 | 영향 | 대응 |
|------|------|------|------|
| REFERENCES orphan edge — 없는 조문 참조 | 중간 | 낮음 | OPTIONAL MATCH + WHERE target IS NOT NULL |
| PENALIZES 패턴 오탐 — "제3조를 위반한 것처럼 보이는" 일반 문장 | 중간 | 중간 | `is_penalty_clause=True` 조건 선행 필터링 |
| AuraDB rate limit — 마이그레이션 중 429 | 낮음 | 높음 | 배치 1000건 + 지수 backoff (§27 패턴 재사용) |
| 기존 쿼리 회귀 | 낮음 | 높음 | 새 메서드만 추가, 기존 메서드 변경 없음 |
| OWL/Neo4j 불일치 누적 | 낮음 | 중간 | 이번 작업으로 동기화 완성 → CLAUDE.md에 대응 규칙 추가 |

---

## 6. 작업 순서 (구현 세션 플랜)

| 세션 | 모듈 | 파일 | 예상 변경량 |
|------|------|------|-------------|
| **S1** | OWL 확장 | `ordinance.rdf` | +60줄 (6개 ObjectProperty) |
| **S1** | 파이프라인 빌더 | `neo4j_loader.py` | +120줄 (4개 빌더) |
| **S1** | initial_load 연결 | `initial_load.py` | +8줄 |
| **S2** | 마이그레이션 스크립트 | `migrate_relations.py` (신규) | ~200줄 |
| **S3** | DB 인터페이스 | `base.py`, `neo4j_db.py` | +150줄 |
| **S4** | 워크플로우 통합 | `graph_retriever.py`, `legal_checker.py` | +80줄 |
| **S4** | 문서 | `CLAUDE.md` | 관계 표·주의사항 업데이트 |

---

## 7. 성공 기준

| 기준 | 검증 방법 |
|------|-----------|
| AuraDB에 LIMITS 관계 1건 이상 존재 | `MATCH ()-[:LIMITS]->() RETURN count(*)` > 0 |
| AuraDB에 REFERENCES 관계 1건 이상 존재 | `MATCH ()-[:REFERENCES]->() RETURN count(*)` > 0 |
| AuraDB에 ENFORCES 관계 1건 이상 존재 | `MATCH ()-[:ENFORCES]->() RETURN count(*)` > 0 |
| AuraDB에 PENALIZES 관계 1건 이상 존재 | `MATCH ()-[:PENALIZES]->() RETURN count(*)` > 0 |
| APPLIES_BY_ANALOGY 쿼리 메서드 존재 | `neo4j_db.get_analogy_applications()` 호출 가능 |
| SUPERIOR_TO 쿼리 메서드 존재 | `neo4j_db.get_superior_statutes()` 호출 가능 |
| 기존 워크플로우 회귀 없음 | Cloud Run 로그에서 기존 관계 관련 500 없음 |
| OWL 파일에 6개 ObjectProperty 정의 | Protégé에서 파일 열기 → 속성 목록 확인 |
