import type { LegalIssue } from '../types'

interface Props {
  draft: string
  legalIssues: LegalIssue[] | null
  onClose: () => void
}

const SEVERITY_CONFIG = {
  HIGH:   { label: '위반',  color: '#ef4444', bg: '#fef2f2', icon: '🔴' },
  MEDIUM: { label: '주의',  color: '#f59e0b', bg: '#fffbeb', icon: '🟡' },
  LOW:    { label: '제안',  color: '#22c55e', bg: '#f0fdf4', icon: '🟢' },
}

export default function CompletedDraftModal({ draft, legalIssues, onClose }: Props) {
  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose()
  }

  const sorted = legalIssues ? [...legalIssues].sort((a, b) => {
    const order = { HIGH: 0, MEDIUM: 1, LOW: 2 }
    return order[a.severity] - order[b.severity]
  }) : []

  return (
    <div className="draft-modal-backdrop" onClick={handleBackdropClick}>
      <div className="draft-modal completed-draft-modal">

        {/* Header */}
        <div className="draft-modal-header">
          <div className="draft-modal-title">
            <span className="draft-modal-icon">✅</span>
            <h2>확정 조례 초안</h2>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              className="draft-modal-copy-btn"
              onClick={() => navigator.clipboard.writeText(draft)}
            >
              복사
            </button>
            <button className="draft-modal-close" onClick={onClose} aria-label="닫기">✕</button>
          </div>
        </div>

        {/* Draft text */}
        <div className="completed-draft-body">
          <pre className="completed-draft-text">{draft}</pre>
        </div>

        {/* Legal issues */}
        {legalIssues && legalIssues.length > 0 && (
          <div className="draft-modal-issues">
            <div className="draft-modal-issues-header">
              <span className="draft-modal-issues-title">법률 검토 결과</span>
              <span className="draft-modal-issues-count">{legalIssues.length}건</span>
            </div>
            <ul className="draft-modal-issue-list">
              {sorted.map((issue, i) => {
                const cfg = SEVERITY_CONFIG[issue.severity]
                return (
                  <li
                    key={i}
                    className="draft-modal-issue-item"
                    style={{ borderLeftColor: cfg.color, background: cfg.bg }}
                  >
                    <div className="draft-modal-issue-row">
                      <span>{cfg.icon}</span>
                      <span className="draft-modal-issue-severity" style={{ color: cfg.color }}>
                        {cfg.label}
                      </span>
                      {issue.related_provision && (
                        <span className="draft-modal-issue-ref">
                          {issue.related_statute} {issue.related_provision}
                        </span>
                      )}
                    </div>
                    <p className="draft-modal-issue-desc">{issue.description}</p>
                    {issue.suggestion && (
                      <p className="draft-modal-issue-suggest">💡 {issue.suggestion}</p>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        )}

        <div className="draft-modal-footer" style={{ justifyContent: 'flex-end' }}>
          <button className="draft-modal-close-footer-btn" onClick={onClose}>닫기</button>
        </div>
      </div>
    </div>
  )
}
