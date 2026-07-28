import { useId } from 'react'

export type EvidenceApplyMode = 'append' | 'replace'

interface Props {
  articleKey: string
  sourceTitle: string
  mode: EvidenceApplyMode
  preview: string
  isDuplicate: boolean
  onModeChange: (mode: EvidenceApplyMode) => void
  onPreviewChange: (preview: string) => void
  onCancel: () => void
  onConfirm: () => void
}

export default function EvidenceApplyDialog({
  articleKey,
  sourceTitle,
  mode,
  preview,
  isDuplicate,
  onModeChange,
  onPreviewChange,
  onCancel,
  onConfirm,
}: Props) {
  const titleId = useId()
  const previewId = useId()

  return (
    <div className="evidence-apply-backdrop">
      <section
        className="evidence-apply-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <div className="evidence-apply-dialog-header">
          <div>
            <span className="evidence-dialog-kicker">근거 적용 미리보기</span>
            <h3 id={titleId}>{articleKey}에 적용</h3>
            <p>{sourceTitle}</p>
          </div>
          <button type="button" className="evidence-dialog-close" onClick={onCancel} aria-label="근거 적용 창 닫기">×</button>
        </div>

        <fieldset className="evidence-mode-fieldset">
          <legend>적용 방식</legend>
          <label>
            <input
              type="radio"
              name="evidence-apply-mode"
              checked={mode === 'append'}
              onChange={() => onModeChange('append')}
            />
            기존 내용 뒤에 추가
          </label>
          <label>
            <input
              type="radio"
              name="evidence-apply-mode"
              checked={mode === 'replace'}
              onChange={() => onModeChange('replace')}
            />
            기존 내용 바꾸기
          </label>
        </fieldset>

        {isDuplicate && (
          <p className="evidence-duplicate-warning" role="status">
            동일하거나 매우 유사한 내용이 현재 조문에 이미 포함되어 있습니다. 적용 전에 미리보기를 확인해 주세요.
          </p>
        )}

        <label className="evidence-preview-label" htmlFor={previewId}>적용 후 조문 내용</label>
        <textarea
          id={previewId}
          value={preview}
          onChange={(event) => onPreviewChange(event.target.value)}
          rows={10}
          autoFocus
        />

        <div className="evidence-dialog-actions">
          <button type="button" className="evidence-dialog-cancel" onClick={onCancel}>취소</button>
          <button
            type="button"
            className="evidence-dialog-confirm"
            disabled={!preview.trim()}
            onClick={onConfirm}
          >
            이 내용 적용
          </button>
        </div>
      </section>
    </div>
  )
}
