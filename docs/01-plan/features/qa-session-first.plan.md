# Plan: QA 세션 법령 우선 — 체크포인트 legal_basis 우선 활용 (qa-session-first)

**작성일**: 2026-05-09  
**상태**: Planning  
**단계**: Plan

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **문제** | QAPanel이 세션 유무와 관계없이 항상 직접 벡터 검색을 사용 → 세션과 무관한 조례 추천. 세션 생성 시 `graph_retriever`가 이미 수집한 `legal_basis`(체크포인트 캐시)가 있는데 QA에서 전혀 활용하지 않음 |
| **해결** | 세션이 있을 때는 세션 기반 QA(`/session/{id}/qa`)를 사용. 세션 QA는 체크포인트 `legal_basis`를 1순위로 사용하고, 캐시가 없을 때만 fresh 키워드 검색. 직접 검색은 세션 없는 경우의 fallback |
| **기능 UX 효과** | 세션에서 QA 질문 시 해당 조례와 직접 관련된 법령 근거로 답변. 무관한 조례 노출 제거. `applicable_content`도 더 정확하게 생성 |
| **핵심 가치** | 이미 수집된 세션 법령 데이터를 재활용 → DB 재검색 비용 절감 + 답변 관련성 향상 |

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | `qa_chat` 핸들러가 `values.get("legal_basis")`를 무시하고 매번 `find_legal_basis()` 재호출. QAPanel은 세션이 있어도 `searchDirectQuestion()` 고정 사용 |
| **WHO** | 세션에서 조례 작성 중 법령 질의응답하는 지자체 담당자 |
| **RISK** | 체크포인트 `legal_basis`가 오래되거나 비어 있으면 fresh 검색으로 fallback → 기존 동작 유지. 세션 없을 때 회귀 없음 |
| **SUCCESS** | 세션 QA에서 해당 조례 관련 법령만 sources에 표시 / `applicable_content` 정확도 향상 / 세션 없을 때 기존 직접 검색 동작 유지 |
| **SCOPE** | 백엔드 1파일 (`chat.py` `qa_chat` 핸들러) + 프론트엔드 1파일 (`QAPanel.tsx`) |

---

## 1. 배경 및 목표

### 현재 흐름 (문제)

```
[세션 생성 시]
  graph_retriever → legal_basis, similar_ordinances 수집 → 체크포인트에 저장
                    (해당 조례에 최적화된 법령 데이터)

[QA 질문 시]
  QAPanel → searchDirectQuestion(q)          # 세션 무시
               → 질문 임베딩 벡터 검색       # 무관한 조례 반환 가능
               → applicable_content 생성에 세션 컨텍스트 없음
```

```
[qa_chat 엔드포인트 - 현재 미사용]
  체크포인트 읽기 → values.get("legal_basis") 무시
               → find_legal_basis(keywords) 재호출  # 체크포인트 캐시 활용 안 함
```

### 목표 흐름 (수정 후)

```
[QA 질문 시]
  QAPanel
    ├─ sessionId 있음 → askQuestion(sessionId, q)
    │      → qa_chat 핸들러
    │           → 체크포인트 legal_basis (캐시) 우선 사용
    │           │   캐시 비어 있으면 → fresh 키워드 검색
    │           → 세션 컨텍스트(ordinance_info, current_article_key)로 답변
    │           → applicable_content 생성
    │
    └─ sessionId 없음 → searchDirectQuestion(q)  (기존 동작)
```

---

## 2. 요구사항

### 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-01 | QAPanel: `sessionId` 있을 때 `askQuestion(sessionId, q)` 사용 | P0 |
| FR-02 | QAPanel: `sessionId` 없을 때 `searchDirectQuestion(q)` fallback | P0 |
| FR-03 | `qa_chat`: 체크포인트 `legal_basis`가 있으면 재검색 없이 캐시 사용 | P0 |
| FR-04 | `qa_chat`: 체크포인트 `legal_basis` 비어 있으면 fresh 키워드 검색 fallback | P0 |
| FR-05 | `applicable_content` 생성: 세션 `current_article_key` + `ordinance_info` 활용 | P1 |

### 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NFR-01 | 세션 없을 때 기존 직접 검색 동작 동일 |
| NFR-02 | `askQuestion` 실패 시 `searchDirectQuestion`으로 silent fallback |
| NFR-03 | TypeScript 컴파일 오류 없음 |

---

## 3. 기술 설계

### 3-1. `frontend/src/components/QAPanel.tsx` — API 호출 분기

```typescript
// 현재 (qa-session-apply 이후)
const res = await searchDirectQuestion(q, { current_article_key: currentArticleKey })

// 수정 후
let res: QAResponse
if (sessionId) {
    try {
        res = await askQuestion(sessionId, q)
    } catch {
        // 세션 기반 실패 시 silent fallback
        res = await searchDirectQuestion(q, { current_article_key: currentArticleKey })
    }
} else {
    res = await searchDirectQuestion(q, { current_article_key: currentArticleKey })
}
```

`askQuestion`은 `api.ts`에 이미 구현됨 → import 추가만 필요.

### 3-2. `app/api/routers/chat.py` — `qa_chat` 핸들러 법령 검색 로직

```python
# 현재 (항상 fresh 검색)
if db:
    legal_basis, legal_terms = await asyncio.gather(
        asyncio.to_thread(db.find_legal_basis, keywords, support_type),
        asyncio.to_thread(db.find_legal_terms, keywords),
    )

# 수정 후 (체크포인트 캐시 우선)
cached_legal_basis = values.get("legal_basis") or []

if cached_legal_basis:
    # 1순위: 세션 생성 시 graph_retriever가 수집한 법령 (해당 조례에 최적화)
    legal_basis = cached_legal_basis
    if db:
        try:
            legal_terms = await asyncio.to_thread(db.find_legal_terms, keywords)
        except Exception:
            logger.warning("법률 용어 검색 실패 — 용어 없이 계속")
else:
    # 2순위: 캐시 없으면 fresh 키워드 검색 (기존 동작)
    if db:
        try:
            legal_basis, legal_terms = await asyncio.gather(
                asyncio.to_thread(db.find_legal_basis, keywords, support_type),
                asyncio.to_thread(db.find_legal_terms, keywords),
            )
        except Exception:
            logger.warning("GraphRAG DB 검색 실패 — LLM 단독 답변으로 계속")
```

### 법령 캐시 데이터 구조 확인

`graph_retriever`가 저장하는 `legal_basis` 항목 구조:
```python
{
    "statute_title": "청년기본법",
    "provision_article": "제3조",
    "provision_content": "...",
    "relation_type": "DELEGATES"  # DELEGATES | BASED_ON | KEYWORD
}
```
`build_qa_human`은 이 구조를 그대로 사용 → 형식 호환 확인됨.

---

## 4. 변경 파일 요약

| 파일 | 변경 내용 | 규모 |
|------|-----------|------|
| `frontend/src/components/QAPanel.tsx` | `askQuestion` import 추가 + `handleSend` 분기 (~15줄) | +12줄 |
| `app/api/routers/chat.py` | `qa_chat`의 법령 검색 로직을 캐시 우선으로 교체 | +10줄 |

**총 변경 규모**: ~22줄

---

## 5. 검색 소스 우선순위 정리

| 우선순위 | 소스 | 사용 조건 | 관련성 |
|---------|------|-----------|--------|
| 1 | 체크포인트 `legal_basis` (캐시) | 세션 있음 + 캐시 비지 않음 | 최고 (조례에 최적화) |
| 2 | fresh 키워드 그래프 검색 | 세션 있음 + 캐시 비어 있음 | 중간 (ordinance_info 기반) |
| 3 | 직접 벡터 검색 | 세션 없음 | 낮음 (질문 의미 기반) |

---

## 6. 리스크 및 대응

| 리스크 | 가능성 | 대응 |
|--------|--------|------|
| 체크포인트 캐시가 오래되어 질문과 관련 없는 법령만 있는 경우 | 낮음 | 캐시 법령 + `legal_terms` fresh 검색으로 답변 품질 보완 |
| `askQuestion` 호출 실패 | 낮음 | silent fallback → `searchDirectQuestion` 자동 재시도 |
| `applicable_content` 회귀 (qa-session-apply와 충돌) | 없음 | `askQuestion` 사용 시 세션 기반 QA가 `applicable_content` 그대로 생성 |

---

## 7. 성공 기준

| 기준 | 측정 방법 |
|------|-----------|
| 세션 있을 때 QA sources가 해당 조례 관련 법령만 표시 | 수동 테스트 (조례 주제와 무관한 조례 미표시 확인) |
| 세션 없을 때 기존 직접 검색 동작 유지 | 수동 테스트 |
| `applicable_content` 정상 생성 (article_interviewing 단계) | 수동 테스트 |
| TypeScript 컴파일 오류 없음 | `npx tsc --noEmit` |

---

## 8. 예상 소요 시간

| 작업 | 예상 시간 |
|------|----------|
| QAPanel.tsx 수정 | 10분 |
| chat.py qa_chat 수정 | 10분 |
| 타입 체크 + 수동 테스트 | 15분 |
| 배포 | 20분 |
| **합계** | **~55분** |
