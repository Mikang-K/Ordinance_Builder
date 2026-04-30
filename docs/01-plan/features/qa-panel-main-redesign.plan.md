# Plan: QA 패널 메인화 — 채팅 UI 제거 (qa-panel-main-redesign)

**작성일**: 2026-04-30  
**상태**: Planning  
**단계**: Plan

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **문제** | 기본정보·조항 상세가 모달로 수집되면서 메인 채팅 화면은 AI 응답 메시지를 출력하는 역할만 남아 실질적으로 활용도가 없음 |
| **해결** | 채팅 UI(ChatWindow + 입력창)를 제거하고 QA 패널을 메인 컨텐츠 영역으로 승격. 새 조례 생성은 헤더 버튼 → OnboardingWizard 모달로 진입 |
| **기능 UX 효과** | 화면 공간 낭비 제거 / 법령 Q&A를 첫 화면부터 노출 / 조례 생성 중에도 상시 질의응답 가능 |
| **핵심 가치** | "법령 검색 + 조례 생성" 두 기능을 단일 화면에서 끊김 없이 제공 |

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | 채팅창은 OnboardingWizard·ArticleItemsModal로 대체되어 빈 공간이 되었음. QA 기능이 더 높은 상시 활용가치를 가짐 |
| **WHO** | 지자체 담당자 — 조례 생성 중 관련 법령을 수시로 조회해야 하는 사용자 |
| **RISK** | QA 패널 구조 변경 시 기존 `pendingQAContent` → ArticleItemsModal pre-fill 흐름이 깨질 수 있음 |
| **SUCCESS** | 채팅 관련 state/컴포넌트 완전 제거 / QA 패널이 메인 영역에서 정상 동작 / 기존 모달(조항·초안·법률검증) 모두 그대로 작동 |
| **SCOPE** | 프론트엔드 전용 변경. 백엔드 API·LangGraph 워크플로우 변경 없음 |

---

## 1. 배경 및 목표

### 현재 문제

**"chat" 뷰의 실제 사용 흐름**:

```
view='chat' 진입
  → messages.length === 0 → OnboardingWizard 표시 (기본정보 수집)
  → OnboardingWizard 완료 → sendText() → createSession()
  → ChatWindow에 AI 응답 표시 (잠깐)
  → article_interviewing 단계 → ArticleItemsModal 자동 오픈
  → 조항 완료 → DraftModal 자동 오픈
  → 확정 → CompletedDraftModal
```

채팅창은 세션 생성 직후 AI 응답 몇 줄을 보여주는 역할만 하며, 실질적인 상호작용은 모두 모달에서 이루어짐.

**QA 패널의 현재 위치**:
- 헤더의 "🔍 질문" 버튼을 클릭해야만 진입 가능한 슬라이딩 오버레이
- z-index 150, backdrop 포함 → 메인 화면을 가리는 부가 기능 취급
- 조례 생성 진행 중에도 상시 유용하지만 진입 장벽이 높음

### 목표

1. 채팅 UI(ChatWindow, 입력창, SimilarOrdinancesPanel) **완전 제거**
2. QA 패널을 **메인 컨텐츠 영역**으로 승격 (항상 표시, 오버레이 아님)
3. 새 조례 생성 진입: 헤더 "새 조례 만들기" 버튼 → OnboardingWizard 모달
4. 세션 목록 화면(view='list') **현재 방식 유지**
5. 기존 모달(ArticleItemsModal, DraftModal, CompletedDraftModal) **변경 없음**

---

## 2. 범위 (Scope)

### 포함

| 구성요소 | 변경 내용 |
|----------|-----------|
| `App.tsx` | 채팅 state·핸들러 제거, QAPanel 메인 배치, OnboardingWizard 모달화, 헤더 버튼 추가 |
| `QAPanel.tsx` | 오버레이 → 메인 컨텐츠 영역으로 전환 (절대 위치 → 정적 배치, backdrop 제거) |
| `OnboardingWizard.tsx` | `isOpen`/`onClose` props 추가하여 모달로 사용 가능하도록 수정 |
| `App.css` | `.chat-area` → `.qa-main-area` 스타일 조정 |

### 제외 (변경 없음)

| 구성요소 | 이유 |
|----------|------|
| `SessionListScreen.tsx` | 현재 방식 유지 (view='list' / 'chat' 토글) |
| `ArticleItemsModal.tsx` | 조항 입력 흐름 변경 없음 |
| `DraftModal.tsx` | 초안 편집·법률검증 흐름 변경 없음 |
| `CompletedDraftModal.tsx` | 확정 초안 표시 변경 없음 |
| `StageIndicator.tsx` | 헤더에 유지 |
| `LoadingModal.tsx` | 변경 없음 |
| 백엔드 API | QA 엔드포인트 포함 전체 변경 없음 |

### 삭제 대상 (미사용 컴포넌트)

| 파일 | 이유 |
|------|------|
| `ChatWindow.tsx` | 채팅 메시지 표시 컴포넌트 — 제거 후 미사용 |
| `MessageBubble.tsx` | ChatWindow 하위 컴포넌트 — 함께 제거 |
| `SimilarOrdinancesPanel.tsx` | 채팅창 하단 유사 조례 패널 — QA 패널로 통합되므로 불필요 |

---

## 3. 상세 요구사항

### 3.1 App.tsx 상태 정리

**제거할 state**:

```typescript
// 채팅 관련 — 완전 제거
const [messages, setMessages] = useState<ChatMessage[]>([])
const [input, setInput] = useState('')
```

**제거할 핸들러**:

```typescript
// 채팅 관련 — 완전 제거
const appendMessage = ...
const sendText = ...
const handleSend = ...
const handleKeyDown = ...
const handleOptionSelect = ...
```

**추가할 state**:

```typescript
// OnboardingWizard 모달 제어
const [isOnboardingOpen, setIsOnboardingOpen] = useState(false)
```

**변경할 핸들러**:

```typescript
// sendText에서 createSession 직접 호출로 교체
const handleWizardStart = async (message: string) => {
  setIsOnboardingOpen(false)
  setIsLoading(true)
  setLoadingMessage('기본 정보를 분석하고 있습니다...')
  try {
    const res = await createSession(message)
    sessionIdRef.current = res.session_id
    setHasSession(true)
    applyResponse({ ...res, is_complete: false })
  } catch (e) {
    setError(e instanceof Error ? e.message : '알 수 없는 오류가 발생했습니다.')
  } finally {
    setIsLoading(false)
    setLoadingMessage(null)
  }
}
```

### 3.2 레이아웃 변경

**현재 "chat" 뷰 구조**:
```
<main class="app-main">
  <div class="chat-area">
    OnboardingWizard (조건부) or ChatWindow
    SimilarOrdinancesPanel (조건부)
    error bar
    input-area (textarea + 전송 버튼)
  </div>
</main>
```

**새 "chat" 뷰 구조**:
```
<main class="app-main">
  <div class="qa-main-area">
    QAPanel (항상 표시, 메인 영역)
    error bar (조건부)
  </div>
</main>

<!-- 모달 오버레이들 -->
OnboardingWizard (isOnboardingOpen 시 모달)
ArticleItemsModal (기존 유지)
DraftModal (기존 유지)
CompletedDraftModal (기존 유지)
LoadingModal (기존 유지)
```

### 3.3 헤더 버튼

```
[StageIndicator]  [새 조례 만들기 ✚]  [목록]  [로그아웃]
```

- "새 조례 만들기" 버튼: `setIsOnboardingOpen(true)` 호출
- 세션 진행 중(`hasSession === true`)일 때도 클릭 가능 (새 세션 생성 허용)
  - 단, 확인 다이얼로그 표시: "현재 진행 중인 조례 작업이 있습니다. 새로 시작하시겠습니까?"

### 3.4 QAPanel 구조 변경

**현재**: `position: fixed` 오버레이, `isOpen` prop으로 슬라이드 인/아웃

**변경**:
- `position: fixed` → `position: static` (또는 flex 자식)
- backdrop 오버레이 제거
- `isOpen`/`onClose` props 제거 (항상 렌더링)
- 세션 없을 때: "새 조례 만들기 버튼을 눌러 조례 생성을 시작하세요" 빈 상태 메시지

**QAPanel props 변경**:
```typescript
// Before
interface QAPanelProps {
  isOpen: boolean
  onClose: () => void
  sessionId: string | null
  // ...
}

// After
interface QAPanelProps {
  sessionId: string | null
  // isOpen, onClose 제거
  // 나머지 props 유지
}
```

### 3.5 OnboardingWizard 모달화

**현재**: App.tsx 메인 영역에 조건부 렌더링 (메시지 없을 때)

**변경**: `isOpen` prop 추가하여 모달 오버레이로 표시

```typescript
// Before
interface Props {
  onStart: (message: string) => void
  isLoading: boolean
}

// After
interface Props {
  isOpen: boolean          // 추가
  onClose: () => void      // 추가
  onStart: (message: string) => void
  isLoading: boolean
}
```

모달 래퍼 스타일: `position: fixed, inset: 0, z-index: 100, backdrop`
내부 컨텐츠: 기존 OnboardingWizard UI 그대로

---

## 4. 구현 순서

| 순서 | 파일 | 작업 |
|------|------|------|
| 1 | `QAPanel.tsx` | 오버레이 → 정적 배치 전환 (`isOpen`/`onClose`/backdrop 제거) |
| 2 | `OnboardingWizard.tsx` | `isOpen`/`onClose` props 추가, 모달 래퍼 추가 |
| 3 | `App.tsx` | 채팅 state·핸들러 제거, `handleWizardStart` 추가, 레이아웃 교체, 헤더 버튼 추가 |
| 4 | `App.css` | `.chat-area` → `.qa-main-area` 스타일 조정 |
| 5 | 삭제 | `ChatWindow.tsx`, `MessageBubble.tsx`, `SimilarOrdinancesPanel.tsx` |

---

## 5. 위험 요소 및 대응

| 위험 | 대응 |
|------|------|
| `pendingQAContent` → ArticleItemsModal pre-fill 흐름 | QAPanel에서 "현재 조항에 적용하기" 버튼은 `onApplyContent` 콜백으로 처리 — App.tsx가 여전히 중간에서 라우팅하므로 영향 없음 |
| `hasSession` 판별 로직 | `messages` 기반이 아니라 `sessionIdRef.current`와 별도 `hasSession` state로 관리 중 — 변경 없음 |
| `applyResponse`에서 `appendMessage` 호출 제거 | `applyResponse` 내 `appendMessage` 호출 라인만 제거. 나머지 state 업데이트(stage, draft, article_queue 등)는 유지 |
| `resetState`에서 `setMessages([])` 제거 | messages state 자체를 제거하므로 자동으로 정리됨 |
| TypeScript 미사용 import 오류 | `ChatMessage`, `SuggestedOption` 타입 import 제거 필요 |

---

## 6. 성공 기준

- [ ] `view='chat'` 진입 시 QA 패널이 메인 영역에 바로 표시됨
- [ ] 헤더 "새 조례 만들기" 버튼 클릭 → OnboardingWizard 모달 오픈
- [ ] OnboardingWizard 완료 → 세션 생성 → 이후 모달 흐름(ArticleItemsModal → DraftModal) 정상 동작
- [ ] QA 질문/답변 정상 동작 (세션 있을 때)
- [ ] ArticleItemsModal "질문하기" → QA 패널 → "조항 적용하기" pre-fill 정상 동작
- [ ] `ChatWindow.tsx`, `MessageBubble.tsx`, `SimilarOrdinancesPanel.tsx` 파일 삭제
- [ ] TypeScript 컴파일 오류 없음 (`npx tsc --noEmit`)
