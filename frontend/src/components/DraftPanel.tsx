interface Props {
  draft: string
}

export default function DraftPanel({ draft }: Props) {
  const handleCopy = () => {
    navigator.clipboard.writeText(draft)
  }

  return (
    <div className="draft-panel">
      <div className="panel-header">
        <h3>조례 초안</h3>
        <button className="copy-btn" onClick={handleCopy}>복사</button>
      </div>
      <pre className="draft-text">{draft}</pre>
    </div>
  )
}
