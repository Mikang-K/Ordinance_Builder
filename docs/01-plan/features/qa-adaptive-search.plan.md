# Plan: QA 적응형 DB 검색 — 질문 유형 기반 조건부 검색 (qa-adaptive-search)

**작성일**: 2026-05-05  
**상태**: Planning  
**단계**: Plan

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **문제** | 현재 QA 패널은 질문 내용과 무관하게 매번 Neo4j 벡터 검색을 수행함. 단순 인사·확인 질문에도 임베딩 생성 + DB 쿼리 비용이 발생 |
| **해결** | LLM이 질문 유형을 먼저 분류(법령 검색 필요 / 불필요)한 뒤, 필요한 경우에만 벡터 검색을 수행하는 조건부 RAG 파이프라인 적용 |
| **기능 UX 효과** | 단순 질문 응답 속도 개선 (DB 생략 경로) / 법령 관련 질문은 기존과 동일하게 근거 데이터 포함 답변 |
| **핵심 가치** | LLM 라우팅으로 불필요한 DB I/O 제거, 응답 지연 최소화 |

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | 벡터 임베딩 생성 + Neo4j 쿼리는 왕복 ~300–500ms 추가 지연. 일반 대화 질문에는 불필요한 비용 |
| **WHO** | QA 패널 사용자 — 법령 질의와 일반 대화 질문을 혼용하는 지자체 담당자 |
| **RISK** | 라우터 LLM 오분류 시 법령 질문에 DB 검색이 생략되어 근거 없는 답변 반환 가능 |
| **SUCCESS** | 법령 관련 질문에는 sources 반환 / 일반 질문에는 sources 없이 빠른 답변 / 오분류율 < 5% |
| **SCOPE** | 백엔드 전용 변경. `app/services/qa_service.py`, `app/prompts/qa_agent.py`. 프론트엔드 변경 없음 |

---

## 1. 배경 및 목표

### 현재 흐름 (`direct_search_qa`)

```
질문 입력
  → get_embedder().embed_query(question)   # 항상 실행
  → db.vector_search_provisions(embedding)  # 항상 실행
  → db.find_legal_terms(keywords)           # 항상 실행
  → build_qa_human_direct(...)
  → LLM 답변 생성
```

**문제**: "감사합니다", "이게 뭐예요?", "좀 더 쉽게 설명해줘" 같은 질문에도
임베딩 API 호출 + Neo4j 쿼리 2회가 실행됨.

### 목표 흐름 (Adaptive RAG)

```
질문 입력
  → [Router LLM] 질문 유형 분류
       ├─ "법령 검색 필요" → 기존 벡터 검색 경로 실행
       └─ "검색 불필요"   → DB 생략, LLM 직접 답변
```

---

## 2. 요구사항

### 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-01 | 질문이 법령·조례 관련인지를 LLM이 판단하는 라우팅 단계 추가 | P0 |
| FR-02 | "검색 필요" 판정 시 기존 벡터 검색 경로 그대로 실행 | P0 |
| FR-03 | "검색 불필요" 판정 시 DB 검색 생략, LLM 단독 답변 반환 | P0 |
| FR-04 | 라우팅 결과를 응답에 포함해 프론트가 참조 가능하도록 노출 (선택적) | P2 |

### 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NFR-01 | 라우터 LLM 호출은 경량 모델(Gemini Flash 또는 동일 모델 소형 프롬프트) 사용 |
| NFR-02 | 라우터 오류 시 기존 벡터 검색 경로로 fallback (안전 우선) |
| NFR-03 | 프론트엔드 API 인터페이스(`QAResponse`) 변경 없음 |

### 검색 불필요 질문 유형 (예시)

- 인사·감사: "안녕하세요", "감사합니다", "수고하세요"
- 이전 답변 참조: "더 자세히 설명해줘", "예시를 들어줘", "요약해줘"
- 앱 기능 질문: "이 패널에서 뭘 할 수 있어요?"
- 순수 논리·계산: "이 두 조항 중 어떤 게 더 엄격해?"

### 검색 필요 질문 유형 (예시)

- 특정 법령 조회: "청년기본법 제3조가 뭐야?", "지방자치법 조례 위임 범위"
- 조례 작성 기준: "지원금 상한선을 어떻게 설정해야 해?"
- 충돌·합법성: "이 조항이 상위법과 충돌하나요?"
- 유사 사례: "다른 지자체 청년 창업 지원 조례 사례"

---

## 3. 기술 설계

### 라우팅 방식: LLM 단일 호출 (구조화 출력)

```python
class SearchDecision(BaseModel):
    needs_search: bool   # True → 벡터 검색 실행
    reason: str          # 판단 근거 (로그용)
```

**라우터 프롬프트 설계 원칙**:
- 법령명·조항번호·조례 작성 기준·유사 사례 요청 → `needs_search: true`
- 이전 답변 관련·일반 대화·앱 사용법 → `needs_search: false`
- 판단 불확실 시 → `needs_search: true` (안전 우선)

### 구현 위치

| 파일 | 변경 내용 |
|------|-----------|
| `app/prompts/qa_agent.py` | `SearchDecision` 모델 + `ROUTER_SYSTEM` 프롬프트 + `build_router_human()` 추가 |
| `app/services/qa_service.py` | `direct_search_qa()` 앞에 라우팅 단계 삽입 |

### 수정 후 `direct_search_qa` 흐름

```python
async def direct_search_qa(question, db, llm):
    # 1. 라우팅
    decision = await _route_question(question, llm)

    # 2-A. 검색 필요
    if decision.needs_search:
        embedding = await embed(question)
        legal_basis, legal_terms, similar_ordinances = await search_db(db, embedding, question)

    # 2-B. 검색 불필요
    else:
        legal_basis = legal_terms = similar_ordinances = []

    # 3. LLM 답변 (기존과 동일)
    result = await generate_answer(question, legal_basis, legal_terms, similar_ordinances, llm)
    return result, legal_basis, legal_terms, similar_ordinances
```

---

## 4. 리스크 및 대응

| 리스크 | 가능성 | 대응 |
|--------|--------|------|
| 라우터가 법령 질문을 "검색 불필요"로 오분류 | 중간 | 판단 불확실 시 `true` 기본값; 프롬프트 few-shot 예시로 보완 |
| 라우터 LLM 호출 실패 | 낮음 | `try/except` → `needs_search=True` fallback으로 기존 경로 유지 |
| 라우팅 추가 latency | 낮음 | 라우터는 소형 프롬프트(~50 token), DB 생략 경로가 더 빠르므로 평균 지연 감소 |

---

## 5. 성공 기준

| 기준 | 측정 방법 |
|------|-----------|
| 법령 질문 → `sources` 1개 이상 반환 | 수동 테스트 5건 |
| 일반 대화 질문 → `sources` 빈 배열 반환 | 수동 테스트 5건 |
| 라우터 오류 시 기존 동작 유지 | 라우터 LLM mock 오류 주입 테스트 |
| 프론트엔드 UI 변경 없음 | 타입 체크 통과 (`npx tsc --noEmit`) |

---

## 6. 구현 범위 (Do 단계)

**수정 파일 2개**:

1. `app/prompts/qa_agent.py`
   - `SearchDecision(BaseModel)` 추가
   - `ROUTER_SYSTEM` 프롬프트 상수 추가
   - `build_router_human(question)` 함수 추가

2. `app/services/qa_service.py`
   - `_route_question(question, llm) -> SearchDecision` 내부 함수 추가
   - `direct_search_qa()` 앞에 라우팅 단계 삽입
   - fallback 처리 (`except` → `needs_search=True`)

**변경 없는 파일**:
- `app/api/routers/chat.py` — 엔드포인트 시그니처 동일
- `app/api/schemas.py` — `QAResponse` 구조 동일
- `frontend/` — 변경 없음

---

## 7. 예상 소요 시간

| 작업 | 예상 시간 |
|------|----------|
| `qa_agent.py` 라우터 프롬프트 작성 | 30분 |
| `qa_service.py` 라우팅 로직 삽입 | 30분 |
| 수동 테스트 (법령 5건 + 일반 5건) | 20분 |
| 배포 | 20분 |
| **합계** | **~1.5시간** |
