import type { Stage } from '../types'

const STAGES: { key: Stage; label: string }[] = [
  { key: 'intent_analysis', label: '의도 분석' },
  { key: 'interviewing', label: '정보 수집' },
  { key: 'retrieving', label: '법령 검색' },
  { key: 'article_interviewing', label: '조항 작성' },
  { key: 'drafting', label: '초안 작성' },
  { key: 'legal_checking', label: '법률 검토' },
  { key: 'completed', label: '완료' },
]

const STAGE_INDEX: Record<string, number> = {
  intent_analysis: 0,
  interviewing: 1,
  retrieving: 2,
  article_interviewing: 3,
  article_complete: 3,
  drafting: 4,
  draft_review: 4,
  legal_review_requested: 5,
  legal_checking: 5,
  completed: 6,
  error: -1,
}

interface Props {
  stage: Stage | null
}

export default function StageIndicator({ stage }: Props) {
  const currentIndex = stage ? (STAGE_INDEX[stage] ?? -1) : -1
  const isCompleted = stage === 'completed'

  return (
    <div className="stage-indicator" aria-label="조례 작성 진행 단계">
      {STAGES.map((s, i) => {
        const done = isCompleted || i < currentIndex
        const active = !isCompleted && i === currentIndex
        return (
          <div key={s.key} className={`stage-step ${done ? 'done' : ''} ${active ? 'active' : ''}`}>
            <div className="stage-dot" aria-hidden="true">{done ? '✓' : i + 1}</div>
            <span className="stage-label">{s.label}</span>
            {i < STAGES.length - 1 && <div className={`stage-line ${done ? 'done' : ''}`} />}
          </div>
        )
      })}
    </div>
  )
}
