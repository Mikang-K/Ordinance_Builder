# Design: 온보딩 튜토리얼 (Onboarding Tutorial)

**Feature**: `onboarding-tutorial`
**Phase**: Design
**Architecture**: Option B — SVG Cutout 방식
**Created**: 2026-05-08

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | 신규 사용자 이탈률 감소 — 워크플로우를 모르면 첫 시도에서 포기 |
| **WHO** | 처음 서비스를 접하는 지방 공무원, 의회 관계자, 법령 연구자 |
| **RISK** | 단계 자동 진행 타이밍 오류, 기존 모달 z-index 충돌 |
| **SUCCESS** | 튜토리얼 완료 사용자가 독립적으로 조례 작성 완료 가능 |
| **SCOPE** | 프론트엔드 전용 (TutorialOverlay.tsx 신규 + App.tsx · SessionListScreen.tsx 최소 수정) |

---

## 1. 아키텍처 결정: Option B (SVG Cutout)

### 선택 이유

- 기존 컴포넌트 수정 최소화: `SessionListScreen.tsx`에 `id` 속성 하나만 추가
- 가장 정확한 spotlight 효과: SVG mask로 타겟 요소를 정밀하게 cutout
- DOM 요소를 직접 수정하지 않아 기존 레이아웃·z-index에 영향 없음

### 핵심 SVG 패턴

```svg
<svg position:fixed inset:0 z-index:180>
  <defs>
    <mask id="tutorial-cutout">
      <rect width="100%" height="100%" fill="white"/>        <!-- 전체 흰색 (보임) -->
      <rect x={rect.x-8} y={rect.y-8}                       <!-- 타겟 위치에 구멍 -->
            width={rect.width+16} height={rect.height+16}
            rx="8" fill="black"/>                            <!-- 검정 = 투명 -->
    </mask>
  </defs>
  <rect width="100%" height="100%"
        fill="rgba(0,0,0,0.55)" mask="url(#tutorial-cutout)"/>
</svg>
```

### 단계별 렌더링 전략

| 단계 | 화면 상태 | SVG 오버레이 | 말풍선 |
|------|-----------|-------------|--------|
| 0 | 목록 화면 (SessionListScreen) | ✅ + spotlight on `#btn-new-session` | 버튼 아래 |
| 1 | OnboardingWizard 열림 | ❌ (wizard 자체 backdrop 있음) | floating bottom-right |
| 2 | ArticleItemsModal 열림 | ❌ (modal 자체 배경 있음) | floating top-right |
| 3 | DraftModal 열림 | ❌ (modal 자체 배경 있음) | floating top-right |
| 4 | CompletedDraftModal (완료) | ✅ gentle overlay | center card |

---

## 2. 컴포넌트 설계

### 2.1 TutorialOverlay.tsx (신규)

```typescript
// ── 타입 ──────────────────────────────────────────────────────────────────────

interface StepConfig {
  targetSelector: string | null   // null = overlay 없는 floating 카드
  title: string
  description: string
  placement: 'bottom' | 'right' | 'top-right' | 'center'
  showDarkOverlay: boolean        // SVG dark overlay 표시 여부
}

// ── 5단계 정의 ────────────────────────────────────────────────────────────────

const TUTORIAL_STEPS: StepConfig[] = [
  {
    targetSelector: '#btn-new-session',
    title: '조례 작성을 시작해 볼까요?',
    description: '이 버튼을 눌러 새 조례 작성을 시작하세요. 마법사가 단계별로 안내해 드립니다.',
    placement: 'bottom',
    showDarkOverlay: true,
  },
  {
    targetSelector: null,
    title: '기본 정보를 입력해 주세요',
    description: '조례 유형·지역·목적·지원 대상을 선택하세요. 예시 칩을 클릭하거나 직접 입력할 수 있습니다. 완료 후 "조례 만들기 시작"을 눌러주세요.',
    placement: 'right',
    showDarkOverlay: false,
  },
  {
    targetSelector: null,
    title: '각 조문을 작성하세요',
    description: '왼쪽 목록에서 조항을 선택하고 내용을 입력하세요. "기본값"이라고 입력하면 AI가 유사 조례를 참고해 자동으로 채워 드립니다.',
    placement: 'top-right',
    showDarkOverlay: false,
  },
  {
    targetSelector: null,
    title: 'AI 초안을 확인하고 검증하세요',
    description: '생성된 조례 초안을 직접 수정할 수 있습니다. "법률 검증" 버튼으로 상위법과의 충돌 여부를 확인해 보세요.',
    placement: 'top-right',
    showDarkOverlay: false,
  },
  {
    targetSelector: null,
    title: '조례 초안이 완성되었습니다! 🎉',
    description: '처음 사용해 보셨군요! 앞으로도 조례 빌더 AI가 조례 작성을 도와드리겠습니다. 완성된 초안을 복사하거나 다운로드해 활용하세요.',
    placement: 'center',
    showDarkOverlay: true,
  },
]

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  step: number        // 0~4; -1 = 비활성 (렌더링 안 함)
  onNext: () => void  // 다음 단계 or 완료
  onSkip: () => void  // 즉시 종료 + localStorage 저장
}
```

### 2.2 내부 로직

```typescript
export default function TutorialOverlay({ step, onNext, onSkip }: Props) {
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null)
  const config = TUTORIAL_STEPS[step]

  // ── 타겟 요소 rect 계산 ────────────────────────────────────────────────────
  useEffect(() => {
    if (step < 0 || !config.targetSelector) {
      setTargetRect(null)
      return
    }
    const update = () => {
      const el = document.querySelector(config.targetSelector!)
      if (el) setTargetRect(el.getBoundingClientRect())
    }
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [step, config?.targetSelector])

  // ── Escape 키 처리 ─────────────────────────────────────────────────────────
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onSkip() }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onSkip])

  if (step < 0 || step >= TUTORIAL_STEPS.length) return null

  return (
    <>
      {/* SVG 오버레이 (step 0 spotlight, step 4 gentle overlay) */}
      {config.showDarkOverlay && (
        <SvgOverlay
          targetRect={config.targetSelector ? targetRect : null}
        />
      )}
      {/* 말풍선 카드 */}
      <TooltipCard
        step={step}
        total={TUTORIAL_STEPS.length}
        config={config}
        targetRect={targetRect}
        onNext={onNext}
        onSkip={onSkip}
      />
    </>
  )
}
```

### 2.3 SVG Overlay 서브컴포넌트

```typescript
function SvgOverlay({ targetRect }: { targetRect: DOMRect | null }) {
  const PAD = 8  // cutout 여백
  return (
    <svg
      style={{ position: 'fixed', inset: 0, width: '100%', height: '100%',
               zIndex: 180, pointerEvents: 'none' }}
    >
      <defs>
        <mask id="tutorial-mask">
          <rect width="100%" height="100%" fill="white" />
          {targetRect && (
            <rect
              x={targetRect.x - PAD} y={targetRect.y - PAD}
              width={targetRect.width + PAD * 2}
              height={targetRect.height + PAD * 2}
              rx="10" fill="black"
            />
          )}
        </mask>
      </defs>
      <rect
        width="100%" height="100%"
        fill="rgba(0,0,0,0.55)"
        mask="url(#tutorial-mask)"
      />
    </svg>
  )
}
```

### 2.4 Tooltip Card 위치 계산

| placement | 위치 계산 방법 |
|-----------|--------------|
| `bottom` | `top: rect.bottom + 16, left: rect.left + rect.width/2` (중앙 정렬) |
| `right` | `top: 50%, right: 24px` (화면 우측 세로 중앙, floating) |
| `top-right` | `top: 80px, right: 24px` (floating, 모달 상단 겹치지 않게) |
| `center` | `top: 50%, left: 50%, transform: translate(-50%, -50%)` |

> **bottom** 위치 시 화면 하단 넘침 방지: `top > window.innerHeight - cardHeight - 16` 이면 `bottom`을 `top` 방향으로 전환

---

## 3. App.tsx 변경 사항

### 3.1 추가 State

```typescript
// tutorial state (기존 state 선언 영역에 추가)
const [tutorialStep, setTutorialStep] = useState(-1)  // -1 = 비활성
```

### 3.2 자동 트리거 useEffect

```typescript
// 첫 로그인 시 자동 튜토리얼 시작
useEffect(() => {
  if (user && !localStorage.getItem('ordinance_tutorial_completed')) {
    // 인증 완료 시 목록 화면(view=list)에서 step 0 시작
    setTutorialStep(0)
  }
}, [user])
```

### 3.3 단계 자동 진행 useEffect

```typescript
// App 상태 변화를 감지해 tutorial step 자동 진행
useEffect(() => {
  if (tutorialStep < 0) return

  // step 0 → 1: OnboardingWizard 열림 감지
  if (tutorialStep === 0 && isOnboardingOpen) {
    setTutorialStep(1)
    return
  }
  // step 1 → 2: 마법사 완료 후 article 단계 진입
  if (tutorialStep === 1 && !isOnboardingOpen && stage === 'article_interviewing') {
    setTutorialStep(2)
    return
  }
  // step 2 → 3: 조항 제출 후 초안 생성
  if (tutorialStep === 2 && stage === 'draft_review') {
    setTutorialStep(3)
    return
  }
  // step 3 → 4: 초안 확정 완료
  if (tutorialStep === 3 && stage === 'completed') {
    setTutorialStep(4)
    return
  }
}, [tutorialStep, isOnboardingOpen, stage])
```

### 3.4 핸들러

```typescript
const TUTORIAL_KEY = 'ordinance_tutorial_completed'

const handleTutorialNext = () => {
  if (tutorialStep === 4) {
    setTutorialStep(-1)
    localStorage.setItem(TUTORIAL_KEY, 'true')
  }
  // 단계 0~3은 App 상태 변화로 자동 진행 — 수동 next 없음
}

const handleTutorialSkip = () => {
  setTutorialStep(-1)
  localStorage.setItem(TUTORIAL_KEY, 'true')
}
```

### 3.5 헤더 "도움말" 버튼

```typescript
// header-actions 영역에 추가 (하단 위치)
<button
  id="btn-tutorial-restart"
  onClick={() => setTutorialStep(0)}
  style={{
    padding: '6px 12px',
    background: 'rgba(255,255,255,0.15)',
    border: '1px solid rgba(255,255,255,0.35)',
    borderRadius: '8px',
    color: '#ffffff',
    fontSize: '0.82rem',
    cursor: 'pointer',
  }}
>
  ? 도움말
</button>
```

### 3.6 view === 'list' 렌더링 수정

```typescript
// 기존: return <SessionListScreen ... />
// 수정: Fragment로 감싸 TutorialOverlay 함께 렌더링
if (view === 'list') {
  return (
    <>
      <SessionListScreen
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        user={user}
        onLogout={handleLogout}
      />
      {tutorialStep >= 0 && (
        <TutorialOverlay
          step={tutorialStep}
          onNext={handleTutorialNext}
          onSkip={handleTutorialSkip}
        />
      )}
    </>
  )
}
```

### 3.7 view === 'chat' 렌더링 수정

```typescript
// return <div className="app"> ... </div> 마지막에 추가
{tutorialStep >= 0 && (
  <TutorialOverlay
    step={tutorialStep}
    onNext={handleTutorialNext}
    onSkip={handleTutorialSkip}
  />
)}
```

---

## 4. SessionListScreen.tsx 변경 사항

```typescript
// 기존 (line 80)
<button className="new-session-btn" onClick={onNewSession}>
  + 새 조례 만들기
</button>

// 수정 — id 속성 추가
<button id="btn-new-session" className="new-session-btn" onClick={onNewSession}>
  + 새 조례 만들기
</button>
```

**변경 범위**: 1줄 (id 속성만 추가, 기능·스타일 변경 없음)

---

## 5. App.css 추가 스타일

```css
/* ── Tutorial Tooltip Card ────────────────────────────────────────── */
.tutorial-card {
  position: fixed;
  z-index: 181;
  background: #ffffff;
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25), 0 0 0 1px rgba(30, 64, 175, 0.1);
  padding: 20px 24px;
  max-width: 320px;
  min-width: 260px;
  animation: tutorialCardIn 0.22s ease;
}

@keyframes tutorialCardIn {
  from { opacity: 0; transform: scale(0.94) translateY(6px); }
  to   { opacity: 1; transform: scale(1)    translateY(0); }
}

/* 말풍선 화살표 (step 0 — bottom 배치 시) */
.tutorial-card-arrow-top::before {
  content: '';
  position: absolute;
  top: -8px;
  left: 50%;
  transform: translateX(-50%);
  border: 8px solid transparent;
  border-bottom-color: #ffffff;
  border-top: none;
}

/* Dot indicator */
.tutorial-dots {
  display: flex;
  gap: 6px;
  justify-content: center;
  margin: 12px 0 0;
}
.tutorial-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #cbd5e1;
  transition: background 0.2s;
}
.tutorial-dot.active {
  background: #1e40af;
  width: 16px;
  border-radius: 3px;
}

/* Buttons */
.tutorial-btn-next {
  width: 100%;
  margin-top: 16px;
  padding: 10px;
  background: #1e40af;
  color: #ffffff;
  border: none;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
}
.tutorial-btn-skip {
  display: block;
  text-align: center;
  margin-top: 8px;
  font-size: 0.78rem;
  color: #94a3b8;
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
}
.tutorial-btn-skip:hover { color: #475569; }
```

---

## 6. z-index 계층 확인

| 계층 | z-index | 컴포넌트 |
|------|---------|---------|
| 최상위 | 200 | LoadingModal |
| 튜토리얼 | 181 | TutorialOverlay tooltip card |
| 튜토리얼 배경 | 180 | TutorialOverlay SVG overlay |
| QA 패널 | 150 | QAPanel backdrop |
| 일반 모달 | 100 | DraftModal / ArticleItemsModal / OnboardingWizard |

> **주의**: step 0의 SVG (z-index 180)이 DraftModal/ArticleItemsModal (z-index 100)보다 위에 있으므로, step 0은 반드시 view=list (모달 없음) 상태에서만 렌더링되어야 한다. step 1~4는 SVG overlay 없으므로 z-index 충돌 없음.

---

## 7. 구현 순서 (Session Guide)

### Module 1: 기반 (30분)
1. `TutorialOverlay.tsx` 생성 — props 인터페이스 + 빈 컴포넌트
2. `App.tsx` — `tutorialStep` state + `handleTutorialNext` + `handleTutorialSkip` 추가
3. `App.tsx` — view=list 렌더링을 Fragment로 변경, TutorialOverlay 연결
4. `SessionListScreen.tsx` — `id="btn-new-session"` 추가

### Module 2: SVG Cutout + Tooltip (60분)
5. `TutorialOverlay.tsx` — `SvgOverlay` 서브컴포넌트 구현
6. `TutorialOverlay.tsx` — `getBoundingClientRect` 위치 계산 + placement 로직
7. `TutorialOverlay.tsx` — `TooltipCard` 서브컴포넌트 구현 (title, desc, dots, buttons)
8. `App.css` — tutorial CSS 추가

### Module 3: 자동화 + 트리거 (30분)
9. `App.tsx` — 자동 트리거 useEffect (user 변화)
10. `App.tsx` — 단계 자동 진행 useEffect (stage, isOnboardingOpen 변화)
11. `App.tsx` — 헤더 "? 도움말" 버튼 추가
12. 기능 테스트: 5단계 전 단계 수동 검증

---

## 8. 테스트 시나리오

| 케이스 | 기대 동작 |
|--------|-----------|
| 첫 로그인 | tutorial step 0 자동 시작, SVG spotlight on "새 조례 만들기" 버튼 |
| 재방문 로그인 | localStorage 플래그 감지 → 튜토리얼 미표시 |
| "? 도움말" 버튼 클릭 | step 0부터 재시작 (localStorage 플래그 무시) |
| 건너뛰기 클릭 | 즉시 종료, localStorage 저장 |
| Escape 키 | 건너뛰기와 동일 |
| step 0 → 1 자동 진행 | "새 조례 만들기" 클릭 (=isOnboardingOpen=true) 시 step 1로 진행 |
| step 1 → 2 자동 진행 | 마법사 완료(stage=article_interviewing) 시 step 2로 진행 |
| step 2 → 3 자동 진행 | 조항 제출(stage=draft_review) 시 step 3으로 진행 |
| step 3 → 4 자동 진행 | 초안 확정(stage=completed) 시 step 4로 진행 |
| step 4 "확인" 클릭 | 튜토리얼 종료, localStorage 저장 |
| 창 크기 변경 | resize 이벤트에서 targetRect 재계산, spotlight 위치 업데이트 |
| 타겟 요소 없음 (step 0, DOM 미존재) | spotlight 없이 tooltip만 표시 (graceful fallback) |
