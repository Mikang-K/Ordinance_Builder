import { useState } from 'react'
import type { SimilarOrdinance } from '../types'

interface Props {
  ordinances: SimilarOrdinance[]
}

export default function SimilarOrdinancesPanel({ ordinances }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <div className="similar-panel">
      <button
        className="similar-toggle"
        onClick={() => setOpen(prev => !prev)}
        aria-expanded={open}
      >
        <span className="similar-toggle-label">
          <span className="similar-toggle-icon">{open ? '▾' : '▸'}</span>
          유사 조례 사례
        </span>
        <span className="issue-count">{ordinances.length}건</span>
      </button>

      {open && (
        <ul className="similar-list">
          {ordinances.map((o) => (
            <li key={o.ordinance_id} className="similar-item">
              <div className="similar-header">
                <span className="similar-region">{o.region_name}</span>
                {o.similarity_score > 0 && (
                  <span className="similar-score">
                    유사도 {(o.similarity_score * 100).toFixed(1)}%
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <p className="similar-title" style={{ margin: 0, flex: 1 }}>{o.title}</p>
                <a
                  href={`https://www.law.go.kr/ordinSc.do?query=${encodeURIComponent(o.title)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ fontSize: '0.78rem', color: '#2563eb', whiteSpace: 'nowrap', textDecoration: 'none', border: '1px solid #bfdbfe', borderRadius: '4px', padding: '2px 7px', background: '#eff6ff', flexShrink: 0 }}
                >
                  원문 보기 ↗
                </a>
              </div>
              {o.relevance_reason && (
                <p className="similar-reason">{o.relevance_reason}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
