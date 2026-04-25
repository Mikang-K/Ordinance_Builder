# Design: 조례 인터뷰 UX 재설계 (interview-ux-redesign)

**작성일**: 2026-04-25  
**상태**: Design  
**단계**: Design  
**선택한 아키텍처**: Option C — 실용적 절충안

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | 현재 인터뷰 UX가 법령 지식이 없는 사용자에게 너무 많은 자유도를 주어 완성률이 낮음 |
| **WHO** | 지자체 담당 공무원, 지방의원 보좌 인력 — 법령 초안 작성 경험 적음 |
| **RISK** | 선택지가 너무 많으면 오히려 인지 부하 증가 / 선택지 범위가 좁으면 자유도 침해 |
| **SUCCESS** | 기본정보 4개 필드를 선택지 클릭만으로도 완성 가능 / 조항 상세 최소 3개 항목에 구조화 입력 제공 |
| **SCOPE** | 프론트엔드 + 백엔드 API 응답 스키마 확장 / LangGraph 워크플로우 구조는 변경 없음 |

---

## 1. Overview

### 1.1 선택 아키텍처: Option C — 실용적 절충안

**핵심 설계 결정**:

1. **백엔드**가 `suggested_options: list[SuggestedOption]`을 `ChatResponse`에 포함
   - `interviewer.py`가 `missing_fields`를 보고 해당 필드의 선택지를 생성
   - 선택지 데이터는 백엔드 상수로 관리 (DB 조회 없음)

2. **프론트엔드** `ChatWindow`가 `suggested_options`를 AI 메시지 하단에 버튼 칩으로 렌더링
   - 칩 클릭 → 기존 `handleSend(value)` 호출 — LangGraph 플로우 변경 없음

3. **ArticleItemsModal** 선택값 → 자연어 텍스트로 변환 → 기존 `string` 타입으로 전송
   - `ArticleBatchRequest` 스키마 변경 없음 (breaking change 없음)

4. `build_drafting_human()` 소폭 업데이트 — 구조화 텍스트 패턴 인식 강화

### 1.2 데이터 흐름

```
[채팅 칩 선택지 흐름]
interviewer_node
  → suggested_options 생성 (field_name 기반)
  → ChatResponse.suggested_options 포함
  → ChatWindow 칩 버튼 렌더링
  → 사용자 클릭
  → handleSend(option.value)  ← 기존 전송 로직 그대로
  → intent_analyzer_node 처리  ← 변경 없음

[조항 모달 구조화 입력 흐름]
ArticleItemsModal
  → 사용자: 선택 칩 클릭 OR 직접 타이핑
  → 선택값 → formatSelectionAsText() → string 변환
  → onSubmit(Record<string, string | null>)  ← 기존 타입 그대로
  → /articles_batch 전송  ← 변경 없음
  → drafting_agent.build_drafting_human()  ← 선택 텍스트 패턴 인식 강화
```

---

## 2. 컴포넌트 설계

### 2.1 백엔드 변경

#### `app/api/schemas.py`

```python
# 신규 모델
class SuggestedOption(BaseModel):
    label: str   # 버튼에 표시되는 텍스트: "보조금 지급"
    value: str   # 클릭 시 전송되는 값: "보조금 지급"

# 기존 ChatResponse에 필드 추가 (optional — 하위 호환)
class ChatResponse(BaseModel):
    ...기존 필드 유지...
    suggested_options: Optional[list[SuggestedOption]] = None  # 신규

# SessionCreateResponse에도 동일 추가 (첫 메시지 응답에도 칩 제공)
class SessionCreateResponse(BaseModel):
    ...기존 필드 유지...
    suggested_options: Optional[list[SuggestedOption]] = None  # 신규
```

#### `app/graph/nodes/interviewer.py`

```python
# 필드별 선택지 상수 (기존 FIELD_QUESTIONS 바로 아래 추가)
FIELD_OPTIONS: dict[str, list[dict]] = {
    "region": [
        {"label": "서울특별시", "value": "서울특별시"},
        {"label": "부산광역시", "value": "부산광역시"},
        {"label": "인천광역시", "value": "인천광역시"},
        {"label": "대구광역시", "value": "대구광역시"},
        {"label": "경기도", "value": "경기도"},
    ],
    "purpose": [
        {"label": "청년 창업 지원", "value": "청년 창업 지원"},
        {"label": "소상공인 지원", "value": "소상공인 지원"},
        {"label": "주거 복지", "value": "주거 복지 지원"},
        {"label": "문화·체육 활동", "value": "문화·체육 활동 지원"},
        {"label": "농업 진흥", "value": "농업 진흥 지원"},
    ],
    "target_group": [
        {"label": "청년 (19~39세)", "value": "만 19세 이상 39세 이하 청년"},
        {"label": "노인 (65세 이상)", "value": "만 65세 이상 노인"},
        {"label": "장애인", "value": "장애인복지법상 등록 장애인"},
        {"label": "소상공인", "value": "소상공인기본법상 소상공인"},
        {"label": "다문화가족", "value": "다문화가족지원법상 다문화가족"},
    ],
    "support_type": [
        {"label": "보조금 지급", "value": "보조금 지급"},
        {"label": "현물 지원", "value": "현물 지원 (물품·서비스)"},
        {"label": "바우처", "value": "바우처 지급"},
        {"label": "교육·컨설팅", "value": "교육 및 컨설팅 지원"},
        {"label": "시설 이용권", "value": "시설 이용 지원"},
    ],
}

# interviewer_node 반환값에 suggested_options 추가
def interviewer_node(state) -> dict:
    ...기존 로직...
    # 첫 번째 누락 필드의 선택지 반환
    first_field = fields_to_ask[0] if fields_to_ask else None
    suggested_options = FIELD_OPTIONS.get(first_field, []) if first_field else []

    return {
        ...기존 반환값...
        "suggested_options": suggested_options,  # 신규
    }
```

> **참고**: LangGraph State에는 `suggested_options`를 추가하지 않음. API 라우터에서 노드 결과를 직접 읽어 응답에 포함. State 오염 방지.

#### `app/api/routers/chat.py` — suggested_options 전달

```python
# chat 엔드포인트의 응답 구성 시
result = await graph.ainvoke(...)
suggested_options = result.get("suggested_options") or []

return ChatResponse(
    ...기존 필드...
    suggested_options=[SuggestedOption(**o) for o in suggested_options] or None,
)
```

#### `app/prompts/drafting_agent.py` — 선택 텍스트 패턴 인식

```python
# build_drafting_human() 내부 article_section 생성 부분
# 기존:
#   lines.append(f"  - [{key}] (사용자 입력): {value}")
# 변경:
#   구조화 선택 텍스트 패턴 인식 (예: "500만원 이내 | 지원기간: 2년 | 비율: 70%")
#   → LLM 프롬프트에 "구조화 선택값 형식" 처리 지침 추가

DRAFTING_SYSTEM 프롬프트에 추가:
"""
사용자 입력이 '값A | 값B | 값C' 형식의 구조화 선택값인 경우:
- 각 값을 해당 조항의 구체적 수치/방법으로 반영할 것
- 예: '500만원 이내 | 지원기간: 2년 | 지원비율: 70%' → 제5조에 구체적 금액 조항 작성
"""
```

---

### 2.2 프론트엔드 변경

#### `frontend/src/types.ts` — 타입 추가

```typescript
// 신규 인터페이스
export interface SuggestedOption {
  label: string
  value: string
}

// 기존 ChatMessage에 suggested_options 추가
export interface ChatMessage {
  role: 'user' | 'ai'
  text: string
  suggested_options?: SuggestedOption[]  // 신규
}

// 기존 ChatResponse에 추가 (optional — 하위 호환)
export interface ChatResponse {
  ...기존 필드...
  suggested_options?: SuggestedOption[]  // 신규
}

// SessionCreateResponse에도 추가
export interface SessionCreateResponse {
  ...기존 필드...
  suggested_options?: SuggestedOption[]  // 신규
}
```

#### `frontend/src/App.tsx` — applyResponse 시 suggested_options 처리

```typescript
// applyResponse() 함수에서 AI 메시지를 messages 배열에 추가할 때
// suggested_options를 ChatMessage에 포함
const aiMsg: ChatMessage = {
  role: 'ai',
  text: res.message,
  suggested_options: res.suggested_options,  // 신규: 칩 데이터 첨부
}
setMessages((prev) => [...prev, aiMsg])
```

#### `frontend/src/components/ChatWindow.tsx` — Props 확장

```typescript
interface Props {
  messages: ChatMessage[]
  isLoading: boolean
  onOptionSelect: (value: string) => void  // 신규: 칩 클릭 콜백
}

// 렌더링: MessageBubble에 suggested_options 전달
{messages.map((msg, i) => (
  <MessageBubble
    key={i}
    message={msg}
    onOptionSelect={onOptionSelect}  // 신규
  />
))}
```

#### `frontend/src/components/MessageBubble.tsx` — 칩 렌더링

```typescript
// AI 메시지 버블 하단에 선택지 칩 렌더링
{message.role === 'ai' && message.suggested_options && message.suggested_options.length > 0 && (
  <div className="suggestion-chips">
    {message.suggested_options.map((opt) => (
      <button
        key={opt.value}
        className="suggestion-chip"
        onClick={() => onOptionSelect?.(opt.value)}
        aria-label={`선택: ${opt.label}`}
      >
        {opt.label}
      </button>
    ))}
  </div>
)}
```

> **설계 결정**: `ChatWindow` 대신 `MessageBubble`에 칩 렌더링을 배치.
> MessageBubble이 이미 메시지 레이아웃을 담당하므로 칩도 버블 내부에 위치하는 것이 자연스러움.

#### CSS 클래스 (App.css 추가)

```css
.suggestion-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.suggestion-chip {
  padding: 6px 14px;
  border: 1.5px solid #0f766e;
  border-radius: 20px;
  background: #f0fdfa;
  color: #0f766e;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
  min-height: 36px;  /* 터치 타겟 */
}

.suggestion-chip:hover {
  background: #0f766e;
  color: white;
}
```

#### `frontend/src/constants/interviewOptions.ts` (신규)

```typescript
// 조항 모달용 구조화 선택지 상수
export const ARTICLE_STRUCTURED_OPTIONS = {
  지원금액: {
    amount: {
      label: '지원 한도',
      type: 'single' as const,
      options: ['100만원', '300만원', '500만원', '1,000만원'],
    },
    period: {
      label: '지원 기간',
      type: 'single' as const,
      options: ['1년', '2년', '3년'],
    },
    ratio: {
      label: '지원 비율',
      type: 'single' as const,
      options: ['50%', '70%', '100%'],
    },
  },
  지원내용: {
    items: {
      label: '지원 항목',
      type: 'multi' as const,
      options: ['창업 초기비용', '임대료', '교육비', '장비 구입비', '마케팅비'],
    },
  },
  신청방법: {
    channels: {
      label: '신청 방법',
      type: 'multi' as const,
      options: ['방문 접수', '온라인 접수', '우편 접수'],
    },
  },
  심사선정: {
    method: {
      label: '심사 방식',
      type: 'single' as const,
      options: ['서류 심사', '발표 심사', '서류+발표 혼합', '선착순'],
    },
  },
} as const

// 선택값을 drafting_agent가 이해할 수 있는 텍스트로 변환
export function formatSelectionAsText(
  articleKey: string,
  selections: Record<string, string | string[]>
): string {
  const parts: string[] = []
  Object.entries(selections).forEach(([field, value]) => {
    if (Array.isArray(value)) {
      if (value.length > 0) parts.push(`${field}: ${value.join(', ')}`)
    } else if (value) {
      parts.push(`${field}: ${value}`)
    }
  })
  return parts.join(' | ')
}
```

#### `frontend/src/components/ArticleItemsModal.tsx` — 구조화 선택 UI 추가

**변경 패턴**:

```typescript
// 구조화 선택 상태
const [structuredSelections, setStructuredSelections] = useState<
  Record<string, Record<string, string | string[]>>
>({})

// 현재 조항의 구조화 옵션 존재 여부 확인
const currentKey = articles[currentIndex]
const structuredOpts = ARTICLE_STRUCTURED_OPTIONS[currentKey as keyof typeof ARTICLE_STRUCTURED_OPTIONS]

// 렌더링: textarea 위에 구조화 UI 표시
{structuredOpts && (
  <div className="structured-input-panel">
    {Object.entries(structuredOpts).map(([field, config]) => (
      <div key={field} className="structured-field">
        <label>{config.label}</label>
        <div className="option-chips">
          {config.options.map((opt) => {
            const sel = structuredSelections[currentKey]?.[field]
            const isSelected = config.type === 'multi'
              ? Array.isArray(sel) && sel.includes(opt)
              : sel === opt
            return (
              <button
                key={opt}
                className={`option-chip ${isSelected ? 'selected' : ''}`}
                onClick={() => handleStructuredSelect(currentKey, field, opt, config.type)}
              >
                {opt}
              </button>
            )
          })}
        </div>
      </div>
    ))}
  </div>
)}
```

**제출 시 텍스트 변환**:

```typescript
// handleSubmit() 수정
const submitData: Record<string, string | null> = {}
articles.forEach((key) => {
  const val = values[key]
  const sels = structuredSelections[key]

  if (val === null) {
    // AI 자동 (기본값) — 변경 없음
    submitData[key] = null
  } else if (sels && Object.keys(sels).length > 0) {
    // 구조화 선택값을 텍스트로 변환 후 자유 텍스트와 합산
    const selText = formatSelectionAsText(key, sels)
    const combined = [selText, val].filter(Boolean).join('\n')
    submitData[key] = combined || null
  } else {
    submitData[key] = (val === '' || val === undefined) ? null : val
  }
})
onSubmit(submitData)
```

---

## 3. API 계약

### 3.1 ChatResponse 변경 (additive only)

```json
// 기존 + 신규 필드
{
  "session_id": "...",
  "message": "어떤 지원 방식을 원하시나요?",
  "stage": "interviewing",
  "is_complete": false,
  "suggested_options": [
    {"label": "보조금 지급", "value": "보조금 지급"},
    {"label": "현물 지원", "value": "현물 지원 (물품·서비스)"},
    {"label": "바우처", "value": "바우처 지급"},
    {"label": "교육·컨설팅", "value": "교육 및 컨설팅 지원"},
    {"label": "시설 이용권", "value": "시설 이용 지원"}
  ]
}
```

> `suggested_options`가 없는 기존 응답도 프론트엔드가 정상 처리 (optional 필드).

### 3.2 ArticleBatchRequest — 변경 없음

```json
// 구조화 선택 후에도 기존 형식 그대로
{
  "articles": {
    "지원금액": "지원 한도: 500만원 | 지원 기간: 2년 | 지원 비율: 70%",
    "지원내용": "지원 항목: 창업 초기비용, 임대료, 교육비",
    "신청방법": "신청 방법: 방문 접수, 온라인 접수",
    "목적": null,
    "정의": null
  }
}
```

---

## 4. 상태 관리

```
App.tsx 상태 변화 없음 (messages, stage, articleQueue 등 기존 유지)

ChatMessage 타입 확장:
  기존: { role, text }
  변경: { role, text, suggested_options? }
  → 메시지 배열에 칩 데이터가 함께 저장됨
  → 세션 복원 시: messages 배열에서 복원 (별도 상태 불필요)

ArticleItemsModal 내부 상태 추가:
  structuredSelections: Record<articleKey, Record<fieldKey, string|string[]>>
  → 모달 마운트 시 초기화, 제출 시 소멸
  → 세션 저장 불필요 (모달 내 일회성 상태)
```

---

## 5. LangGraph 워크플로우 — 변경 없음

```
인터뷰 노드 변경:
  interviewer_node: 반환값에 suggested_options 추가
    → State에는 저장하지 않음
    → chat.py 라우터가 노드 result에서 직접 읽어 ChatResponse에 포함

State (OrdinanceBuilderState):
  변경 없음 — suggested_options는 transient 데이터

워크플로우 엣지/분기:
  변경 없음
```

---

## 6. 파일별 변경 명세

| 파일 | 변경 유형 | 주요 변경 내용 |
|------|-----------|---------------|
| `app/api/schemas.py` | 수정 | `SuggestedOption` 모델 신규, `ChatResponse` + `SessionCreateResponse`에 `suggested_options` 필드 추가 |
| `app/graph/nodes/interviewer.py` | 수정 | `FIELD_OPTIONS` 상수 추가, 반환값에 `suggested_options` 포함 |
| `app/api/routers/chat.py` | 수정 | `ChatResponse` 생성 시 `suggested_options` 전달 (create_session, chat 두 핸들러) |
| `app/prompts/drafting_agent.py` | 수정 | `DRAFTING_SYSTEM`에 구조화 텍스트 패턴 처리 지침 추가 |
| `frontend/src/types.ts` | 수정 | `SuggestedOption` 인터페이스, `ChatMessage` + `ChatResponse` + `SessionCreateResponse` 필드 추가 |
| `frontend/src/App.tsx` | 수정 | `applyResponse()` — AI 메시지 저장 시 `suggested_options` 포함, `onOptionSelect` 핸들러 추가 |
| `frontend/src/components/ChatWindow.tsx` | 수정 | `onOptionSelect` Props 추가, `MessageBubble`에 전달 |
| `frontend/src/components/MessageBubble.tsx` | 수정 | 칩 렌더링 로직 + `suggestion-chips` CSS 클래스 |
| `frontend/src/components/ArticleItemsModal.tsx` | 수정 | `structuredSelections` 상태, 구조화 선택 UI, `handleSubmit` 텍스트 변환 |
| `frontend/src/constants/interviewOptions.ts` | 신규 | `ARTICLE_STRUCTURED_OPTIONS`, `formatSelectionAsText` |
| `frontend/src/App.css` | 수정 | `.suggestion-chips`, `.suggestion-chip`, `.structured-input-panel`, `.option-chip` |

---

## 7. 비기능 설계

### 7.1 하위 호환성

- `suggested_options` 필드 없이 응답해도 프론트엔드 정상 동작 (`?.` 옵셔널 체이닝)
- `ArticleBatchRequest` 스키마 변경 없음 — 기존 세션 데이터 영향 없음
- 세션 복원(`GET /session/{id}`) 응답에 `suggested_options` 포함 불필요 (메시지 배열에서 복원 가능)

### 7.2 UX 규칙

- 칩은 최대 5개, 이후 "직접 입력"으로 유도
- 칩 클릭 시 선택된 칩은 시각적으로 표시 후 disabled (중복 클릭 방지)
- 단, 이전 메시지의 칩은 현재 세션에서는 재클릭 불가 (이미 전송 완료)
- 구조화 선택 UI는 텍스트에어리어와 **동시에 표시** (택일이 아님)
- "기본값(AI 자동)" 버튼은 구조화 선택값도 모두 지움 (null 처리)

### 7.3 접근성

- 칩 버튼: `aria-label={선택: ${label}}`, `role="button"`, 키보드 `Enter`/`Space` 동작
- 구조화 선택 패널: `role="group"`, `aria-labelledby` 연결

---

## 8. 테스트 시나리오

| 번호 | 시나리오 | 예상 결과 |
|------|---------|----------|
| T-01 | support_type 질문 도달 후 "보조금 지급" 칩 클릭 | intent_analyzer가 support_type="보조금 지급" 추출 후 다음 질문으로 진행 |
| T-02 | 칩 클릭 후 직접 타이핑으로 다른 값 입력 | 마지막으로 전송된 값이 처리됨 (칩/타이핑 모두 동등) |
| T-03 | 지원금액 조항에서 500만원+2년+70% 선택 후 제출 | articles["지원금액"] = "지원 한도: 500만원 | 지원 기간: 2년 | 지원 비율: 70%" 전송 |
| T-04 | 지원내용에서 3개 항목 다중 선택 후 제출 | 선택 항목들이 쉼표 구분 텍스트로 전송 |
| T-05 | 구조화 선택 + 추가 텍스트 입력 후 제출 | 선택 텍스트와 자유 입력이 개행으로 합산 전송 |
| T-06 | "기본값(AI 자동)" 클릭 | 구조화 선택값 포함 null 처리 |
| T-07 | 세션 복원 후 채팅 이어가기 | 이전 메시지의 칩은 표시되지 않음 (복원된 messages는 suggested_options 없음) |
| T-08 | `suggested_options` 없는 응답 처리 | 칩 영역 미표시, 기존 동작 그대로 |

---

## 9. 제외 항목 (명시적)

- `OrdinanceBuilderState` 변경 없음
- `GET /session/{id}` 복원 응답 변경 없음 (`suggested_options` 비포함)
- 채팅 입력창 이외 별도 마법사 화면 없음
- region 자동완성/검색 기능 없음 (Phase 2)

---

## 10. 구현 세션 가이드

### Module Map

| 모듈 | 파일 수 | 예상 작업량 |
|------|---------|------------|
| M1: 백엔드 스키마 + 인터뷰어 | 3파일 | ~30분 |
| M2: 채팅 칩 UI (프론트엔드) | 4파일 + CSS | ~45분 |
| M3: 조항 모달 구조화 UI | 2파일 | ~60분 |
| M4: drafting_agent 프롬프트 | 1파일 | ~15분 |

### 권장 세션 분할

```
Session 1: M1 + M2 (백엔드 + 채팅 칩)
  → /pdca do interview-ux-redesign --scope M1,M2
  → 검증: 채팅에서 선택지 칩이 정상 렌더링되는지 확인

Session 2: M3 + M4 (조항 모달 + 프롬프트)
  → /pdca do interview-ux-redesign --scope M3,M4
  → 검증: 구조화 선택 후 초안에 선택값 반영 확인
```
