# Design: 워크플로우 전반 온톨로지 통합 (ontology-workflow-integration)

**작성일**: 2026-05-12
**상태**: Design
**단계**: Design
**아키텍처**: Option C — OntologyContext 미들웨어 레이어

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | OWL 온톨로지와 SWRL 추론 결과가 3개 노드에만 고립되어 있어, 사용자가 조항을 입력할 때 법령 용어 안내가 없고 초안 수정 시 위계 체계가 미반영됨. 온톨로지 지식을 전 워크플로우로 흘려보내야 법적 완성도가 높아짐 |
| **WHO** | 조항 입력 중인 사용자(조항별 법령 용어 힌트), 초안 수정 사용자(위계 체계 반영 수정), intent_analyzer(정확한 조례 유형 분류) |
| **RISK** | `article_interviewer` async 전환 시 `workflow.py` partial 누락 → `TypeError` / State 신규 필드 → LangGraph checkpointer 마이그레이션 주의 / AuraDB LegalTerm 미충분 → graceful skip / SWRL 사전 계산 3쿼리 추가 → graph_retriever 응답 지연 |
| **SUCCESS** | 4개 노드 모두 온톨로지 활용 / 기존 워크플로우 회귀 없음 / article_interviewer 응답 ≤2초 |
| **SCOPE** | `app/core/ontology_context.py`(신규), `app/graph/state.py`, `app/prompts/legal_terms.py`, `app/prompts/intent_analyzer.py`, `app/graph/nodes/intent_analyzer.py`, `app/graph/nodes/graph_retriever.py`, `app/graph/nodes/article_interviewer.py`, `app/graph/nodes/legal_checker.py`, `app/graph/nodes/draft_reviewer.py`, `app/prompts/draft_reviewer.py`, `app/graph/workflow.py` |

---

## 1. 아키텍처 개요

### 1.1 Option C 핵심 원칙

| 원칙 | 설명 |
|------|------|
| **단일 진입점** | 모든 온톨로지 접근은 `OntologyContext` 한 곳을 통함 (RDF 파싱 + DB 쿼리 통합) |
| **기존 partial 패턴 준수** | `partial(node_fn, ontology_ctx=ontology_ctx)` — `llm`, `db` 주입 패턴과 동일 |
| **SWRL 결과 State 저장** | `graph_retriever`에서 한 번 계산 → State → 하위 노드는 State 읽기 (DB 재쿼리 없음) |
| **정적/동적 분리** | RDF 기반(클래스 계층·term guide)은 모듈 상수 / DB 기반(SWRL·LegalTerm)은 런타임 |
| **Graceful Degradation** | 모든 온톨로지 호출 `try/except` — DB 미응답 시 힌트 생략, 워크플로우 계속 |

### 1.2 레이어별 변경 범위

```
[ordinance.rdf]           ← 기존 그대로 (owl-swrl-enrichment에서 완성)
         ↓ rdflib 파싱
[legal_terms.py]          ← ONTOLOGY_CLASS_GUIDE 모듈 상수 추가
         ↓ 정적 주입
[intent_analyzer_system]  ← OWL 클래스 계층 포함 (import 시 자동 반영)

[app/core/ontology_context.py]  ← 신규: OntologyContext 클래스
   ├── precompute_swrl(keywords) → SWRLContext  (async DB 쿼리)
   └── get_article_hints(article_key) → str     (async DB 쿼리)
         ↓ functools.partial
[graph_retriever_node]    ← ontology_ctx.precompute_swrl() → State 저장
[article_interviewer_node] ← ontology_ctx.get_article_hints() → 질문 하단 표시

[state.py]                ← hierarchy_chain, conflict_chain, penalty_extension 필드 추가
         ↓ State 읽기
[legal_checker_node]      ← State.hierarchy_chain/conflict_chain/penalty_extension
[draft_reviewer_node]     ← State.hierarchy_chain/conflict_chain → revision 프롬프트

[workflow.py]             ← OntologyContext 싱글톤 생성 + partial 바인딩
```

### 1.3 노드별 온톨로지 연결 전후 비교

| 노드 | 이전 | 이후 |
|------|------|------|
| `intent_analyzer` | 유형 목록 수동 나열 | `ONTOLOGY_CLASS_GUIDE` 정적 주입 (모듈 상수) |
| `graph_retriever` | SWRL Rule 1만 계산 | `OntologyContext.precompute_swrl()` → Rules 1-4 State 저장 |
| `article_interviewer` | 정적 질문만 | `OntologyContext.get_article_hints()` → LegalTerm 힌트 표시 |
| `drafting_agent` | ONTOLOGY_TERM_GUIDE ✅ | 변경 없음 |
| `draft_reviewer` | ONTOLOGY_TERM_GUIDE만 | State.hierarchy_chain/conflict_chain → revision 프롬프트 |
| `legal_checker` | SWRL Rules 2-4 DB 재쿼리 | State 읽기로 교체 (중복 쿼리 제거) |

---

## 2. `OntologyContext` 클래스 설계

### 2.1 파일: `app/core/ontology_context.py`

```python
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.base import GraphDBInterface

logger = logging.getLogger(__name__)


@dataclass
class SWRLContext:
    """SWRL Rules 2-4 사전 계산 결과. graph_retriever → State에 저장."""
    hierarchy_chain: list[dict] = field(default_factory=list)    # Rule 2
    conflict_chain: list[dict] = field(default_factory=list)     # Rule 3
    penalty_extension: list[dict] = field(default_factory=list)  # Rule 4


class OntologyContext:
    """
    온톨로지 미들웨어 레이어.
    
    - 정적 (RDF 기반): 모듈 임포트 시 계산된 값을 반환 (class_guide, term_guide)
    - 동적 (DB 기반): 런타임에 keywords로 DB를 쿼리하고 결과를 반환
    
    workflow.py에서 db와 함께 싱글톤으로 생성되고,
    functools.partial로 필요한 노드에 주입됩니다.
    """

    def __init__(self, db: GraphDBInterface) -> None:
        self._db = db

    # ── 동적 메서드 (DB 쿼리) ─────────────────────────────────────────────────

    async def precompute_swrl(self, keywords: list[str]) -> SWRLContext:
        """
        SWRL Rules 2-4를 병렬 실행하여 SWRLContext 반환.
        graph_retriever에서 호출 → 결과를 State에 저장.
        """
        import asyncio

        async def _safe(coro, default):
            try:
                return await asyncio.to_thread(coro)
            except Exception as exc:
                logger.debug("SWRL 쿼리 생략: %s", exc)
                return default

        hierarchy, conflict, penalty = await asyncio.gather(
            _safe(lambda: self._db.get_hierarchy_chain(keywords=keywords), []),
            _safe(lambda: self._db.get_conflict_chain(keywords=keywords), []),
            _safe(lambda: self._db.get_penalty_extension(keywords=keywords), []),
        )
        return SWRLContext(
            hierarchy_chain=hierarchy,
            conflict_chain=conflict,
            penalty_extension=penalty,
        )

    async def get_article_hints(self, article_key: str, hint_keywords: list[str]) -> str:
        """
        조항 키에 맞는 LegalTerm 힌트 텍스트 반환.
        article_interviewer에서 다음 조항 질문 시 호출.
        DB 미응답 또는 LegalTerm 없으면 빈 문자열 반환.
        """
        try:
            import asyncio
            legal_terms: list[dict] = await asyncio.to_thread(
                lambda: self._db.find_legal_terms(keywords=hint_keywords, limit=3)
            )
            if not legal_terms:
                return ""
            lines = [
                f"  • **{t['term_name']}**: {t['definition'][:120]}"
                + (f" _(출처: {t['source_statute']})_" if t.get("source_statute") else "")
                for t in legal_terms
            ]
            return "\n\n---\n**관련 법령 용어** (OWL 온톨로지 기반)\n" + "\n".join(lines)
        except Exception as exc:
            logger.debug("온톨로지 힌트 생략 (article=%s): %s", article_key, exc)
            return ""
```

### 2.2 `asyncio.to_thread` 사용 이유

`GraphDBInterface`의 DB 메서드(`find_legal_terms`, `get_hierarchy_chain` 등)는 동기(sync) 함수입니다.
`article_interviewer_node`가 `async def`이므로, 동기 DB 호출을 이벤트 루프 블로킹 없이 실행하려면
`asyncio.to_thread()`로 스레드 풀에 위임해야 합니다.

---

## 3. State 스키마 변경

### 3.1 `app/graph/state.py` — 신규 필드 3개

```python
# --- SWRL 사전 계산 결과 (graph_retriever에서 저장, 하위 노드에서 읽기) ---
# LangGraph TypedDict는 누락 필드를 None으로 채우므로 기존 체크포인트 호환
hierarchy_chain: list[dict]      # SWRL Rule 2 — 위계 전이성 체인
conflict_chain: list[dict]       # SWRL Rule 3 — 충돌 연쇄
penalty_extension: list[dict]    # SWRL Rule 4 — 벌칙 범위 확장
```

> **체크포인트 호환성**: LangGraph `TypedDict` 기반 State는 새 필드가 추가되어도
> 기존 PostgreSQL 체크포인트에서 해당 필드가 없으면 `None`으로 초기화됩니다.
> 코드에서 `state.get("hierarchy_chain") or []` 패턴으로 안전하게 접근할 수 있습니다.

---

## 4. 노드별 변경 설계

### 4.1 `legal_terms.py` — `ONTOLOGY_CLASS_GUIDE` 추가

```python
# app/prompts/legal_terms.py — 기존 _build_from_rdf 함수 아래 추가

def _build_class_hierarchy_section(g: Graph) -> str:
    """
    OWL 자치법규의 하위 클래스 목록을 추출해 intent_analyzer용 분류 가이드 반환.
    
    조례(지원/설치·운영/관리·규제/복지·서비스) 하위 유형이
    intent_analyzer 시스템 프롬프트에 OWL 정의 기반으로 주입됨.
    """
    lines = []
    try:
        자치법규_uri = URIRef(_NS + "자치법규")
        for cls in sorted(g.subjects(RDFS.subClassOf, 자치법규_uri)):
            name = _local(cls)
            label_ko = next(
                (str(lb) for lb in g.objects(cls, RDFS.label) if getattr(lb, "language", None) == "ko"),
                name,
            )
            comment = next(g.objects(cls, RDFS.comment), None)
            entry = f"  - {label_ko}"
            if comment:
                entry += f": {str(comment)[:80]}"
            lines.append(entry)
    except Exception:
        pass
    if not lines:
        # RDF에 조례 하위 클래스가 없으면 하드코딩 fallback
        lines = [
            "  - 지원: 보조금·지원금·현물 지원 목적",
            "  - 설치·운영: 위원회·센터 설치 및 운영",
            "  - 관리·규제: 시설 관리·사용 허가·과태료·규제",
            "  - 복지·서비스: 돌봄·복지서비스·급여·방문서비스",
        ]
    return "[조례 하위 유형 (OWL 자치법규 클래스 계층)]\n" + "\n".join(lines)


# 기존 _rdf_section 빌드 블록 아래 추가
try:
    _class_section = _build_class_hierarchy_section(
        Graph().parse(str(_RDF_PATH), format="xml") if _RDF_PATH.exists() else Graph()
    )
except Exception:
    _class_section = _build_class_hierarchy_section(Graph())

ONTOLOGY_CLASS_GUIDE: str = _class_section
```

> **주의**: `_build_class_hierarchy_section`은 `_build_from_rdf`와 별도로 Graph 인스턴스를 파싱합니다.
> 모듈 임포트 시점에 한 번만 실행되며, `try/except`로 감싸져 있어 파싱 실패 시 하드코딩 fallback을 반환합니다.

### 4.2 `intent_analyzer.py` — `ONTOLOGY_CLASS_GUIDE` 주입

```python
# app/prompts/intent_analyzer.py

from app.prompts.legal_terms import ONTOLOGY_CLASS_GUIDE  # 신규 import

INTENT_ANALYZER_SYSTEM = f"""
당신은 지방 조례 전문 AI 보조관입니다.
사용자의 자연어 입력에서 조례 작성에 필요한 구조화된 정보를 추출하는 것이 역할입니다.

추출 규칙:
1. 언급되지 않은 필드는 반드시 null로 설정하세요.
2. 지역명은 공식 행정구역명으로 정규화하세요 ...
...

{ONTOLOGY_CLASS_GUIDE}
""".strip()
```

> `intent_analyzer_node` 코드 변경 없음. 프롬프트 모듈 변경만으로 적용됩니다.

### 4.3 `graph_retriever.py` — `OntologyContext.precompute_swrl()` 호출

```python
# app/graph/nodes/graph_retriever.py

from app.core.ontology_context import OntologyContext, SWRLContext  # 신규

def graph_retriever_node(
    state: OrdinanceBuilderState,
    db: GraphDBInterface,
    ontology_ctx: OntologyContext | None = None,  # 신규 파라미터
) -> dict:
    ...
    # 기존 SWRL Rule 1 (위임 상속) 블록 유지
    # 신규: SWRL Rules 2-4 사전 계산
    swrl = SWRLContext()  # 기본값: 빈 리스트들
    if ontology_ctx and keywords:
        try:
            import asyncio
            swrl = asyncio.get_event_loop().run_until_complete(
                ontology_ctx.precompute_swrl(keywords=keywords)
            )
        except Exception as swrl_exc:
            logger.debug("SWRL 사전 계산 생략: %s", swrl_exc)

    logger.debug(
        "[graph_retriever] hierarchy=%d건 conflict=%d건 penalty_ext=%d건",
        len(swrl.hierarchy_chain), len(swrl.conflict_chain), len(swrl.penalty_extension),
    )

    return {
        ...기존 필드...,
        "hierarchy_chain": swrl.hierarchy_chain,
        "conflict_chain": swrl.conflict_chain,
        "penalty_extension": swrl.penalty_extension,
    }
```

> **비동기 주의**: `graph_retriever_node`는 현재 동기 함수입니다(LLM 호출 없음).
> `OntologyContext.precompute_swrl()`은 async이므로 `asyncio.get_event_loop().run_until_complete()`로 호출합니다.
> 대안: `graph_retriever_node`를 `async def`로 전환 후 `await ontology_ctx.precompute_swrl()`. 
> 단순성을 위해 동기 유지 + `run_until_complete` 패턴 채택.

### 4.4 `article_interviewer.py` — async 전환 + `OntologyContext` 힌트

```python
# app/graph/nodes/article_interviewer.py

from app.core.ontology_context import OntologyContext  # 신규

# 조항키 → 온톨로지 검색 키워드 매핑 (23개 조항키)
ARTICLE_ONTOLOGY_KEYWORDS: dict[str, list[str]] = {
    "목적":     ["목적", "공익", "활성화"],
    "정의":     ["정의", "청년", "창업", "지원"],
    "지원대상": ["자격", "지원대상", "청년"],
    "지원내용": ["보조금", "지원", "급부"],
    "지원금액": ["한도", "지원금", "예산"],
    "신청방법": ["신청", "접수", "서류"],
    "심사선정": ["심사", "선정", "위원회"],
    "환수제재": ["환수", "제재", "벌칙", "과태료"],
    "위임":     ["위임", "규칙", "시행"],
    "설치":     ["설치", "기관", "소속"],
    "구성":     ["위원", "임기", "구성"],
    "직무":     ["직무", "권한", "의결"],
    "운영":     ["운영", "회의", "정족수"],
    "간사":     ["간사", "사무", "공무원"],
    "적용범위": ["적용", "범위", "시설"],
    "관리책임": ["관리", "책임", "위탁"],
    "사용허가": ["허가", "신청", "취소"],
    "사용료":   ["사용료", "감면", "징수"],
    "위반제재": ["과태료", "위반", "제재"],
    "서비스내용": ["서비스", "돌봄", "급여"],
    "제공기관": ["제공기관", "위탁", "지정"],
    "신청접수": ["신청", "접수", "자격"],
    "비용":     ["비용", "본인부담", "감면"],
}


async def article_interviewer_node(           # def → async def (변경)
    state: OrdinanceBuilderState,
    ontology_ctx: OntologyContext | None = None,  # 신규 파라미터
) -> dict:
    ...
    # ── 다음 조항 질문 분기 ─────────────────────────────────────────────────
    next_key = article_queue[0]
    ...
    # 온톨로지 힌트 조회 (다음 조항에만, 빈 결과 시 블록 미표시)
    ontology_hints_block = ""
    if ontology_ctx and next_key in ARTICLE_ONTOLOGY_KEYWORDS:
        hint_kw = ARTICLE_ONTOLOGY_KEYWORDS[next_key]
        ontology_hints_block = await ontology_ctx.get_article_hints(next_key, hint_kw)

    response = (
        f"✓ **{current_title}** {saved_label}\n\n"
        f"━━━ **{filled_count + 1} / {total}** ━━━\n\n"
        f"**[{next_title}]**\n\n"
        f"{next_question}"
        f"{examples_block}"
        f"{ontology_hints_block}"   # 온톨로지 힌트 (있을 때만 표시)
    )
```

### 4.5 `legal_checker.py` — State 읽기로 전환 (DB 재쿼리 제거)

```python
# app/graph/nodes/legal_checker.py

async def legal_checker_node(state, llm, db=None) -> dict:
    ...
    # SWRL Rules 2-4: DB 재쿼리 → State 읽기로 교체
    # graph_retriever에서 이미 계산했으므로 중복 제거

    # Before (제거):
    # hierarchy_chain = db.get_hierarchy_chain(keywords=keywords)
    # conflict_chain = db.get_conflict_chain(keywords=keywords)
    # penalty_extension = db.get_penalty_extension(keywords=keywords)

    # After (신규):
    hierarchy_chain: list[dict] = state.get("hierarchy_chain") or []
    conflict_chain: list[dict] = state.get("conflict_chain") or []
    penalty_extension: list[dict] = state.get("penalty_extension") or []

    # SUPERIOR_TO, PENALIZES는 legal_checker 고유 — 유지
    superior_provisions = db.get_superior_statute_provisions(keywords=keywords) if db else []
    penalty_chain = db.get_penalty_chain(keywords=keywords) if db else []
```

> `db` 파라미터는 `get_superior_statute_provisions`, `get_penalty_chain`을 위해 유지.
> `get_hierarchy_chain`, `get_conflict_chain`, `get_penalty_extension`은 State로 대체되므로
> `legal_checker`에서 더 이상 직접 호출하지 않습니다.

### 4.6 `draft_reviewer.py` — State SWRL 활용 (revision 경로)

```python
# app/graph/nodes/draft_reviewer.py

async def draft_reviewer_node(state, llm) -> dict:
    ...
    # State에서 SWRL 결과 읽기 (graph_retriever가 저장한 값)
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

### 4.7 `draft_reviewer.py` 프롬프트 — `build_draft_revision_human` 확장

```python
# app/prompts/draft_reviewer.py

def build_draft_revision_human(
    user_request: str,
    draft_full_text: str,
    draft_articles: list[dict],
    hierarchy_chain: list[dict] | None = None,  # 신규 (기본값 None → 하위 호환)
    conflict_chain: list[dict] | None = None,   # 신규
) -> str:
    articles_text = "\n\n".join(
        f"{a['article_no']} {a['title']}\n{a['content']}"
        for a in draft_articles
    )

    # SWRL Rule 2 — 위계 체계 섹션
    hierarchy_section = ""
    if hierarchy_chain:
        lines = [
            f"  [depth={h['depth']}] {h['statute_title']} ({h.get('statute_category','')}) "
            f"→ {h['ordinance_title']}"
            for h in hierarchy_chain[:5]
        ]
        hierarchy_section = "\n\n## 수정 시 준수해야 할 법적 위계 체계\n" + "\n".join(lines)

    # SWRL Rule 3 — 충돌 위험 섹션
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

### 4.8 `workflow.py` — `OntologyContext` 싱글톤 + 노드 바인딩

```python
# app/graph/workflow.py

from app.core.ontology_context import OntologyContext  # 신규

def create_workflow(checkpointer):
    ...
    db = Neo4jGraphDB(...)
    _db_instance = db

    # OntologyContext 싱글톤 생성 (db와 함께 한 번만)
    ontology_ctx = OntologyContext(db=db)

    builder.add_node("intent_analyzer",
        partial(intent_analyzer_node, llm=intent_llm))
    # intent_analyzer는 ONTOLOGY_CLASS_GUIDE를 모듈 상수로 사용 → OntologyContext 주입 불필요

    builder.add_node("graph_retriever",
        partial(graph_retriever_node, db=db, ontology_ctx=ontology_ctx))  # 변경

    builder.add_node("article_interviewer",
        partial(article_interviewer_node, ontology_ctx=ontology_ctx))    # 변경 (db 제거, ctx 추가)

    builder.add_node("legal_checker",
        partial(legal_checker_node, llm=legal_llm, db=db))              # 변경 없음

    builder.add_node("draft_reviewer",
        partial(draft_reviewer_node, llm=reviewer_llm))                  # 변경 없음 (State 읽기)
    ...
```

---

## 5. 데이터 흐름도

### 5.1 온톨로지 데이터 흐름 (한 세션 기준)

```
앱 시작
  └── create_workflow()
        ├── Neo4jGraphDB()  → db 싱글톤
        └── OntologyContext(db) → ontology_ctx 싱글톤

                        ┌── [모듈 임포트 시] ──────────────────────────────────┐
legal_terms.py          │  ONTOLOGY_CLASS_GUIDE ← _build_class_hierarchy_section(rdf)
intent_analyzer.py      │  INTENT_ANALYZER_SYSTEM = f"...{ONTOLOGY_CLASS_GUIDE}..."
                        └──────────────────────────────────────────────────────┘

사용자 첫 메시지
  → intent_analyzer_node
        → INTENT_ANALYZER_SYSTEM (ONTOLOGY_CLASS_GUIDE 포함) → Gemini
        → ordinance_type 추출 정확도 향상

정보 수집 완료 후
  → graph_retriever_node(state, db, ontology_ctx)
        ├── [기존] db.find_legal_basis() → legal_basis
        ├── [기존] db.find_similar_ordinances() → similar_ordinances
        ├── [기존] SWRL Rule 1: db.get_delegation_limits() → legal_basis 병합
        └── [신규] ontology_ctx.precompute_swrl(keywords) → SWRLContext
                    ├── Rule 2: db.get_hierarchy_chain() → hierarchy_chain
                    ├── Rule 3: db.get_conflict_chain() → conflict_chain
                    └── Rule 4: db.get_penalty_extension() → penalty_extension
        → State: {legal_basis, hierarchy_chain, conflict_chain, penalty_extension, ...}

  → article_planner_node → 조항 순서 결정

  → article_interviewer_node(state, ontology_ctx) [per 조항]
        ├── 다음 조항 키 = next_key
        ├── hint_kw = ARTICLE_ONTOLOGY_KEYWORDS[next_key]
        └── [신규] ontology_ctx.get_article_hints(next_key, hint_kw)
                    → db.find_legal_terms(hint_kw) → LegalTerm 힌트 텍스트
        → 응답: 기존 질문 + examples_block + ontology_hints_block

  → drafting_agent_node [조항 완료 후]
        → ONTOLOGY_TERM_GUIDE 포함 (기존 유지)

  → draft_reviewer_node [사용자 revise 요청 시]
        ├── hierarchy_chain = state.get("hierarchy_chain") or []  [State 읽기]
        ├── conflict_chain = state.get("conflict_chain") or []    [State 읽기]
        └── build_draft_revision_human(..., hierarchy_chain, conflict_chain)
              → SWRL 위계·충돌 섹션 포함 revision 프롬프트

  → legal_checker_node [confirm 후]
        ├── hierarchy_chain = state.get("hierarchy_chain") or []  [State 읽기, DB 재쿼리 없음]
        ├── conflict_chain = state.get("conflict_chain") or []    [State 읽기]
        ├── penalty_extension = state.get("penalty_extension") or [] [State 읽기]
        └── [유지] db.get_superior_statute_provisions() + db.get_penalty_chain()
```

---

## 6. 에러 처리 설계

### 6.1 `OntologyContext` 예외 처리 매트릭스

| 시나리오 | 영향 노드 | 동작 |
|----------|----------|------|
| AuraDB 연결 끊김 | graph_retriever | `SWRLContext(빈 리스트)` 반환, 워크플로우 계속 |
| LegalTerm 노드 없음 | article_interviewer | `""` 반환, 힌트 섹션 미표시 |
| `ordinance.rdf` 파싱 실패 | intent_analyzer (프롬프트 생성 시) | 하드코딩 fallback 텍스트 사용 |
| `asyncio.to_thread` 타임아웃 | article_interviewer | `except Exception` 캐치 → 힌트 없이 응답 |
| State 필드 없음 (기존 세션) | draft_reviewer, legal_checker | `.get("hierarchy_chain") or []` → 빈 리스트 |

### 6.2 로그 패턴

```python
# graph_retriever 정상
logger.debug("[graph_retriever] hierarchy=%d건 conflict=%d건 penalty_ext=%d건", ...)

# graph_retriever SWRL 생략
logger.debug("SWRL 사전 계산 생략: %s", swrl_exc)

# article_interviewer 힌트 생략
logger.debug("온톨로지 힌트 생략 (article=%s): %s", next_key, exc)

# legal_checker State 읽기 확인
logger.debug(
    "[legal_checker] State에서 읽기 — hierarchy=%d건 conflict=%d건 penalty_ext=%d건",
    len(hierarchy_chain), len(conflict_chain), len(penalty_extension),
)
```

---

## 7. 변경 파일 목록

| 파일 | 유형 | 변경 내용 |
|------|------|-----------|
| `app/core/ontology_context.py` | **신규** | `OntologyContext` 클래스 + `SWRLContext` 데이터클래스 |
| `app/graph/state.py` | 수정 | `hierarchy_chain`, `conflict_chain`, `penalty_extension` 필드 추가 |
| `app/prompts/legal_terms.py` | 수정 | `_build_class_hierarchy_section()`, `ONTOLOGY_CLASS_GUIDE` 상수 추가 |
| `app/prompts/intent_analyzer.py` | 수정 | `ONTOLOGY_CLASS_GUIDE` import + 시스템 프롬프트 주입 |
| `app/graph/nodes/graph_retriever.py` | 수정 | `ontology_ctx` 파라미터 + `precompute_swrl()` 호출 + State 반환 |
| `app/graph/nodes/article_interviewer.py` | 수정 | `async def` 전환 + `ontology_ctx` 파라미터 + `ARTICLE_ONTOLOGY_KEYWORDS` + 힌트 표시 |
| `app/graph/nodes/legal_checker.py` | 수정 | SWRL Rules 2-4 DB 호출 → State 읽기 교체 |
| `app/graph/nodes/draft_reviewer.py` | 수정 | `hierarchy_chain`, `conflict_chain` State 읽기 + revision 프롬프트 전달 |
| `app/prompts/draft_reviewer.py` | 수정 | `build_draft_revision_human()` 파라미터 + 위계·충돌 섹션 추가 |
| `app/graph/workflow.py` | 수정 | `OntologyContext` 생성 + `graph_retriever`, `article_interviewer` partial 바인딩 변경 |

---

## 8. 테스트 계획

### L1 — 로그 기반 검증 (배포 환경)

| 테스트 항목 | 검증 방법 |
|------------|-----------|
| intent_analyzer 프롬프트에 OWL 클래스 계층 포함 | Cloud Run 로그에서 `ONTOLOGY_CLASS_GUIDE` 내용 확인 |
| graph_retriever SWRL 사전 계산 건수 기록 | `[graph_retriever] hierarchy=N건` 로그 > 0 (AuraDB 데이터 있을 시) |
| legal_checker State 읽기 전환 확인 | `[legal_checker] State에서 읽기` 로그 출력 확인 |
| article_interviewer 힌트 표시 | 실제 UI에서 조항 질문 시 "관련 법령 용어" 섹션 확인 |
| draft_reviewer revision 위계 섹션 | Cloud Run 로그 + 실제 수정 응답에 위계 체계 반영 확인 |

### L2 — 회귀 테스트 (기존 워크플로우)

| 시나리오 | 예상 결과 |
|----------|----------|
| AuraDB 연결 없이 워크플로우 실행 | 모든 온톨로지 호출 graceful skip, 기존 흐름 유지 |
| 기존 세션 복원 (`hierarchy_chain` State 없음) | `.get() or []`로 안전 처리, legal_checker 정상 실행 |
| `article_interviewer` async 전환 후 `/articles_batch` 엔드포인트 | DraftModal 정상 열림 확인 |
| OWL 파일 없는 환경 | `ONTOLOGY_CLASS_GUIDE` fallback 텍스트 사용, 앱 시작 정상 |

---

## 9. 구현 가이드

### 9.1 구현 순서 (의존성 기반)

```
Step 1: app/core/ontology_context.py 신규 생성 (의존성 없음)
Step 2: app/graph/state.py 필드 추가 (의존성 없음)
Step 3: app/prompts/legal_terms.py ONTOLOGY_CLASS_GUIDE 추가
Step 4: app/prompts/intent_analyzer.py ONTOLOGY_CLASS_GUIDE 주입
Step 5: app/graph/nodes/graph_retriever.py ontology_ctx 추가
Step 6: app/graph/nodes/legal_checker.py State 읽기 전환
Step 7: app/graph/nodes/article_interviewer.py async + ontology_ctx
Step 8: app/prompts/draft_reviewer.py build_draft_revision_human 확장
Step 9: app/graph/nodes/draft_reviewer.py State 읽기 + 프롬프트 전달
Step 10: app/graph/workflow.py OntologyContext + 바인딩 변경
Step 11: CLAUDE.md 변경 내용 기록
```

### 9.2 세션 가이드 (Module Map)

| 모듈 | 파일 수 | 예상 소요 | 내용 |
|------|---------|-----------|------|
| **M1 — 기반 레이어** | 3 | 45분 | `ontology_context.py`(신규) + `state.py` + `legal_terms.py` |
| **M2 — intent_analyzer** | 1 | 15분 | `intent_analyzer.py` 프롬프트 수정 |
| **M3 — graph_retriever + legal_checker** | 2 | 30분 | SWRL 사전 계산 + State 읽기 전환 |
| **M4 — article_interviewer** | 1 | 45분 | async 전환 + 힌트 표시 |
| **M5 — draft_reviewer** | 2 | 30분 | State 읽기 + 프롬프트 확장 |
| **M6 — workflow + CLAUDE.md** | 2 | 15분 | OntologyContext 바인딩 + 문서화 |

**추천 세션 분할**:
- 세션 1: M1 + M2 + M3 (기반 레이어 + 정적 주입 + SWRL 이전)
- 세션 2: M4 + M5 + M6 (동적 DB 호출 + 검토 단계 + 마무리)
