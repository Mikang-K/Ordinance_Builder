import { useEffect, useState } from 'react'
import { downloadFinalResult } from '../api'
import type { LegalIssue } from '../types'

interface Props {
  sessionId: string
  draft: string
  legalIssues: LegalIssue[] | null
  onClose: () => void
}

const SEVERITY_CONFIG = {
  HIGH: { label: '위반', color: '#ef4444', bg: '#fef2f2' },
  MEDIUM: { label: '주의', color: '#f59e0b', bg: '#fffbeb' },
  LOW: { label: '제안', color: '#22c55e', bg: '#f0fdf4' },
} as const

const DEFAULT_FILE_BASENAME = '조례-최종-초안'

function normalizeFilename(value: string, format: 'txt' | 'docx') {
  const withoutExtension = value
    .trim()
    .replace(/[<>:"/\\|?*\u0000-\u001F]/g, '-')
    .replace(/\.+$/, '')
    .replace(/\.(txt|docx)$/i, '')
  return `${withoutExtension || DEFAULT_FILE_BASENAME}.${format}`
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export default function CompletedDraftModal({ sessionId, draft, legalIssues, onClose }: Props) {
  const [downloadingFormat, setDownloadingFormat] = useState<'txt' | 'docx' | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [filename, setFilename] = useState(DEFAULT_FILE_BASENAME)

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose()
  }

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const handleDownload = async (format: 'txt' | 'docx') => {
    if (downloadingFormat) return

    setDownloadError(null)
    setDownloadingFormat(format)
    try {
      const downloadName = normalizeFilename(filename, format)
      const blob = await downloadFinalResult(sessionId, format, downloadName)
      saveBlob(blob, downloadName)
    } catch (e) {
      console.error('final result download failed:', e)
      setDownloadError('파일 저장에 실패했습니다. 잠시 후 다시 시도해 주세요.')
    } finally {
      setDownloadingFormat(null)
    }
  }

  const sorted = legalIssues ? [...legalIssues].sort((a, b) => {
    const order = { HIGH: 0, MEDIUM: 1, LOW: 2 }
    return order[a.severity] - order[b.severity]
  }) : []

  return (
    <div className="draft-modal-backdrop" onClick={handleBackdropClick}>
      <div
        className="draft-modal completed-draft-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="completed-draft-title"
      >
        <div className="draft-modal-header completed-draft-header">
          <div className="draft-modal-title">
            <span className="draft-modal-icon" aria-hidden="true">✓</span>
            <h2 id="completed-draft-title">확정 조례 초안</h2>
          </div>
          <div className="completed-draft-actions">
            <label className="completed-draft-filename">
              <span>파일 이름</span>
              <input
                type="text"
                value={filename}
                onChange={(event) => setFilename(event.target.value)}
                placeholder={DEFAULT_FILE_BASENAME}
                disabled={downloadingFormat !== null}
              />
            </label>
            <button
              className="draft-modal-copy-btn"
              onClick={() => navigator.clipboard.writeText(draft)}
            >
              복사
            </button>
            <button
              className="draft-modal-copy-btn"
              disabled={downloadingFormat !== null}
              onClick={() => handleDownload('txt')}
            >
              {downloadingFormat === 'txt' ? '저장 중...' : 'TXT 저장'}
            </button>
            <button
              className="draft-modal-copy-btn"
              disabled={downloadingFormat !== null}
              onClick={() => handleDownload('docx')}
            >
              {downloadingFormat === 'docx' ? '저장 중...' : 'Word 저장'}
            </button>
            <button className="draft-modal-close" onClick={onClose} aria-label="닫기">×</button>
          </div>
        </div>

        {downloadError && (
          <div className="completed-draft-error" role="alert">
            {downloadError}
          </div>
        )}

        <div className="completed-draft-body">
          <pre className="completed-draft-text">{draft}</pre>
        </div>

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
                      <p className="draft-modal-issue-suggest">제안: {issue.suggestion}</p>
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
