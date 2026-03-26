import type { Stage } from '../types'

const STAGES: { key: Stage; label: string }[] = [
  { key: 'intent_analysis', label: '의도 분석' },
  { key: 'interviewing', label: '정보 수집' },
  { key: 'retrieving', label: '법령 검색' },
  { key: 'drafting', label: '초안 작성' },
  { key: 'legal_checking', label: '법률 검토' },
]

const STAGE_INDEX: Record<string, number> = {
  intent_analysis: 0,
  interviewing: 1,
  retrieving: 2,
  drafting: 3,
  draft_review: 3,
  legal_review_requested: 4,
  legal_checking: 4,
  completed: 4,
}

interface Props {
  stage: Stage | null
}

export default function StageIndicator({ stage }: Props) {
  const currentIndex = stage ? (STAGE_INDEX[stage] ?? -1) : -1
  const isCompleted = stage === 'completed'

  return (
    <div className="stage-indicator">
      {STAGES.map((s, i) => {
        const done = isCompleted || i < currentIndex
        const active = !isCompleted && i === currentIndex
        return (
          <div key={s.key} className={`stage-step ${done ? 'done' : ''} ${active ? 'active' : ''}`}>
            <div className="stage-dot">{done ? '✓' : i + 1}</div>
            <span className="stage-label">{s.label}</span>
            {i < STAGES.length - 1 && <div className={`stage-line ${done ? 'done' : ''}`} />}
          </div>
        )
      })}
    </div>
  )
}
