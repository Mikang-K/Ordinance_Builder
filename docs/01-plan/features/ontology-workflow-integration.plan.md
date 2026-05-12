# Plan: 워크플로우 전반 온톨로지 통합 (ontology-workflow-integration)

**작성일**: 2026-05-12
**상태**: Planning
**단계**: Plan

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **문제** | OWL 온톨로지(`ordinance.rdf`)와 SWRL 4규칙이 `legal_checker`·`graph_retriever`·`drafting_agent` 3개 노드에만 연결되어 있어, 조항 인터뷰 단계(`article_planner`/`article_interviewer`), 초안 검토 단계(`draft_reviewer`), 입력 분류 단계(`intent_analyzer`)에서는 온톨로지 지식이 전혀 활용되지 않음 |
| **해결** | ① `intent_analyzer` 프롬프트에 OWL 클래스 계층 주입 → ordinance_type 추출 정확도 향상 ② `graph_retriever`에서 SWRL Rules 2-4 사전 계산 + State 저장 → 하위 노드 재쿼리 제거 ③ `article_interviewer`에 조항별 LegalTerm DB 호출 → 입력 중 실시간 법령 용어 힌트 제공 ④ `draft_reviewer` 수정 경로에 위계·충돌 정보 주입 → 수정 품질 향상 |
| **기능 UX 효과** | 조항 작성 중 "이 조항과 관련된 법령 용어: ○○이란 …" 자동 표시 / 초안 수정 요청 시 위계 체계 context가 반영된 법적으로 더 정확한 수정 반환 / ordinance_type 오추출로 인한 인터뷰 루프 탈출 실패 빈도 감소 |
| **핵심 가치** | OWL 온톨로지를 설계 명세에서 전 워크플로우 실행 지식으로 격상. 각 노드가 온톨로지 지식을 자신의 역할에 맞게 활용하는 "온톨로지-native 워크플로우" 구현 |

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | owl-swrl-enrichment(§29)에서 온톨로지 구조와 SWRL 추론은 완성됐지만, 실제 사용자 여정(인터뷰→작성→검토)의 앞 단계에서는 이 지식이 도달하지 않아 법령 용어 안내 없이 사용자가 텍스트를 입력함. 온톨로지를 전 워크플로우에 흘려보내야 법적 완성도가 높아짐 |
| **WHO** | 조항 입력 중인 사용자(조항별 법령 용어 힌트), 초안 수정 요청 사용자(위계 체계 반영 수정), intent_analyzer(정확한 조례 유형 분류) |
| **RISK** | ① article_interviewer async 전환 시 workflow.py partial 바인딩 누락 → `TypeError` ② SWRL 사전 계산 AuraDB 데이터 미적재 시 빈 결과 → graceful degradation 필수 ③ LegalTerm 조항별 DB 호출로 응답 지연 가능 (≤1초 목표) ④ State 필드 추가 시 기존 체크포인트 스키마 변경 → LangGraph checkpointer 마이그레이션 주의 |
| **SUCCESS** | 4개 노드(intent_analyzer, graph_retriever, article_interviewer, draft_reviewer) 모두 온톨로지 데이터를 활용 / 기존 워크플로우 회귀 없음 / article_interviewer DB 호출 추가 후 응답 ≤2초 |
| **SCOPE** | `app/graph/state.py`, `app/graph/nodes/intent_analyzer.py`, `app/graph/nodes/graph_retriever.py`, `app/graph/nodes/article_interviewer.py`, `app/graph/nodes/legal_checker.py`, `app/graph/workflow.py`, `app/prompts/intent_analyzer.py`, `app/prompts/draft_reviewer.py`, `app/prompts/legal_terms.py`. 프론트엔드·API 스키마·DB 레이어 변경 없음 |

---

## 1. 현황 분석

### 1.1 노드별 온톨로지 연결 현황

| 노드 | 온톨로지 활용 여부 | 현재 방식 | 미활용 영역 |
|------|-----------------|-----------|------------|
| `intent_analyzer` | 부분 | 프롬프트에 조례 유형 목록 수동 나열 | OWL 클래스 계층 미주입 → 추출 오류 가능 |
| `graph_retriever` | 부분 | SWRL Rule 1 (위임 상속) 적용 | Rules 2-4 미계산 → legal_checker에서 재쿼리 |
| `article_planner` | 없음 | 정적 ARTICLE_TEMPLATES 딕셔너리 | OWL 조문구조·법적행위 미활용 |
| `article_interviewer` | 없음 | 정적 질문 + article_examples | LegalTerm 힌트·LIMITS 제약 미표시 |
| `drafting_agent` | 있음 | ONTOLOGY_TERM_GUIDE 시스템 프롬프트 | — (기존 구현 유지) |
| `draft_reviewer` | 부분 | ONTOLOGY_TERM_GUIDE (revision path) | SWRL 위계·충돌 결과 미활용 |
| `legal_checker` | 있음 | SWRL Rules 2-4 직접 쿼리 + 프롬프트 | graph_retriever와 중복 쿼리 가능 |

### 1.2 SWRL 쿼리 이중화 문제

```
현재 흐름:
graph_retriever → (SWRL Rule 1만)
  → ... → drafting_agent → draft_reviewer → legal_checker
                                              ↓
                             SWRL Rules 2-4 DB 재쿼리 (중복)
                             get_hierarchy_chain()
                             get_conflict_chain()
                             get_penalty_extension()

개선 후 흐름:
graph_retriever → (SWRL Rules 1-4 모두 계산 → State 저장)
  → ... → draft_reviewer → State 읽기 (DB 호출 없음)
         → legal_checker → State 읽기 (DB 호출 없음)
```

### 1.3 article_interviewer 온톨로지 접근 가능성

```
현재: article_interviewer_node(state) — db 파라미터 없음
개선: async article_interviewer_node(state, db) + workflow.py partial 바인딩

호출 패턴 (article_interviewer DB):
  ARTICLE_ONTOLOGY_KEYWORDS = {
    "목적": ["목적", "공익"],
    "정의": ["정의", "해석"],
    "지원대상": ["지원", "자격", "대상"],
    ...
  }
  → find_legal_terms(keywords=ARTICLE_ONTOLOGY_KEYWORDS[current_article_key])
  → get_limiting_provisions(legal_term=first_term)
```

---

## 2. 요구사항 정의

### 기능 요구사항

| ID | 요구사항 | 우선순위 | 대상 노드 |
|----|----------|----------|-----------|
| FR-01 | `legal_terms.py`에 OWL 클래스 계층 빌더 함수 추가 (`build_class_hierarchy_section()`) | 필수 | intent_analyzer |
| FR-02 | `INTENT_ANALYZER_SYSTEM` 프롬프트에 OWL 조례 하위 클래스 계층을 동적 주입 | 필수 | intent_analyzer |
| FR-03 | `graph_retriever_node`에 `get_hierarchy_chain()`, `get_conflict_chain()`, `get_penalty_extension()` 추가 | 필수 | graph_retriever |
| FR-04 | `state.py`에 `hierarchy_chain`, `conflict_chain`, `penalty_extension` 필드 추가 | 필수 | state |
| FR-05 | `legal_checker_node`가 DB 재쿼리 대신 State에서 SWRL 결과 읽도록 변경 | 필수 | legal_checker |
| FR-06 | `article_interviewer_node`를 `async def`로 전환 + `db: GraphDBInterface` 파라미터 추가 | 필수 | article_interviewer |
| FR-07 | `ARTICLE_ONTOLOGY_KEYWORDS` 딕셔너리 정의 (조항키 → 검색 키워드 매핑) | 필수 | article_interviewer |
| FR-08 | `article_interviewer`에서 `find_legal_terms()` + `get_limiting_provisions()` 호출해 질문 하단에 힌트 표시 | 필수 | article_interviewer |
| FR-09 | `workflow.py`에서 `article_interviewer_node`에 `db` 바인딩 추가 | 필수 | workflow |
| FR-10 | `build_draft_revision_human()`에 `hierarchy_chain` + `conflict_chain` State 값 수신 및 프롬프트 섹션 추가 | 중요 | draft_reviewer |
| FR-11 | `draft_reviewer_node`가 State에서 `hierarchy_chain`, `conflict_chain` 읽어 revision human 프롬프트에 전달 | 중요 | draft_reviewer |

### 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NFR-01 | `article_interviewer` DB 호출 포함 응답 ≤2초 (AuraDB 기준) |
| NFR-02 | 모든 온톨로지 호출 `try/except` 래핑 — DB 미응답 시 graceful degradation |
| NFR-03 | 기존 체크포인트 호환성 — State 신규 필드는 `Optional` 기본값 |
| NFR-04 | 프론트엔드·API 스키마 변경 없음 (백엔드 내부 변경만) |

---

## 3. 기술 설계 방향

### 3.1 FR-01/02 — intent_analyzer OWL 클래스 계층 주입

```python
# app/prompts/legal_terms.py — 신규 함수 추가
def _build_class_hierarchy_section(g) -> str:
    """OWL 클래스 계층에서 조례 타입 분류 섹션 생성."""
    ordinance_subclasses = []
    for cls in g.subjects(RDFS.subClassOf, URIRef(_NS + "자치법규")):
        name = _local(cls)
        comment = next(g.objects(cls, RDFS.comment), None)
        label_ko = next(
            (str(l) for l in g.objects(cls, RDFS.label) if l.language == "ko"), name
        )
        ordinance_subclasses.append(f"  - {label_ko}: {str(comment) if comment else ''}")
    return "[조례 하위 유형 (OWL)]\n" + "\n".join(ordinance_subclasses)

# 적용: INTENT_ANALYZER_SYSTEM에 f-string으로 주입
# ONTOLOGY_CLASS_GUIDE = _build_class_hierarchy_section(g) — lazy import 패턴
```

```python
# app/prompts/intent_analyzer.py — 시스템 프롬프트 확장
from app.prompts.legal_terms import ONTOLOGY_CLASS_GUIDE  # 신규

INTENT_ANALYZER_SYSTEM = f"""
...기존 내용...

{ONTOLOGY_CLASS_GUIDE}
""".strip()
```

### 3.2 FR-03/04/05 — graph_retriever SWRL 사전 계산

```python
# app/graph/nodes/graph_retriever.py — SWRL Rules 2-4 추가

# SWRL Rule 2 — 위계 전이성 (사전 계산 → State에 저장)
hierarchy_chain: list[dict] = []
try:
    hierarchy_chain = db.get_hierarchy_chain(keywords=keywords)
except Exception as exc:
    logger.debug("SWRL Rule 2 위계 전이성 생략: %s", exc)

# SWRL Rule 3 — 충돌 연쇄
conflict_chain: list[dict] = []
try:
    conflict_chain = db.get_conflict_chain(keywords=keywords)
except Exception as exc:
    logger.debug("SWRL Rule 3 충돌 연쇄 생략: %s", exc)

# SWRL Rule 4 — 벌칙 범위 확장
penalty_extension: list[dict] = []
try:
    penalty_extension = db.get_penalty_extension(keywords=keywords)
except Exception as exc:
    logger.debug("SWRL Rule 4 벌칙 범위 확장 생략: %s", exc)

return {
    ...기존 필드...,
    "hierarchy_chain": hierarchy_chain,
    "conflict_chain": conflict_chain,
    "penalty_extension": penalty_extension,
}
```

```python
# app/graph/state.py — 신규 필드 추가 (Optional, 기존 체크포인트 호환)
hierarchy_chain: list[dict]      # SWRL Rule 2 — 위계 전이성 체인
conflict_chain: list[dict]       # SWRL Rule 3 — 충돌 연쇄
penalty_extension: list[dict]    # SWRL Rule 4 — 벌칙 범위 확장
```

```python
# app/graph/nodes/legal_checker.py — DB 재쿼리 → State 읽기로 교체
# Before:
hierarchy_chain = db.get_hierarchy_chain(keywords=keywords)

# After:
hierarchy_chain = state.get("hierarchy_chain") or []
```

### 3.3 FR-06/07/08/09 — article_interviewer LegalTerm 힌트

```python
# app/graph/nodes/article_interviewer.py

# 조항키 → 온톨로지 검색 키워드 매핑
ARTICLE_ONTOLOGY_KEYWORDS: dict[str, list[str]] = {
    "목적":   ["목적", "공익", "활성화"],
    "정의":   ["정의", "청년", "창업", "지원"],
    "지원대상": ["자격", "지원대상", "청년"],
    "지원내용": ["보조금", "지원", "급부"],
    "지원금액": ["한도", "지원금", "예산"],
    "신청방법": ["신청", "접수", "서류"],
    "심사선정": ["심사", "선정", "위원회"],
    "환수제재": ["환수", "제재", "벌칙", "과태료"],
    "위임":   ["위임", "규칙", "시행"],
    "설치":   ["설치", "기관", "소속"],
    "구성":   ["위원", "임기", "구성"],
    "직무":   ["직무", "권한", "의결"],
    "운영":   ["운영", "회의", "정족수"],
    "간사":   ["간사", "사무", "공무원"],
    "적용범위": ["적용", "범위", "시설"],
    "관리책임": ["관리", "책임", "위탁"],
    "사용허가": ["허가", "신청", "취소"],
    "사용료": ["사용료", "감면", "징수"],
    "위반제재": ["과태료", "위반", "제재"],
    "서비스내용": ["서비스", "돌봄", "급여"],
    "제공기관": ["제공기관", "위탁", "지정"],
    "신청접수": ["신청", "접수", "자격"],
    "비용":   ["비용", "본인부담", "감면"],
}

async def article_interviewer_node(
    state: OrdinanceBuilderState,
    db: GraphDBInterface,         # 신규 파라미터
) -> dict:
    ...
    # 다음 조항 질문 시 LegalTerm 힌트 조회
    ontology_hints_block = ""
    if db and next_key in ARTICLE_ONTOLOGY_KEYWORDS:
        try:
            hint_keywords = ARTICLE_ONTOLOGY_KEYWORDS[next_key]
            legal_terms = db.find_legal_terms(keywords=hint_keywords, limit=3)
            if legal_terms:
                hint_lines = [
                    f"  • **{t['term_name']}**: {t['definition'][:120]}"
                    + (f" _(출처: {t['source_statute']})_" if t.get("source_statute") else "")
                    for t in legal_terms
                ]
                ontology_hints_block = (
                    "\n\n---\n**관련 법령 용어** (OWL 온톨로지 기반)\n"
                    + "\n".join(hint_lines)
                )
        except Exception as hint_exc:
            logger.debug("온톨로지 힌트 생략 (조항=%s): %s", next_key, hint_exc)

    response = (
        f"✓ **{current_title}** {saved_label}\n\n"
        f"━━━ **{filled_count + 1} / {total}** ━━━\n\n"
        f"**[{next_title}]**\n\n"
        f"{next_question}"
        f"{examples_block}"
        f"{ontology_hints_block}"  # 온톨로지 힌트 추가
    )
```

```python
# app/graph/workflow.py — partial 바인딩 업데이트
from functools import partial

article_interviewer_with_db = partial(article_interviewer_node, db=db)
graph.add_node("article_interviewer", article_interviewer_with_db)
# 기존: graph.add_node("article_interviewer", article_interviewer_node)
```

### 3.4 FR-10/11 — draft_reviewer SWRL State 활용

```python
# app/graph/nodes/draft_reviewer.py — revise 경로에 SWRL 주입
async def draft_reviewer_node(state, llm):
    ...
    # SWRL 결과 State에서 읽기 (revision path에서만 활용)
    hierarchy_chain: list[dict] = state.get("hierarchy_chain") or []
    conflict_chain: list[dict] = state.get("conflict_chain") or []

    if decision == "revise":
        revised = await reviser_llm.ainvoke([
            ("system", DRAFT_REVISION_SYSTEM),
            ("human", build_draft_revision_human(
                user_input, draft_full_text, draft_articles,
                hierarchy_chain=hierarchy_chain,     # 신규
                conflict_chain=conflict_chain,       # 신규
            )),
        ])
```

```python
# app/prompts/draft_reviewer.py — build_draft_revision_human 확장

def build_draft_revision_human(
    user_request: str,
    draft_full_text: str,
    draft_articles: list[dict],
    hierarchy_chain: list[dict] | None = None,  # 신규
    conflict_chain: list[dict] | None = None,   # 신규
) -> str:
    ...
    # 위계 체계 섹션 (SWRL Rule 2)
    hierarchy_section = ""
    if hierarchy_chain:
        lines = [
            f"  [depth={h['depth']}] {h['statute_title']} → {h['ordinance_title']}"
            for h in hierarchy_chain[:5]
        ]
        hierarchy_section = "\n\n## 준수해야 할 법적 위계 체계\n" + "\n".join(lines)

    # 충돌 위험 섹션 (SWRL Rule 3)
    conflict_section = ""
    if conflict_chain:
        lines = [
            f"  [{c['conflict_term']}] 상위법 {c['statute_article']} ↔ 조례 {c['ordinance_article']}"
            for c in conflict_chain[:5]
        ]
        conflict_section = "\n\n## 충돌 위험 용어 (수정 시 주의)\n" + "\n".join(lines)

    return (
        f"## 현재 조례 초안\n{articles_text}\n\n"
        f"## 사용자 수정 요청\n{user_request}"
        f"{hierarchy_section}{conflict_section}\n\n"
        f"위 수정 사항을 반영하되, 법적 위계 체계를 준수하고 충돌 위험 용어에 주의하세요."
    )
```

---

## 4. 구현 계획 (4 세션)

### S1 — intent_analyzer OWL 클래스 주입
**예상 소요**: 30분

| 작업 | 파일 |
|------|------|
| `legal_terms.py`에 `_build_class_hierarchy_section()` + `ONTOLOGY_CLASS_GUIDE` 추가 | `app/prompts/legal_terms.py` |
| `INTENT_ANALYZER_SYSTEM`에 `ONTOLOGY_CLASS_GUIDE` 주입 | `app/prompts/intent_analyzer.py` |
| 수동 테스트: "복지 서비스 조례" 입력 → ordinance_type 추출 확인 | — |

**완료 기준**: `intent_analyzer_node` 호출 시 시스템 프롬프트에 OWL 클래스 계층이 포함됨

### S2 — graph_retriever SWRL 사전 계산 + State 이전
**예상 소요**: 45분

| 작업 | 파일 |
|------|------|
| `state.py`에 `hierarchy_chain`, `conflict_chain`, `penalty_extension` 필드 추가 (Optional, 빈 리스트 기본값) | `app/graph/state.py` |
| `graph_retriever_node`에 SWRL Rules 2-4 쿼리 블록 추가 | `app/graph/nodes/graph_retriever.py` |
| `legal_checker_node`의 SWRL Rules 2-4 DB 호출 → State 읽기로 교체 | `app/graph/nodes/legal_checker.py` |
| 로그 확인: `[graph_retriever] hierarchy=N건 conflict=N건 penalty_ext=N건` | — |

**완료 기준**: `legal_checker` 로그에서 SWRL DB 호출이 사라지고 State에서 읽음

### S3 — article_interviewer LegalTerm 힌트 (핵심 세션)
**예상 소요**: 60분

| 작업 | 파일 |
|------|------|
| `ARTICLE_ONTOLOGY_KEYWORDS` 딕셔너리 정의 (23개 조항키) | `app/graph/nodes/article_interviewer.py` |
| `article_interviewer_node` → `async def` + `db: GraphDBInterface` 파라미터 추가 | `app/graph/nodes/article_interviewer.py` |
| 힌트 조회 블록 추가 (find_legal_terms + 예외 처리) | `app/graph/nodes/article_interviewer.py` |
| `workflow.py`에서 `partial(article_interviewer_node, db=db)` 바인딩 | `app/graph/workflow.py` |
| 응답 시간 측정: 힌트 포함 조항 질문 ≤2초 확인 | — |

**완료 기준**: 조항 질문 응답 하단에 "관련 법령 용어" 섹션이 표시됨

### S4 — draft_reviewer SWRL State 활용
**예상 소요**: 30분

| 작업 | 파일 |
|------|------|
| `draft_reviewer_node`에서 `hierarchy_chain`, `conflict_chain` State 읽기 추가 | `app/graph/nodes/draft_reviewer.py` |
| `build_draft_revision_human()`에 `hierarchy_chain`, `conflict_chain` 파라미터 추가 + 섹션 빌드 | `app/prompts/draft_reviewer.py` |
| CLAUDE.md §온톨로지 워크플로우 통합 기록 | `CLAUDE.md` |

**완료 기준**: revise 경로에서 `build_draft_revision_human`이 위계 체계·충돌 섹션을 포함함

---

## 5. 위험 및 대응

| 위험 | 가능성 | 대응 |
|------|--------|------|
| `article_interviewer` async 전환 시 `workflow.py` partial 누락 | 중 | S3 완료 기준 항목에 workflow.py 변경 명시 / CLAUDE.md §주의사항에 async 노드 패턴 기록 |
| State 신규 필드로 기존 체크포인트 역호환 문제 | 중 | `state.py`에 `TypedDict` `total=False` 또는 `.get()` 기본값 처리 / LangGraph는 누락 필드를 `None`으로 채움 |
| AuraDB에 LegalTerm 노드 미충분 → 힌트 빈 결과 | 중 | 빈 결과 시 힌트 섹션 미표시 (graceful skip) — UX 저하 없음 |
| SWRL 사전 계산으로 graph_retriever 응답 지연 | 저 | 3개 SWRL 쿼리 모두 독립적 → `asyncio.gather`로 병렬 실행 검토 가능 |
| OWL rdf 파싱 실패 시 ONTOLOGY_CLASS_GUIDE 빈 문자열 | 저 | 기존 `try/except` fallback 유지 (`legal_terms.py` 패턴 재사용) |

---

## 6. 성공 지표

| 지표 | 측정 방법 |
|------|-----------|
| intent_analyzer 시스템 프롬프트에 OWL 클래스 계층 포함 | 로그 또는 프롬프트 출력 확인 |
| graph_retriever 응답에 `hierarchy_chain`, `conflict_chain`, `penalty_extension` 필드 존재 | `docker logs` + `[graph_retriever]` 로그 건수 확인 |
| legal_checker 로그에 SWRL DB 호출 제거 확인 | `grep "get_hierarchy_chain\|get_conflict_chain\|get_penalty_extension" logs` ≡ 0 |
| article_interviewer 조항 질문에 "관련 법령 용어" 섹션 표시 (LegalTerm 존재 시) | 배포 환경 수동 테스트 |
| draft_reviewer revision 프롬프트에 위계 체계 섹션 포함 | 로그 + 실제 수정 결과 확인 |
| 기존 워크플로우 회귀 없음 | Cloud Run 로그 에러 0건 |
