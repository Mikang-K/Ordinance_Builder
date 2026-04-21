# QA 직접 검색 (QA Direct Search) Design Document

> **Summary**: QAPanel에서 세션 컨텍스트 없이 질문 텍스트 자체를 임베딩하여 Neo4j 전체 DB를 벡터 검색하는 독립 엔드포인트 구현
>
> **Project**: 조례 빌더 AI (Ordinance Builder AI)
> **Author**: Mikang87
> **Date**: 2026-04-21
> **Status**: Draft
> **Planning Doc**: N/A (대화 기반 설계)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 현재 QA는 세션의 `ordinance_info`(지역·목적·대상·지원유형)로 검색 범위를 좁혀 조례와 무관한 법령 질문이나 세션 초기에는 유용한 결과를 얻기 어려움 |
| **WHO** | 조례 작성자 — 현재 작성 중인 조례와 직접 관련 없는 법령 개념도 자유롭게 질문하고 싶은 사용자 |
| **RISK** | 임베딩 비용 증가(질문마다 Gemini embed 호출), AuraDB Provision 임베딩 미적재 시 provision 벡터 검색 불가(ordinance 벡터 검색으로 fallback) |
| **SUCCESS** | 세션 없이도 `/api/v1/qa` 엔드포인트로 법령·조례 질의응답 가능, QAPanel에서 모드 전환 UI 동작 |
| **SCOPE** | 백엔드 신규 엔드포인트 + DB 메서드 2개 + 서비스 계층 + 프론트엔드 모드 전환 UI. 기존 `/session/{id}/qa` 엔드포인트는 변경 없음 |

---

## 1. Overview

### 1.1 Design Goals

- 기존 세션 기반 QA를 유지하면서, 질문 텍스트 임베딩 기반의 독립 검색 경로를 추가
- Clean Architecture: 직접 검색 로직을 `app/services/qa_service.py`로 분리하여 테스트 용이성 확보
- `GraphDBInterface` 추상화 계층 확장 — `vector_search_provisions()`, `vector_search_ordinances()` 추가

### 1.2 Design Principles

- 기존 코드 비파괴(기존 `/session/{id}/qa` 완전 유지)
- DB 추상화 계층(ABC) 통해 Mock↔Neo4j 교체 가능성 유지
- async 패턴 일관성 유지(`asyncio.to_thread` for sync DB calls)

---

## 2. Architecture

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | **Option B: Clean** | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | qa_chat 내 if-else 분기 | 독립 엔드포인트 + 서비스 계층 | 기존 엔드포인트 + 내부 헬퍼 |
| **New Files** | 0 | 1 (`qa_service.py`) | 0 |
| **Modified Files** | 5 | 6 | 6 |
| **Complexity** | Low | Medium | Medium |
| **Maintainability** | Medium | High | High |
| **Effort** | Low | Medium | Medium |
| **Risk** | 함수 비대화 | 낮음 | 같은 엔드포인트에 두 로직 |

**Selected**: Option B — **Rationale**: 세션 없이 독립 호출 가능한 구조, 서비스 계층 분리로 테스트 용이, 기존 엔드포인트 완전 비파괴

### 2.1 Component Diagram

```
QAPanel (frontend)
  ├── [세션 기반 모드]  POST /api/v1/session/{id}/qa  (기존, 변경 없음)
  └── [직접 검색 모드]  POST /api/v1/qa               (신규)
                              │
                    qa_service.direct_search_qa()      (신규)
                              │
               ┌──────────────┼──────────────┐
               ↓              ↓              ↓
  vector_search_provisions()  vector_search_ordinances()  find_legal_terms()
  (GraphDBInterface 신규)     (GraphDBInterface 신규)     (기존)
               │              │
         Neo4j idx_provision_embedding  Neo4j idx_ordinance_embedding
```

### 2.2 Data Flow — 직접 검색 모드

```
사용자 질문
  → POST /api/v1/qa { question }
  → qa_service.direct_search_qa()
      1. embedder.embed_query(question)   → [3072d vector]
      2. db.vector_search_provisions(vec) → legal_basis (최대 5건)
      3. db.vector_search_ordinances(vec) → similar_ordinances (최대 3건)
      4. db.find_legal_terms(q_keywords)  → legal_terms (최대 5건)
      5. build_qa_human_direct(...)       → LLM prompt
      6. llm.ainvoke(prompt)              → QAOutput
  → QAResponse 반환
```

**세션 기반 vs 직접 검색 차이점:**

| 항목 | 세션 기반 (기존) | 직접 검색 (신규) |
|------|----------------|----------------|
| 검색 키워드 소스 | `ordinance_info` (지역·목적 등) | 질문 텍스트 자체 임베딩 |
| 검색 방식 | DELEGATES → BASED_ON → 키워드 → 벡터 | 벡터 우선 → 키워드 fallback |
| 세션 의존성 | 필수 (session_id 필요) | 없음 (auth만 필요) |
| 조항 예시 | 캐시 재사용 (article_interviewing 시) | 없음 |
| 초안 컨텍스트 | `draft_full_text` 포함 | 없음 |

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `POST /api/v1/qa` | `qa_service`, `get_db()`, `get_llm()` | 엔드포인트 진입점 |
| `qa_service.direct_search_qa()` | `GraphDBInterface`, `embedder`, `LLM` | 직접 검색 비즈니스 로직 |
| `vector_search_provisions()` | Neo4j `idx_provision_embedding` | 조문 벡터 유사도 검색 |
| `vector_search_ordinances()` | Neo4j `idx_ordinance_embedding` | 조례 벡터 유사도 검색 |

---

## 3. Data Model

### 3.1 신규 Pydantic 스키마 (`app/api/schemas.py`)

```python
class QADirectRequest(BaseModel):
    question: str                  # 질문 텍스트

# 응답은 기존 QAResponse 재사용 (변경 없음)
# QAResponse: answer, sources, applicable_content, applicable_article_key
```

> `applicable_content` / `applicable_article_key`는 직접 검색 모드에서는 항상 `null` 반환
> (어느 조항에 적용할지 세션 컨텍스트 없이 판단 불가)

### 3.2 신규 DB 메서드 반환 형식

**`vector_search_provisions(embedding, limit) → list[dict]`**
```python
{
    "statute_id": str,
    "statute_title": str,
    "provision_article": str,
    "provision_content": str,
    "relation_type": "VECTOR_MATCH",
    "score": float           # cosine similarity
}
```

**`vector_search_ordinances(embedding, limit) → list[dict]`**
```python
{
    "ordinance_id": str,
    "region_name": str,
    "title": str,
    "similarity_score": float,
    "relevance_reason": str  # "벡터 유사도 기반 추천"
}
```

---

## 4. API Specification

### 4.1 신규 엔드포인트

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/v1/qa` | 직접 검색 QA (세션 독립) | Firebase 필수 |

### 4.2 상세 스펙

#### `POST /api/v1/qa`

**Request:**
```json
{
  "question": "보조금 지급 상한선 관련 법령이 있나요?"
}
```

**Response (200 OK):**
```json
{
  "answer": "보조금 관리에 관한 법률 제22조에 따르면...",
  "sources": [
    {
      "source_type": "statute",
      "title": "보조금 관리에 관한 법률",
      "article_no": "제22조",
      "content": "보조금의 지급 상한은...",
      "relation_type": "VECTOR_MATCH"
    }
  ],
  "applicable_content": null,
  "applicable_article_key": null
}
```

**Error Responses:**
- `400 Bad Request`: `question`이 빈 문자열
- `401 Unauthorized`: Firebase 토큰 없음
- `500 Internal Server Error`: LLM 호출 실패 또는 DB 오류

**Rate Limiting:** `20/minute` (기존 세션 QA와 동일)

---

## 5. UI/UX Design

### 5.1 QAPanel 모드 전환 UI

```
┌─────────────────────────────────────┐
│  🔍 법령·조례 질의응답              │
│                                     │
│  [세션 기반 ●] [직접 검색 ○]       │  ← 토글 버튼
│                                     │
│  직접 검색: 질문 텍스트를 임베딩하여  │  ← 모드 설명 (직접 검색 시 표시)
│  Neo4j 전체 법령·조례 DB 검색       │
│                                     │
│  질문을 입력하세요...               │
│  [전송]                             │
└─────────────────────────────────────┘
```

### 5.2 컴포넌트 변경 목록

| 컴포넌트 | 변경 내용 |
|---------|---------|
| `QAPanel.tsx` | `searchMode: 'session' \| 'direct'` state 추가, 토글 UI, 모드별 API 호출 분기 |
| `api.ts` | `searchDirectQuestion(question: string): Promise<QAResponse>` 추가 |
| `types.ts` | `QADirectRequest` 인터페이스 추가 (필요 시) |

### 5.3 Page UI Checklist

#### QAPanel (직접 검색 모드)

- [ ] 토글: "세션 기반" / "직접 검색" 전환 버튼 (두 옵션)
- [ ] 레이블: 현재 선택된 모드 강조 표시
- [ ] 텍스트: 직접 검색 모드 설명 안내 문구 (모드 전환 시 표시)
- [ ] 입력: 질문 textarea (기존과 동일)
- [ ] 버튼: 전송 (기존과 동일)
- [ ] "현재 조항에 적용하기" 버튼: 직접 검색 모드에서는 미표시 (`applicable_content` null)

---

## 6. Error Handling

| Code | 원인 | 처리 |
|------|------|------|
| `400` | `question` 빈 문자열 | 프론트엔드 validation으로 사전 차단 |
| `401` | Firebase 토큰 없음 | 로그인 페이지 리디렉션 |
| `500` | DB 오류 | DB 오류는 degraded mode(LLM 단독 답변) — LLM 오류는 500 반환 |

**Degraded Mode**: `vector_search_provisions()` / `vector_search_ordinances()` 실패 시, `find_legal_terms(keywords)` 만으로 LLM 호출. 빈 sources와 함께 답변 반환.

---

## 7. Security Considerations

- [ ] Firebase 인증 필수 (`Depends(get_current_user)`) — 기존 패턴 동일
- [ ] Rate Limiting `20/minute` 적용 (임베딩 비용 제어)
- [ ] `question` 길이 제한: Pydantic `max_length=500` 설정

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| L1: API Tests | `POST /api/v1/qa` 상태코드·응답 형식 | curl |
| L2: UI Action Tests | 모드 전환 토글, 직접 검색 결과 표시 | 브라우저 수동 |

### 8.2 L1: API Test Scenarios

| # | Endpoint | Method | 시나리오 | 예상 Status | 예상 응답 |
|---|----------|--------|---------|:-----------:|---------|
| 1 | `/api/v1/qa` | POST | 유효한 질문 | 200 | `answer` 비어있지 않음 |
| 2 | `/api/v1/qa` | POST | 빈 질문 문자열 | 400 | validation error |
| 3 | `/api/v1/qa` | POST | 인증 없음 | 401 | UNAUTHORIZED |
| 4 | `/api/v1/qa` | POST | DB 없는 환경 | 200 | degraded mode (sources=[], answer 비어있지 않음) |
| 5 | `/api/v1/qa` | POST | 법령 관련 질문 | 200 | `sources[0].source_type === "statute"` |

### 8.3 L2: UI Action Scenarios

| # | Page | Action | 예상 결과 |
|---|------|--------|---------|
| 1 | QAPanel | "직접 검색" 토글 클릭 | 모드 설명 텍스트 표시, 버튼 강조 전환 |
| 2 | QAPanel (직접) | 질문 전송 | `POST /api/v1/qa` 호출 (세션 ID 없음) |
| 3 | QAPanel (직접) | 결과 표시 | "적용하기" 버튼 미표시 |
| 4 | QAPanel (세션) | "세션 기반" 토글 클릭 | 기존 `POST /session/{id}/qa` 경로로 복귀 |

---

## 9. Clean Architecture — 레이어 배치

| 컴포넌트 | 레이어 | 위치 |
|---------|-------|------|
| `POST /api/v1/qa` 핸들러 | Presentation (API) | `app/api/routers/chat.py` |
| `direct_search_qa()` | Application (Service) | `app/services/qa_service.py` (신규) |
| `QADirectRequest` | Domain (Schema) | `app/api/schemas.py` |
| `vector_search_*()` | Infrastructure (DB) | `app/db/base.py`, `neo4j_db.py`, `mock_db.py` |
| `build_qa_human_direct()` | Infrastructure (Prompt) | `app/prompts/qa_agent.py` |

---

## 10. Coding Convention

- 신규 서비스 파일: `app/services/qa_service.py` — `async def direct_search_qa(...)` 패턴
- DB 메서드: `GraphDBInterface` ABC 추가 후 Neo4j 구현 → Mock 구현 순서로 작업
- 임베딩: `asyncio.to_thread(get_embedder().embed_query, question)` (sync → async 래핑)
- Rate limit: `@limiter.limit("20/minute")` + `request: Request` 파라미터 (기존 패턴 동일)

---

## 11. Implementation Guide

### 11.1 File Structure

```
app/
├── api/
│   ├── schemas.py          ← QADirectRequest 추가
│   └── routers/
│       └── chat.py         ← POST /api/v1/qa 엔드포인트 추가
├── db/
│   ├── base.py             ← vector_search_provisions(), vector_search_ordinances() 추가
│   ├── neo4j_db.py         ← 두 메서드 구현 (기존 쿼리 재활용)
│   └── mock_db.py          ← Mock 구현 (빈 리스트 반환)
├── services/
│   └── qa_service.py       ← 신규: direct_search_qa() 서비스 함수
└── prompts/
    └── qa_agent.py         ← build_qa_human_direct() 추가

frontend/src/
├── api.ts                  ← searchDirectQuestion() 추가
├── types.ts                ← (변경 없음, QAResponse 재사용)
└── components/
    └── QAPanel.tsx         ← searchMode state + 토글 UI
```

### 11.2 Implementation Order

1. [ ] `app/db/base.py` — `vector_search_provisions()`, `vector_search_ordinances()` 추상 메서드 추가
2. [ ] `app/db/neo4j_db.py` — 두 메서드 구현 (기존 `find_legal_basis` 내 쿼리 분리 추출)
3. [ ] `app/db/mock_db.py` — Mock 구현 (빈 리스트 반환)
4. [ ] `app/prompts/qa_agent.py` — `build_qa_human_direct()` 추가
5. [ ] `app/services/qa_service.py` — `direct_search_qa()` 서비스 구현 (신규 파일)
6. [ ] `app/api/schemas.py` — `QADirectRequest` 추가
7. [ ] `app/api/routers/chat.py` — `POST /api/v1/qa` 엔드포인트 추가
8. [ ] `frontend/src/api.ts` — `searchDirectQuestion()` 추가
9. [ ] `frontend/src/components/QAPanel.tsx` — 모드 전환 토글 UI 추가

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | 예상 턴 |
|--------|-----------|-------------|:------:|
| DB 계층 | `module-1` | base.py + neo4j_db.py + mock_db.py | 8-10 |
| 서비스 + 프롬프트 | `module-2` | qa_service.py + qa_agent.py + schemas.py | 6-8 |
| 엔드포인트 + 프론트 | `module-3` | chat.py 엔드포인트 + api.ts + QAPanel.tsx | 8-10 |

#### Recommended Session Plan

| Session | Phase | Scope | 예상 턴 |
|---------|-------|-------|:------:|
| Session 1 | Design | 전체 | 현재 |
| Session 2 | Do | `--scope module-1` (DB 계층) | 20-25 |
| Session 3 | Do | `--scope module-2,module-3` (서비스+프론트) | 30-35 |
| Session 4 | Check + Report | 전체 | 20-25 |

---

## 12. Key Implementation Notes

### `vector_search_provisions()` — Neo4j 구현

`find_legal_basis()` 내에 이미 `provision_vector_query`가 존재하므로, 해당 쿼리를 분리 추출합니다.

```python
def vector_search_provisions(self, embedding: list[float], limit: int = 5) -> list[dict]:
    query = """
    CALL db.index.vector.queryNodes('idx_provision_embedding', $limit, $embedding)
    YIELD node AS p, score
    MATCH (s:Statute)-[:CONTAINS]->(p)
    RETURN DISTINCT
           s.id           AS statute_id,
           s.title        AS statute_title,
           p.article_no   AS provision_article,
           p.content_text AS provision_content,
           'VECTOR_MATCH'  AS relation_type
    ORDER BY score DESC
    LIMIT $limit
    """
    with self._driver.session() as session:
        result = session.run(query, embedding=embedding, limit=limit)
        return [dict(r) for r in result]
```

> **AuraDB 주의**: `SKIP_PROVISION_EMBEDDING=true`로 적재된 환경에서는 빈 리스트 반환.
> `qa_service`에서 `vector_search_provisions()` 실패 시 `find_legal_terms(keywords)` fallback 사용.

### `direct_search_qa()` — qa_service.py

```python
async def direct_search_qa(
    question: str,
    db: GraphDBInterface | None,
    llm,
) -> tuple[QAOutput, list[dict], list[dict]]:
    """
    질문 임베딩 → 벡터 검색 → LLM 답변.
    반환: (QAOutput, legal_basis, legal_terms)
    """
    embedding: list[float] = []
    legal_basis: list[dict] = []
    legal_terms: list[dict] = []

    if db:
        try:
            embedding = await asyncio.to_thread(get_embedder().embed_query, question)
            legal_basis, legal_terms = await asyncio.gather(
                asyncio.to_thread(db.vector_search_provisions, embedding),
                asyncio.to_thread(db.find_legal_terms, [w for w in question.split() if len(w) >= 2][:10]),
            )
            # Provision 벡터 결과 없으면 ordinance 벡터 결과로 보완
            if not legal_basis:
                ordinances = await asyncio.to_thread(db.vector_search_ordinances, embedding)
                # ordinance 결과는 sources에 'ordinance' 타입으로 별도 포함 (엔드포인트에서 처리)
        except Exception:
            logger.warning("직접 검색 DB 오류 — LLM 단독 답변으로 계속")

    human_text = build_qa_human_direct(question, legal_basis, legal_terms)
    structured_llm = llm.with_structured_output(QAOutput)
    result = await structured_llm.ainvoke([SystemMessage(content=QA_SYSTEM), HumanMessage(content=human_text)])
    return result, legal_basis, legal_terms
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-21 | Initial draft — Option B (Clean) 선택 | Mikang87 |
