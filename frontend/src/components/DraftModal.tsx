import { useEffect, useRef, useState } from 'react'
import type { LegalIssue } from '../types'

interface Props {
  draft: string
  isLoading: boolean
  legalIssues: LegalIssue[] | null        // null = not checked yet
  isLegallyValid: boolean | null
  onRequestLegalReview: (editedDraft: string) => void
  onFinalize: (finalDraft: string) => void
  onClose: () => void
}

const SEVERITY_CONFIG = {
  HIGH:   { label: '위반',  color: '#ef4444', bg: '#fef2f2', icon: '🔴' },
  MEDIUM: { label: '주의',  color: '#f59e0b', bg: '#fffbeb', icon: '🟡' },
  LOW:    { label: '제안',  color: '#22c55e', bg: '#f0fdf4', icon: '🟢' },
}

export default function DraftModal({
  draft,
  isLoading,
  legalIssues,
  isLegallyValid,
  onRequestLegalReview,
  onFinalize,
  onClose,
}: Props) {
  const [editedDraft, setEditedDraft] = useState(draft)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Sync when a new draft arrives (e.g. after re-request)
  useEffect(() => {
    setEditedDraft(draft)
  }, [draft])

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const hasHighIssues = legalIssues?.some((i) => i.severity === 'HIGH') ?? false
  const sorted = legalIssues ? [...legalIssues].sort((a, b) => {
    const order = { HIGH: 0, MEDIUM: 1, LOW: 2 }
    return order[a.severity] - order[b.severity]
  }) : []

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose()
  }

  return (
    <div className="draft-modal-backdrop" onClick={handleBackdropClick}>
      <div className="draft-modal">

        {/* ── Header ── */}
        <div className="draft-modal-header">
          <div className="draft-modal-title">
            <span className="draft-modal-icon">📄</span>
            <h2>조례 초안 검토 · 편집</h2>
          </div>
          <button className="draft-modal-close" onClick={onClose} aria-label="닫기">✕</button>
        </div>

        {/* ── Hint ── */}
        <div className="draft-modal-hint">
          {legalIssues === null
            ? '초안을 직접 수정하신 후 법률 검증을 요청하세요.'
            : hasHighIssues
              ? '중대한 상위법 충돌이 있습니다. 수정 후 재검증하거나 이대로 확정할 수 있습니다.'
              : '법률 검증이 완료되었습니다. 수정이 없으면 초안을 확정하세요.'}
        </div>

        {/* ── Editable textarea ── */}
        <textarea
          ref={textareaRef}
          className="draft-modal-textarea"
          value={editedDraft}
          onChange={(e) => setEditedDraft(e.target.value)}
          spellCheck={false}
          disabled={isLoading}
        />

        {/* ── Legal issues panel (appears after first check) ── */}
        {legalIssues !== null && (
          <div className="draft-modal-issues">
            <div className="draft-modal-issues-header">
              <span className="draft-modal-issues-title">법률 검토 결과</span>
              <span className={`draft-modal-issues-badge ${hasHighIssues ? 'badge-high' : 'badge-ok'}`}>
                {hasHighIssues ? `⚠ 중대 이슈 ${legalIssues.filter(i => i.severity === 'HIGH').length}건` : '✓ 통과'}
              </span>
              <span className="draft-modal-issues-count">{legalIssues.length}건</span>
            </div>
            {sorted.length === 0 ? (
              <p className="draft-modal-no-issues">법률 이슈가 발견되지 않았습니다.</p>
            ) : (
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
            )}
          </div>
        )}

        {/* ── Footer ── */}
        <div className="draft-modal-footer">
          <button
            className="draft-modal-copy-btn"
            onClick={() => navigator.clipboard.writeText(editedDraft)}
            disabled={isLoading}
          >
            복사
          </button>

          <button
            className="draft-modal-review-btn"
            onClick={() => onRequestLegalReview(editedDraft)}
            disabled={isLoading || !editedDraft.trim()}
          >
            {isLoading ? '검토 중...' : legalIssues !== null ? '재검증 요청' : '법률 검증 요청'}
          </button>

          <button
            className={`draft-modal-finalize-btn ${hasHighIssues ? 'has-warning' : ''}`}
            onClick={() => onFinalize(editedDraft)}
            disabled={isLoading}
            title={hasHighIssues ? '중대한 법률 이슈가 있습니다. 그래도 확정하시겠습니까?' : '초안을 최종 확정합니다'}
          >
            초안 확정
          </button>
        </div>

      </div>
    </div>
  )
}
