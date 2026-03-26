import type { LegalIssue } from '../types'

const SEVERITY_CONFIG = {
  HIGH: { label: '위반', color: '#ef4444', bg: '#fef2f2', icon: '🔴' },
  MEDIUM: { label: '주의', color: '#f59e0b', bg: '#fffbeb', icon: '🟡' },
  LOW: { label: '제안', color: '#22c55e', bg: '#f0fdf4', icon: '🟢' },
}

interface Props {
  issues: LegalIssue[]
}

export default function LegalIssuesPanel({ issues }: Props) {
  const sorted = [...issues].sort((a, b) => {
    const order = { HIGH: 0, MEDIUM: 1, LOW: 2 }
    return order[a.severity] - order[b.severity]
  })

  return (
    <div className="issues-panel">
      <div className="panel-header">
        <h3>법률 검토 결과</h3>
        <span className="issue-count">{issues.length}건</span>
      </div>
      {sorted.length === 0 ? (
        <p className="no-issues">법률 이슈가 발견되지 않았습니다.</p>
      ) : (
        <ul className="issue-list">
          {sorted.map((issue, i) => {
            const cfg = SEVERITY_CONFIG[issue.severity]
            return (
              <li key={i} className="issue-item" style={{ borderLeftColor: cfg.color, background: cfg.bg }}>
                <div className="issue-header">
                  <span className="issue-icon">{cfg.icon}</span>
                  <span className="issue-severity" style={{ color: cfg.color }}>{cfg.label}</span>
                  {issue.related_provision && (
                    <span className="issue-article">{issue.related_provision}</span>
                  )}
                </div>
                <p className="issue-desc">{issue.description}</p>
                {issue.suggestion && (
                  <p className="issue-suggestion">💡 {issue.suggestion}</p>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
