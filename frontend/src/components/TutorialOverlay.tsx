import { useState, useEffect } from 'react'

// ── Step Configs ─────────────────────────────────────────────────────────────

interface StepConfig {
  targetSelector: string | null
  title: string
  description: string
  placement: 'bottom' | 'right' | 'top-right' | 'center'
  showDarkOverlay: boolean
  nextLabel: string
}

const TUTORIAL_STEPS: StepConfig[] = [
  {
    targetSelector: '#btn-new-session',
    title: '조례 작성을 시작해 볼까요?',
    description: '이 버튼을 눌러 새 조례 작성을 시작하세요. 마법사가 단계별로 안내해 드립니다.',
    placement: 'bottom',
    showDarkOverlay: true,
    nextLabel: '알겠어요',
  },
  {
    targetSelector: null,
    title: '기본 정보를 입력해 주세요',
    description: '조례 유형·지역·목적·대상을 선택하세요. 예시 칩을 클릭하거나 직접 입력할 수 있습니다. 완료 후 "조례 만들기 시작"을 눌러주세요.',
    placement: 'right',
    showDarkOverlay: false,
    nextLabel: '알겠어요',
  },
  {
    targetSelector: null,
    title: '각 조문을 작성하세요',
    description: '왼쪽 목록에서 조항을 선택하고 내용을 입력하세요. "기본값"이라고 입력하면 AI가 유사 조례를 참고해 자동으로 채워 드립니다.',
    placement: 'top-right',
    showDarkOverlay: false,
    nextLabel: '알겠어요',
  },
  {
    targetSelector: null,
    title: 'AI 초안을 확인하고 검증하세요',
    description: '생성된 조례 초안을 직접 수정할 수 있습니다. "법률 검증" 버튼으로 상위법과의 충돌 여부를 확인해 보세요.',
    placement: 'top-right',
    showDarkOverlay: false,
    nextLabel: '알겠어요',
  },
  {
    targetSelector: null,
    title: '조례 초안이 완성되었습니다! 🎉',
    description: '처음 사용해 보셨군요! 앞으로도 조례 빌더 AI가 조례 작성을 도와드리겠습니다. 완성된 초안을 복사하거나 다운로드해 활용하세요.',
    placement: 'center',
    showDarkOverlay: true,
    nextLabel: '튜토리얼 완료',
  },
]

// ── SVG Dark Overlay with Spotlight Cutout ───────────────────────────────────

function SvgOverlay({ targetRect }: { targetRect: DOMRect | null }) {
  const PAD = 10
  return (
    <svg
      style={{
        position: 'fixed',
        inset: 0,
        width: '100%',
        height: '100%',
        zIndex: 180,
        pointerEvents: 'none',
      }}
    >
      <defs>
        <mask id="tutorial-mask">
          <rect width="100%" height="100%" fill="white" />
          {targetRect && (
            <rect
              x={targetRect.x - PAD}
              y={targetRect.y - PAD}
              width={targetRect.width + PAD * 2}
              height={targetRect.height + PAD * 2}
              rx="10"
              fill="black"
            />
          )}
        </mask>
      </defs>
      <rect
        width="100%"
        height="100%"
        fill="rgba(0,0,0,0.55)"
        mask="url(#tutorial-mask)"
      />
    </svg>
  )
}

// ── Tooltip Card Position ─────────────────────────────────────────────────────

function getCardStyle(
  placement: StepConfig['placement'],
  targetRect: DOMRect | null
): React.CSSProperties {
  const base: React.CSSProperties = {
    position: 'fixed',
    zIndex: 181,
    maxWidth: '300px',
    minWidth: '240px',
  }
  switch (placement) {
    case 'bottom': {
      if (targetRect) {
        const rawLeft = targetRect.left + targetRect.width / 2
        const clampedLeft = Math.max(16, Math.min(rawLeft, window.innerWidth - 316))
        const belowTop = targetRect.bottom + 16
        const cardHeight = 260
        // flip to above-target when card would overflow viewport bottom
        const top = belowTop + cardHeight > window.innerHeight
          ? targetRect.top - cardHeight - 16
          : belowTop
        return {
          ...base,
          top: Math.max(8, top),
          left: clampedLeft,
          transform: rawLeft === clampedLeft ? 'translateX(-50%)' : undefined,
        }
      }
      return { ...base, bottom: '120px', left: '50%', transform: 'translateX(-50%)' }
    }
    case 'right':
      return { ...base, bottom: '80px', right: '24px' }
    case 'top-right':
      return { ...base, top: '80px', right: '24px' }
    case 'center':
    default:
      return {
        ...base,
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        maxWidth: '360px',
      }
  }
}

// ── Tooltip Card ─────────────────────────────────────────────────────────────

function TooltipCard({
  step,
  total,
  config,
  targetRect,
  onNext,
  onSkip,
}: {
  step: number
  total: number
  config: StepConfig
  targetRect: DOMRect | null
  onNext: () => void
  onSkip: () => void
}) {
  const isLast = step === total - 1
  const showArrowTop = config.placement === 'bottom' && !!targetRect

  return (
    <div
      className={`tutorial-card${showArrowTop ? ' tutorial-card-arrow-top' : ''}`}
      style={getCardStyle(config.placement, targetRect)}
    >
      <p style={{
        fontSize: '0.72rem', fontWeight: 700, color: '#3b82f6',
        margin: '0 0 6px', textTransform: 'uppercase', letterSpacing: '0.05em',
      }}>
        STEP {step + 1} / {total}
      </p>
      <h3 style={{
        fontSize: '1rem', fontWeight: 700, color: '#1e293b',
        margin: '0 0 8px', lineHeight: 1.4,
      }}>
        {config.title}
      </h3>
      <p style={{ fontSize: '0.85rem', color: '#475569', lineHeight: 1.6, margin: 0 }}>
        {config.description}
      </p>

      <div className="tutorial-dots">
        {Array.from({ length: total }, (_, i) => (
          <div key={i} className={`tutorial-dot${i === step ? ' active' : ''}`} />
        ))}
      </div>

      {isLast ? (
        <button className="tutorial-btn-next" onClick={onNext}>
          {config.nextLabel} ✓
        </button>
      ) : (
        <p style={{
          fontSize: '0.78rem', color: '#94a3b8',
          margin: '12px 0 0', textAlign: 'center', lineHeight: 1.5,
        }}>
          각 단계를 완료하면 자동으로 다음으로 넘어갑니다
        </p>
      )}

      {!isLast && (
        <button className="tutorial-btn-skip" onClick={onSkip}>
          건너뛰기
        </button>
      )}
    </div>
  )
}

// ── Main Export ───────────────────────────────────────────────────────────────

interface Props {
  step: number        // 0~4 active; -1 = inactive
  onNext: () => void
  onSkip: () => void
}

export default function TutorialOverlay({ step, onNext, onSkip }: Props) {
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null)
  const config = TUTORIAL_STEPS[step]

  useEffect(() => {
    if (step < 0 || !config?.targetSelector) {
      setTargetRect(null)
      return
    }
    const el = document.querySelector(config.targetSelector!)
    const update = () => {
      const target = document.querySelector(config.targetSelector!)
      if (target) setTargetRect(target.getBoundingClientRect())
      else setTargetRect(null)
    }
    update()
    const ro = new ResizeObserver(update)
    if (el) ro.observe(el)
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [step, config?.targetSelector])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onSkip()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onSkip])

  if (step < 0 || step >= TUTORIAL_STEPS.length || !config) return null

  return (
    <>
      {config.showDarkOverlay && (
        <SvgOverlay targetRect={config.targetSelector ? targetRect : null} />
      )}
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
