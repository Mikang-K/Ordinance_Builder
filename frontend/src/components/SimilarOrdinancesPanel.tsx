import type { SimilarOrdinance } from '../types'

interface Props {
  ordinances: SimilarOrdinance[]
}

export default function SimilarOrdinancesPanel({ ordinances }: Props) {
  return (
    <div className="similar-panel">
      <div className="panel-header">
        <h3>유사 조례 사례</h3>
        <span className="issue-count">{ordinances.length}건</span>
      </div>
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
            <p className="similar-title">{o.title}</p>
            {o.relevance_reason && (
              <p className="similar-reason">{o.relevance_reason}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
