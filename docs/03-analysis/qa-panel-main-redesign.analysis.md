# Analysis: qa-panel-main-redesign

**작성일**: 2026-04-30
**Phase**: Check
**Match Rate**: 100% (수정 후)

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | 채팅창이 모달로 대체되어 빈 공간만 차지하게 됨. QA 기능이 더 높은 상시 활용가치를 가짐 |
| **WHO** | 지자체 담당자 — 조례 생성 중 관련 법령을 수시로 조회해야 하는 사용자 |
| **RISK** | `pendingQAContent` → ArticleItemsModal pre-fill 흐름 유지 필요 |
| **SUCCESS** | 채팅 관련 state/컴포넌트 완전 제거 / QA 패널이 메인 영역에서 정상 동작 |
| **SCOPE** | 프론트엔드 전용 변경. 백엔드 API 변경 없음 |

---

## 1. 구현 검증 결과

### 1.1 Structural Match: 7/7 ✅

| # | 항목 | 결과 | 증거 |
|---|------|:----:|------|
| 1 | `ChatWindow.tsx` 삭제 | ✅ | 파일 없음 |
| 2 | `MessageBubble.tsx` 삭제 | ✅ | 파일 없음 |
| 3 | `SimilarOrdinancesPanel.tsx` 삭제 | ✅ | 파일 없음 |
| 4 | `QAPanel.tsx` — `isOpen`/`onClose` 제거, 오버레이 제거 | ✅ | `height: 100%` 정적 레이아웃, backdrop 없음 |
| 5 | `OnboardingWizard.tsx` — `isOpen`/`onClose` 추가, 모달 래퍼 추가 | ✅ | `position: fixed, inset: 0, zIndex: 100` |
| 6 | `App.tsx` — `.qa-main-area` 내에 `<QAPanel>` 배치 | ✅ | App.tsx:415 |
| 7 | `App.css` — `.qa-main-area` 클래스 추가 | ✅ | App.css:89 (`.chat-area, .qa-main-area`) |

### 1.2 Functional Depth: 9/9 ✅

| # | 항목 | 결과 | 증거 |
|---|------|:----:|------|
| 1 | `messages`, `input` state 제거 | ✅ | App.tsx — grep 결과 없음 |
| 2 | `appendMessage`, `sendText`, `handleSend`, `handleKeyDown`, `handleOptionSelect` 제거 | ✅ | App.tsx — grep 결과 없음 |
| 3 | `isOnboardingOpen` state + `handleWizardStart` 함수 추가 | ✅ | App.tsx:59, :143 |
| 4 | `isQAPanelOpen` state 제거 | ✅ | App.tsx — grep 결과 없음 |
| 5 | 헤더 "✚ 새 조례 만들기" 버튼 추가, "🔍 질문" 버튼 제거 | ✅ | App.tsx:388-398 |
| 6 | QAPanel이 `isOpen`/`onClose` 없이 사용됨 | ✅ | App.tsx:416-427 |
| 7 | `handleWizardStart`에서 `createSession` 호출 | ✅ | App.tsx:148 |
| 8 | `ChatMessage`, `SuggestedOption` import 제거 | ✅ | App.tsx:2 — `LegalIssue, QAMessage, SimilarOrdinance, Stage`만 import |
| 9 | `ChatWindow`, `SimilarOrdinancesPanel` import 제거 | ✅ | App.tsx:6-13 |

### 1.3 CSS Contract: 2/2 ✅

| # | 항목 | 결과 |
|---|------|:----:|
| 1 | `.qa-main-area` 클래스 존재 | ✅ |
| 2 | 기능 동작에 영향 없음 (orphaned styles는 minor) | ✅ |

### 1.4 TypeScript: PASS ✅

`npx tsc --noEmit` — 오류 0개 (수정 후 확인)

---

## 2. Success Criteria 달성 현황

| # | 기준 | 상태 | 증거 |
|---|------|:----:|------|
| 1 | `view='chat'` → QA 패널이 메인 영역에 표시 | ✅ | App.tsx:414-427 |
| 2 | "새 조례 만들기" → OnboardingWizard 모달 오픈 | ✅ | App.tsx:388-398 → `setIsOnboardingOpen(true)` |
| 3 | Wizard 완료 → 세션 생성 → ArticleItemsModal→DraftModal 흐름 | ✅ | `handleWizardStart` → `createSession` → `applyResponse` |
| 4 | QA 질문/답변 정상 동작 | ✅ | QAPanel에 `sessionId` 전달, `askQuestion` 호출 유지 |
| 5 | ArticleItemsModal → QA → "조항 적용하기" pre-fill | ✅ | `pendingQAContent` + `onApplyContent` 콜백 유지 |
| 6 | 파일 3개 삭제 | ✅ | ChatWindow, MessageBubble, SimilarOrdinancesPanel 없음 |
| 7 | TypeScript 컴파일 오류 없음 | ✅ | `tsc --noEmit` 0 errors |

**Success Criteria: 7/7 달성**

---

## 3. 발견된 이슈 및 수정 내역

### 3.1 Critical → 즉시 수정 완료 ✅

| 항목 | 위치 | 설명 | 조치 |
|------|------|------|------|
| **Rules of Hooks 위반** | `OnboardingWizard.tsx:222` | `if (!isOpen) return null`이 `useState` 호출 이전에 위치 → `isOpen`이 `false→true` 전환 시 hook 순서 변경으로 런타임 크래시 발생 | `if (!isOpen) return null`을 4개 `useState` 선언 이후로 이동 |

### 3.2 Minor (비기능적, 향후 정리)

| 항목 | 위치 | 설명 |
|------|------|------|
| 고아 CSS | `App.css` — `.chat-window`, `.empty-state`, `.message-row`, `.bubble` | 삭제된 컴포넌트의 CSS 잔여. 동작에 영향 없음 |
| 미사용 타입 | `types.ts` — `ChatMessage.suggested_options`, `SuggestedOption` | `App.tsx`에서 참조 제거됨. 백엔드 응답 인터페이스에는 유지 중 |

---

## 4. Match Rate

| 축 | 점수 | 가중치 | 기여 |
|----|:----:|:------:|:----:|
| Structural | 100% | 0.20 | 20.0 |
| Functional | 100% | 0.40 | 40.0 |
| Contract (CSS) | 100% | 0.20 | 20.0 |
| TypeScript | 100% | 0.20 | 20.0 |
| **합계** | — | — | **100%** |

**Overall Match Rate: 100%** ✅ (hooks 버그 수정 후)

---

## 5. 다음 단계

Match Rate 100% — `/pdca report qa-panel-main-redesign` 또는 Cloud Build + 배포 진행 가능.
