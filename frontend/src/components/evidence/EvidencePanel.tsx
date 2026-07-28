import type { EvidenceApplyRequest, EvidenceItem } from '../../types'

interface Props {
  items: EvidenceItem[]
  currentArticleKey: string | null
  isLoading: boolean
  error: string | null
  deletingId: string | null
  onRetry: () => void
  onDelete: (item: EvidenceItem) => void
  onApply: (request: Omit<EvidenceApplyRequest, 'requestId'>) => void
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium' }).format(date)
}

export default function EvidencePanel({
  items,
  currentArticleKey,
  isLoading,
  error,
  deletingId,
  onRetry,
  onDelete,
  onApply,
}: Props) {
  if (isLoading) {
    return <p className="evidence-panel-state" role="status">저장한 근거를 불러오는 중입니다…</p>
  }

  if (error) {
    return (
      <div className="evidence-panel-state evidence-panel-error" role="alert">
        <p>{error}</p>
        <button type="button" onClick={onRetry}>다시 시도</button>
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="evidence-panel-state">
        <strong>저장한 근거가 없습니다.</strong>
        <p>Q&amp;A 답변에 표시된 법령 근거를 저장하면 이곳에서 다시 확인하고 조문에 적용할 수 있습니다.</p>
      </div>
    )
  }

  return (
    <ul className="evidence-list" aria-label={`저장한 근거 ${items.length}개`}>
      {items.map((item) => {
        const content = item.applicable_content?.trim() || item.content
        const isDeleting = deletingId === item.id
        return (
          <li key={item.id} className="evidence-card">
            <div className="evidence-card-heading">
              <div>
                <span className="evidence-source-type">{item.source_type}</span>
                <h3>{item.title}</h3>
              </div>
              {item.applied_at && <span className="evidence-applied-badge">적용됨</span>}
            </div>
            <p className="evidence-card-meta">
              {item.article_no || '조문 정보 없음'} · {formatDate(item.created_at)}
            </p>
            <p className="evidence-card-content">{item.content}</p>
            {item.note && <p className="evidence-card-note">메모: {item.note}</p>}
            <div className="evidence-card-actions">
              <button
                type="button"
                className="evidence-apply-button"
                disabled={!currentArticleKey || !content.trim() || isDeleting}
                onClick={() => currentArticleKey && onApply({
                  content,
                  evidenceId: item.id,
                  title: item.title,
                  targetArticleKey: currentArticleKey,
                })}
              >
                {currentArticleKey ? `${currentArticleKey}에 적용` : '적용할 조문 없음'}
              </button>
              <button
                type="button"
                className="evidence-delete-button"
                disabled={isDeleting}
                onClick={() => onDelete(item)}
              >
                {isDeleting ? '삭제 중…' : '삭제'}
              </button>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
