# Plan: 온보딩 튜토리얼 (Onboarding Tutorial)

**Feature**: `onboarding-tutorial`
**Phase**: Plan
**Created**: 2026-05-08

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 처음 사용하는 사용자가 조례 빌더 AI의 5단계 워크플로우(유형선택→기본정보→조항작성→초안생성→법률검증)를 파악하지 못해 조례 작성을 완료하지 못하고 이탈 |
| **Solution** | 툴팁 오버레이 방식으로 각 UI 요소를 직접 가리키며 실제 조례 작성을 따라할 수 있도록 단계별 안내 제공 |
| **Functional UX** | 첫 로그인 시 자동 표시 + 헤더 재시작 버튼. 실제 API를 호출하며 진행하여 튜토리얼 완료 = 실제 조례 초안 생성 완료 |
| **Core Value** | 처음 사용하는 사람도 5단계 안내를 따라 실제 조례 초안 + 법률 검증 결과까지 완성 가능 |

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | 신규 사용자 이탈률 감소 — UI 진입 후 워크플로우를 모르면 첫 시도에서 포기 |
| **WHO** | 처음 서비스를 접하는 지방 공무원, 의회 관계자, 법령 연구자 |
| **RISK** | 튜토리얼 진행 중 단계 자동 전진 타이밍이 맞지 않으면 오히려 혼란 야기 |
| **SUCCESS** | 튜토리얼 완료 사용자가 이후 세션 없이도 독립적으로 조례 작성 완료 가능 |
| **SCOPE** | 프론트엔드 전용 (TutorialOverlay.tsx 신규 + App.tsx 수정). 백엔드 변경 없음 |

---

## 1. 배경 및 목적

### 1.1 현황

조례 빌더 AI는 다음 5개 주요 UI 단계를 거쳐 조례 초안을 생성한다:

```
목록 화면 → OnboardingWizard(기본정보) → ArticleItemsModal(조항작성)
         → DraftModal(초안 확인·법률검증) → CompletedDraftModal(완성)
```

현재 각 화면은 독립적으로 기능하지만, 처음 사용하는 사용자에게 "다음에 무엇을 해야 하는가"를 안내하는 흐름이 없다.

### 1.2 목표

- 첫 로그인 사용자에게 자동으로 툴팁 오버레이 튜토리얼 제공
- 실제 조례 작성을 진행하면서 튜토리얼을 완료 → 튜토리얼 완료 = 조례 초안 완성
- localStorage 플래그로 이미 완료한 사용자에게 재표시 방지

---

## 2. 기능 요구사항

### FR-01: TutorialOverlay 컴포넌트

**설명**: 화면 위에 반투명 배경을 오버레이하고 특정 UI 요소를 spotlight(밝게 강조)한 뒤, 해당 요소 인근에 말풍선 툴팁을 표시한다.

**세부 사항**:
- 반투명 배경 (`rgba(0,0,0,0.55)`) + 타겟 요소 cutout (밝게 보임)
- 말풍선 위치: 타겟 요소 기준 top/bottom/left/right 자동 계산
- "이해했어요! →" 버튼: 다음 단계 진행
- "건너뛰기" 링크: 즉시 튜토리얼 종료 + localStorage 플래그 저장
- 현재 단계 표시: "2 / 5" dot indicator

**props**:
```typescript
interface TutorialStep {
  targetSelector: string         // CSS selector (e.g., '#btn-new-session')
  title: string                  // 말풍선 제목
  description: string            // 설명 텍스트
  placement: 'top' | 'bottom' | 'left' | 'right'
  advanceOn?: 'button' | 'auto'  // 'button': 수동 진행 / 'auto': 조건 충족 시
}
```

### FR-02: 5단계 튜토리얼 시나리오

| 단계 | 화면/상태 | 타겟 요소 | 안내 내용 |
|------|-----------|-----------|-----------|
| **1** | 목록 화면 | "새 조례 만들기" 버튼 | "시작해 볼까요? 이 버튼을 눌러 새 조례 작성을 시작하세요." |
| **2** | OnboardingWizard | 마법사 패널 전체 | "조례 유형과 기본 정보를 선택해 주세요. 단계마다 예시를 선택하거나 직접 입력할 수 있습니다." |
| **3** | ArticleItemsModal | 조항 목록 영역 | "각 조문의 내용을 작성하세요. '기본값'을 입력하면 AI가 유사 조례를 참고해 자동 생성합니다." |
| **4** | DraftModal | 초안 텍스트 영역 + 검증 버튼 | "AI가 생성한 초안을 확인하세요. 직접 수정 후 '법률 검증'을 눌러 상위법과의 충돌을 확인할 수 있습니다." |
| **5** | CompletedDraftModal 또는 DraftModal 완료 시 | 전체 화면 | "축하합니다! 조례 초안이 완성되었습니다. '복사' 또는 '다운로드'로 저장하세요." |

> **Note**: 단계 2~4는 사용자가 실제 행동을 완료하면 자동으로 다음 단계로 진행 (`stage` 변화 감지). 단계 1·5는 버튼 클릭으로 수동 진행.

### FR-03: 트리거

**자동 트리거 (첫 로그인)**:
```typescript
// App.tsx — 인증 완료 후 체크
useEffect(() => {
  if (user && !localStorage.getItem('tutorial_completed')) {
    setTutorialStep(0)   // 0: 활성, -1: 비활성
    setIsTutorialActive(true)
  }
}, [user])
```

**수동 트리거 (헤더 버튼)**:
- 헤더 `header-actions` 영역에 "?" 버튼 추가
- 클릭 시 `setIsTutorialActive(true)`, `setTutorialStep(0)` 실행
- 로그인 여부 무관하게 항상 표시

### FR-04: localStorage 완료 플래그

```typescript
const TUTORIAL_KEY = 'ordinance_tutorial_completed'

// 완료 시 저장
localStorage.setItem(TUTORIAL_KEY, 'true')

// 자동 트리거 시 체크
if (!localStorage.getItem(TUTORIAL_KEY)) { /* 튜토리얼 시작 */ }
```

건너뛰기 시에도 동일하게 저장하여 다음 방문에서 재표시하지 않는다.

---

## 3. 비기능 요구사항

| 항목 | 요구사항 |
|------|---------|
| **외부 라이브러리** | 미사용. 순수 React + CSS만으로 구현 |
| **z-index** | 180 (LoadingModal 200 아래, QAPanel 150 위) |
| **반응형** | 모바일(360px) ~ 데스크톱(1400px) 레이아웃 모두 지원 |
| **접근성** | 키보드 `Escape`로 튜토리얼 종료 가능 |
| **성능** | `getBoundingClientRect()` 기반 위치 계산, ResizeObserver로 리사이즈 대응 |
| **타겟 미발견 시** | 타겟 selector가 DOM에 없으면 해당 단계 건너뜀 (graceful skip) |

---

## 4. 구현 범위 (파일 목록)

### 신규 파일

| 파일 | 설명 |
|------|------|
| `frontend/src/components/TutorialOverlay.tsx` | 툴팁 오버레이 메인 컴포넌트 |

### 수정 파일

| 파일 | 변경 내용 |
|------|-----------|
| `frontend/src/App.tsx` | tutorial state 2개 추가, 자동 트리거 useEffect, 헤더 "?" 버튼, TutorialOverlay 렌더링 |
| `frontend/src/App.css` | `.tutorial-*` 클래스 CSS (spotlight 애니메이션, 말풍선 스타일) |

### 변경 없음

- 백엔드 전체
- `OnboardingWizard.tsx`, `ArticleItemsModal.tsx`, `DraftModal.tsx` 등 기존 컴포넌트

---

## 5. 단계 자동 진행 로직

Tutorial 단계와 App의 `stage` 상태를 연동하여 사용자 행동 후 자동으로 다음 단계로 진행한다:

```
tutorialStep 0 (목록 화면)
  → 사용자가 "새 조례 만들기" 클릭 시 → tutorialStep 1
     (view === 'chat' && isOnboardingOpen 감지)

tutorialStep 1 (OnboardingWizard)
  → 마법사 완료 후 stage 변화 시 → tutorialStep 2
     (stage === 'retrieving' || stage === 'article_interviewing' 감지)

tutorialStep 2 (ArticleItemsModal)
  → 조항 제출 후 → tutorialStep 3
     (stage === 'draft_review' 감지)

tutorialStep 3 (DraftModal)
  → 초안 확정 후 → tutorialStep 4
     (stage === 'completed' 감지)

tutorialStep 4 (완료)
  → "확인" 버튼 클릭 → 튜토리얼 종료 + localStorage 저장
```

---

## 6. 리스크 및 완화 방안

| 리스크 | 가능성 | 완화 방안 |
|--------|--------|-----------|
| 단계 자동 진행 타이밍 오류 (너무 빠름/늦음) | 중 | `useEffect`의 `stage` 의존성으로 정확한 감지. 혹시 놓치면 수동 "다음" 버튼으로 보완 |
| spotlight cutout이 동적 레이아웃에서 위치 틀림 | 중 | `ResizeObserver` + `scroll` 이벤트에서 재계산 |
| 기존 모달과 z-index 충돌 | 낮 | z-index 계층을 CLAUDE.md §11에 명시된 기준으로 적용 |
| 튜토리얼 도중 오류 발생 시 (LLM 실패 등) | 중 | 기존 에러 처리 그대로 유지. 튜토리얼은 단지 시각적 안내이므로 오류와 독립적 |

---

## 7. 성공 기준

1. 첫 로그인 사용자에게 자동으로 튜토리얼 오버레이가 표시된다.
2. 5단계 툴팁이 각 UI 요소를 정확히 가리키며 사용자 행동에 맞춰 자동 진행된다.
3. 튜토리얼을 완료하면 localStorage에 플래그가 저장되어 재방문 시 자동 표시되지 않는다.
4. 헤더 "?" 버튼으로 언제든 튜토리얼을 재시작할 수 있다.
5. "건너뛰기" 클릭 시 즉시 종료되고 플래그가 저장된다.
6. 기존 기능(조례 작성, QA 패널, 초안 검증 등)에 영향 없음.
