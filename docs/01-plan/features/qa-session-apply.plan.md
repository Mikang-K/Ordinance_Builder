# Plan: QA 직접 검색 조항 컨텍스트 주입 — 현재 조항에 적용하기 활성화 (qa-session-apply)

**작성일**: 2026-05-09  
**수정일**: 2026-05-09 (세션 기반 전환 → 직접 검색 컨텍스트 주입 방식으로 변경)  
**상태**: Planning  
**단계**: Plan

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **문제** | `build_qa_human_direct`가 `applicable_content` null 고정 지시 + `current_article_key`를 받지 않아 조항 컨텍스트 없이 LLM 호출 → "현재 조항에 적용하기" 버튼 영원히 미표시 |
| **해결** | 직접 검색 엔드포인트(`/api/v1/qa`)를 유지하되, 프론트엔드가 `current_article_key`·`ordinance_info`를 요청 body에 포함. LLM이 조항 컨텍스트를 알고 `applicable_content` 생성 |
| **기능 UX 효과** | 조항 작성 중 QA 질문 시 "현재 조항에 적용하기" 버튼 표시. 벡터 검색 품질(직접 검색) 그대로 유지. 세션 없을 때도 동일 엔드포인트 사용 |
| **핵심 가치** | 검색 방식 변경 없이 컨텍스트 전달만 추가. 세션 기반 전환·fallback 로직 불필요 |

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | `build_qa_human_direct` 말미에 "applicable_content와 applicable_article_key는 null로 두세요" 지시가 있고, `current_article_key` 파라미터 자체가 없음. 프론트에서 아무리 보내도 프롬프트에 반영이 안 됨 |
| **WHO** | `article_interviewing` 단계에서 조항을 작성 중인 지자체 담당자 |
| **RISK** | 직접 검색은 `article_examples` 캐시(그래프 checkpoint)를 활용하지 못함. 세션 기반 대비 조항별 유사 사례 없이 applicable_content 생성 |
| **SUCCESS** | 조항 작성 중 QA 질문 시 applicable_content 포함 응답 / "현재 조항에 적용하기" 버튼 표시·동작 / 세션 없을 때 기존 동작 유지 / 벡터 검색 방식 유지 |
| **SCOPE** | 백엔드 3파일 + 프론트엔드 2파일 수정 |

---

## 1. 배경 및 목표

### 현재 흐름 (문제)

```
QAPanel.handleSend()
  → searchDirectQuestion(q)              # currentArticleKey 미전달
       → POST /api/v1/qa  { question }   # current_article_key 없음
       → build_qa_human_direct(q, ...)
            "applicable_content와 applicable_article_key는 null로 두세요." ← 고정 지시
       → applicable_content = null
  → QAMessageBubble
       → canApply = false → 버튼 미표시
```

### 목표 흐름 (수정 후)

```
QAPanel.handleSend()
  → searchDirectQuestion(q, { current_article_key, ordinance_info })
       → POST /api/v1/qa {
             question,
             current_article_key: "목적",       # QAPanel prop에서 주입
             ordinance_info: { region, purpose, ... }  # App.tsx 상태에서 주입
         }
       → build_qa_human_direct(q, ..., current_article_key, ordinance_info)
            "[현재 작성 중인 조항: 목적]"
            "관련 질문이면 applicable_content를 조례 텍스트로 생성"
       → applicable_content = "제1조(목적) 이 조례는 ..."
  → QAMessageBubble
       → canApply = true → 버튼 표시
```

---

## 2. 요구사항

### 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-01 | `QADirectRequest`에 `current_article_key`, `ordinance_info` optional 필드 추가 | P0 |
| FR-02 | `build_qa_human_direct`가 두 필드를 받아 프롬프트에 포함, applicable_content 생성 지시 | P0 |
| FR-03 | `qa_direct` 핸들러가 요청 필드를 `build_qa_human_direct`에 전달 | P0 |
| FR-04 | `searchDirectQuestion(q, context?)` — 프론트엔드 API 함수 시그니처 확장 | P0 |
| FR-05 | QAPanel이 `currentArticleKey`, `ordinanceInfo` prop을 받아 요청에 포함 | P0 |

### 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NFR-01 | `current_article_key` 없을 때 기존 동작 동일 (`applicable_content=null`) |
| NFR-02 | TypeScript 컴파일 오류 없음 (`npx tsc --noEmit`) |
| NFR-03 | 벡터 검색 방식 유지 — 직접 검색 엔드포인트 그대로 사용 |

---

## 3. 기술 설계

### 3-1. `app/api/schemas.py` — `QADirectRequest` 확장

```python
# 현재
class QADirectRequest(BaseModel):
    question: str

# 수정 후
class QADirectRequest(BaseModel):
    question: str
    current_article_key: Optional[str] = None
    ordinance_info: Optional[dict] = None
```

### 3-2. `app/prompts/qa_agent.py` — `build_qa_human_direct` 확장

```python
# 현재 시그니처
def build_qa_human_direct(
    question: str,
    legal_basis: list[dict],
    legal_terms: list[dict],
    similar_ordinances: list[dict] | None = None,
) -> str:
    ...
    # 말미
    lines.append("\napplicable_content와 applicable_article_key는 null로 두세요.")

# 수정 후 시그니처
def build_qa_human_direct(
    question: str,
    legal_basis: list[dict],
    legal_terms: list[dict],
    similar_ordinances: list[dict] | None = None,
    current_article_key: Optional[str] = None,
    ordinance_info: Optional[dict] = None,
) -> str:
    ...
    # ordinance_info 섹션 추가 (current_article_key 있을 때)
    if current_article_key and ordinance_info:
        lines.append("\n[현재 작성 중인 조례 정보]")
        lines.append(f"- 지역: {ordinance_info.get('region', '미정')}")
        lines.append(f"- 목적: {ordinance_info.get('purpose', '미정')}")
        lines.append(f"- 지원 대상: {ordinance_info.get('target_group', '미정')}")
        lines.append(f"- 지원 유형: {ordinance_info.get('support_type', '미정')}")

    if current_article_key:
        lines.append(f"\n[현재 작성 중인 조항: {current_article_key}]")

    lines.append(f"\n[질문]\n{question}")

    # 말미 지시 분기
    if current_article_key:
        lines.append(
            f"\napplicable_content는 질문이 '{current_article_key}' 조항 작성과 직접 관련될 때만 "
            "해당 조항에 삽입 가능한 조례 텍스트를 생성하세요. 무관하면 null로 두세요. "
            f"applicable_article_key는 '{current_article_key}'로 설정하세요."
        )
    else:
        lines.append("\napplicable_content와 applicable_article_key는 null로 두세요.")
```

### 3-3. `app/api/routers/chat.py` — `qa_direct` 핸들러 수정

```python
# 현재
human_text = build_qa_human_direct(
    question=body.question,
    legal_basis=legal_basis,
    legal_terms=legal_terms,
    similar_ordinances=similar_ordinances if similar_ordinances else None,
)

# 수정 후
human_text = build_qa_human_direct(
    question=body.question,
    legal_basis=legal_basis,
    legal_terms=legal_terms,
    similar_ordinances=similar_ordinances if similar_ordinances else None,
    current_article_key=body.current_article_key,
    ordinance_info=body.ordinance_info,
)
```

### 3-4. `frontend/src/api.ts` — `searchDirectQuestion` 시그니처 확장

```typescript
// 현재
export async function searchDirectQuestion(question: string): Promise<QAResponse> {
  const res = await fetch('/api/v1/qa', {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify({ question }),
  })
  ...
}

// 수정 후
interface QADirectContext {
  current_article_key?: string | null
  ordinance_info?: Record<string, string> | null
}

export async function searchDirectQuestion(
  question: string,
  context?: QADirectContext,
): Promise<QAResponse> {
  const res = await fetch('/api/v1/qa', {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify({ question, ...context }),
  })
  ...
}
```

### 3-5. `frontend/src/components/QAPanel.tsx` — prop 추가 + 호출 수정

```typescript
// Props 추가
interface Props {
  sessionId: string | null
  stage: Stage | null
  currentArticleKey: string | null
  qaHistory: QAMessage[]
  onAddMessages: (messages: QAMessage[]) => void
  onApplyContent: (content: string) => void
  fontSize: number
  ordinanceInfo?: Record<string, string> | null   // ← 추가
}

// handleSend 수정
const res = await searchDirectQuestion(q, {
  current_article_key: currentArticleKey,
  ordinance_info: ordinanceInfo,
})
```

`App.tsx`에서 `<QAPanel ordinanceInfo={ordinanceInfo} .../>` 전달 필요.

---

## 4. 변경 파일 요약

| 파일 | 변경 내용 | 규모 |
|------|-----------|------|
| `app/api/schemas.py` | `QADirectRequest` 필드 2개 추가 | +3줄 |
| `app/prompts/qa_agent.py` | `build_qa_human_direct` 파라미터·프롬프트 분기 추가 | +20줄 |
| `app/api/routers/chat.py` | `qa_direct` 핸들러 `build_qa_human_direct` 호출부 수정 | +2줄 |
| `frontend/src/api.ts` | `searchDirectQuestion` 시그니처 + `QADirectContext` 타입 추가 | +10줄 |
| `frontend/src/components/QAPanel.tsx` | `ordinanceInfo` prop + `searchDirectQuestion` 호출 수정 | +5줄 |
| `frontend/src/App.tsx` | `<QAPanel ordinanceInfo={ordinanceInfo} />` prop 추가 | +1줄 |

**총 변경 규모**: ~41줄

---

## 5. 리스크 및 대응

| 리스크 | 가능성 | 대응 |
|--------|--------|------|
| `article_examples` 캐시 없어 applicable_content 품질이 세션 기반보다 낮을 수 있음 | 중간 | 벡터 검색으로 찾은 유사 조문으로 보완. 향후 직접 검색에도 `article_examples` 추가 가능 |
| `ordinance_info` prop 미전달 시 조례 컨텍스트 없이 생성 | 낮음 | `current_article_key`만 있어도 조항명 기준으로 생성 가능 |
| `applicable_content` 생성 여부가 LLM 판단에 의존 | 낮음 | 프롬프트 지시가 명확하여 관련 질문에는 안정적으로 생성됨 |

---

## 6. 성공 기준

| 기준 | 측정 방법 |
|------|-----------|
| `article_interviewing` 단계 + 조항 관련 질문 → "현재 조항에 적용하기" 버튼 표시 | 수동 테스트 |
| 버튼 클릭 → ArticleItemsModal 해당 조항 textarea pre-fill | 수동 테스트 |
| `current_article_key` 없을 때 기존 동작 동일 (applicable_content null) | 수동 테스트 |
| TypeScript 컴파일 오류 없음 | `npx tsc --noEmit` |

---

## 7. 예상 소요 시간

| 작업 | 예상 시간 |
|------|----------|
| 백엔드 3파일 수정 | 20분 |
| 프론트엔드 3파일 수정 | 15분 |
| 수동 테스트 | 15분 |
| 배포 | 20분 |
| **합계** | **~70분** |
