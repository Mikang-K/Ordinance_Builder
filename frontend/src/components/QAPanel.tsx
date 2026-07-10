import React, { useState, useRef, useEffect } from 'react'
import type { QAMessage, QASource, Stage } from '../types'
import { askQuestion, searchDirectQuestion } from '../api'

interface Props {
  sessionId: string | null
  stage: Stage | null
  currentArticleKey: string | null
  qaHistory: QAMessage[]
  onAddMessages: (messages: QAMessage[]) => void
  onApplyContent: (content: string) => void
  onNewSession?: () => void
  fontSize: number
}

const RELATION_TYPE_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  DELEGATES: { label: '위임', color: '#1d4ed8', bg: '#dbeafe' },
  BASED_ON:  { label: '근거', color: '#15803d', bg: '#dcfce7' },
  KEYWORD:   { label: '키워드', color: '#6b7280', bg: '#f3f4f6' },
  VECTOR:    { label: '유사', color: '#6b7280', bg: '#f3f4f6' },
}

function SourceBadge({ relationType }: { relationType: string }) {
  const badge = RELATION_TYPE_BADGE[relationType] ?? RELATION_TYPE_BADGE['KEYWORD']
  return (
    <span style={{
      fontSize: '0.7rem', fontWeight: 700, padding: '2px 7px', borderRadius: '10px',
      color: badge.color, background: badge.bg, flexShrink: 0,
    }}>
      {badge.label}
    </span>
  )
}

function SourceItem({ source }: { source: QASource }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px', overflow: 'hidden' }}>
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          width: '100%', textAlign: 'left', padding: '7px 10px', background: 'none',
          border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px',
        }}
      >
        <SourceBadge relationType={source.relation_type} />
        <span style={{ fontSize: '0.8rem', color: '#1e293b', fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {source.title}
        </span>
        <span style={{ fontSize: '0.75rem', color: '#64748b', flexShrink: 0 }}>{source.article_no}</span>
        <span style={{ fontSize: '0.7rem', color: '#64748b', flexShrink: 0 }}>{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded && (
        <div style={{ padding: '0 10px 10px', fontSize: '0.78rem', color: '#374151', lineHeight: '1.6', borderTop: '1px solid #e2e8f0', background: '#ffffff' }}>
          {source.content}
        </div>
      )}
    </div>
  )
}

// Renders **bold**, *italic*, and paragraph/list structure
function renderMarkdown(text: string): React.ReactNode {
  const lines = text.split('\n')
  const nodes: React.ReactNode[] = []
  let keyIdx = 0

  const renderInline = (line: string): React.ReactNode => {
    const parts: React.ReactNode[] = []
    const re = /(\*\*(.+?)\*\*|\*(.+?)\*)/g
    let last = 0, m: RegExpExecArray | null
    while ((m = re.exec(line)) !== null) {
      if (m.index > last) parts.push(line.slice(last, m.index))
      if (m[2] !== undefined) parts.push(<strong key={keyIdx++}>{m[2]}</strong>)
      else if (m[3] !== undefined) parts.push(<em key={keyIdx++}>{m[3]}</em>)
      last = m.index + m[0].length
    }
    if (last < line.length) parts.push(line.slice(last))
    return parts
  }

  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()

    if (!trimmed) { nodes.push(<div key={keyIdx++} style={{ height: '0.4em' }} />); i++; continue }

    // Heading: ## or ###
    if (/^#{1,3} /.test(trimmed)) {
      const level = (trimmed.match(/^#+/)![0].length)
      const content = trimmed.replace(/^#+\s*/, '')
      const fs = level === 1 ? '1rem' : level === 2 ? '0.92rem' : '0.87rem'
      nodes.push(
        <div key={keyIdx++} style={{ fontWeight: 700, fontSize: fs, color: '#1e293b', marginTop: '8px', marginBottom: '2px', borderBottom: level <= 2 ? '1px solid #e2e8f0' : undefined, paddingBottom: level <= 2 ? '3px' : undefined }}>
          {renderInline(content)}
        </div>
      )
      i++; continue
    }

    // Bullet list block
    if (/^[-•*] /.test(trimmed)) {
      const items: React.ReactNode[] = []
      while (i < lines.length && /^[-•*] /.test(lines[i].trim())) {
        items.push(<li key={keyIdx++} style={{ marginBottom: '3px' }}>{renderInline(lines[i].trim().slice(2))}</li>)
        i++
      }
      nodes.push(<ul key={keyIdx++} style={{ margin: '4px 0', paddingLeft: '18px', lineHeight: 1.65 }}>{items}</ul>)
      continue
    }

    // Numbered list block
    if (/^\d+[.)]\s/.test(trimmed)) {
      const items: React.ReactNode[] = []
      while (i < lines.length && /^\d+[.)]\s/.test(lines[i].trim())) {
        items.push(<li key={keyIdx++} style={{ marginBottom: '3px' }}>{renderInline(lines[i].trim().replace(/^\d+[.)]\s*/, ''))}</li>)
        i++
      }
      nodes.push(<ol key={keyIdx++} style={{ margin: '4px 0', paddingLeft: '20px', lineHeight: 1.65 }}>{items}</ol>)
      continue
    }

    nodes.push(<p key={keyIdx++} style={{ margin: '0 0 4px' }}>{renderInline(line)}</p>)
    i++
  }

  return <>{nodes}</>
}

function QAMessageBubble({
  msg, currentArticleKey, stage, onApply,
}: {
  msg: QAMessage
  currentArticleKey: string | null
  stage: Stage | null
  onApply: (content: string) => void
}) {
  const isUser = msg.role === 'user'
  const canApply = !isUser
    && stage === 'article_interviewing'
    && msg.applicable_content
    && msg.applicable_article_key === currentArticleKey

  return (
    <div className="qa-message-row" style={{ display: 'flex', flexDirection: 'column', gap: '6px', alignItems: isUser ? 'flex-end' : 'flex-start' }}>
      <div className="qa-message-bubble" style={{
        maxWidth: '88%',
        padding: '10px 13px',
        borderRadius: isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
        background: isUser ? '#1e40af' : '#ffffff',
        color: isUser ? '#ffffff' : '#1e293b',
        border: isUser ? 'none' : '1px solid #e2e8f0',
        fontSize: '0.88rem',
        lineHeight: '1.6',
        wordBreak: 'break-word',
      }}>
        {isUser ? msg.text : renderMarkdown(msg.text)}
      </div>

      {!isUser && msg.sources && msg.sources.length > 0 && (
        <div className="qa-source-list" style={{ maxWidth: '88%', width: '100%', display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <span style={{ fontSize: '0.72rem', color: '#64748b', paddingLeft: '2px' }}>📋 법령 근거</span>
          {msg.sources.map((s, i) => <SourceItem key={i} source={s} />)}
        </div>
      )}

      {canApply && msg.applicable_content && (
        <button
          onClick={() => onApply(msg.applicable_content!)}
          className="qa-apply-btn"
          style={{
            alignSelf: 'flex-start',
            padding: '6px 14px',
            background: '#0f766e',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '0.8rem',
            fontWeight: 600,
          }}
        >
          ↩ 현재 조항에 적용하기
        </button>
      )}
    </div>
  )
}

export default function QAPanel({
  sessionId, stage, currentArticleKey,
  qaHistory, onAddMessages, onApplyContent, onNewSession, fontSize,
}: Props) {
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [qaHistory])

  const handleSend = async () => {
    const q = input.trim()
    if (!q || isLoading) return
    setInput('')
    setIsLoading(true)

    const userMsg: QAMessage = { role: 'user', text: q }
    onAddMessages([userMsg])

    try {
      let res
      if (sessionId) {
        try {
          res = await askQuestion(sessionId, q)
        } catch {
          res = await searchDirectQuestion(q, { current_article_key: currentArticleKey })
        }
      } else {
        res = await searchDirectQuestion(q, { current_article_key: currentArticleKey })
      }
      const aiMsg: QAMessage = {
        role: 'ai',
        text: res.answer,
        sources: res.sources,
        applicable_content: res.applicable_content,
        applicable_article_key: res.applicable_article_key,
      }
      onAddMessages([aiMsg])
    } catch (e) {
      onAddMessages([{ role: 'ai', text: `오류가 발생했습니다: ${e instanceof Error ? e.message : '알 수 없는 오류'}` }])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  return (
    <div className="qa-panel" style={{
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      background: '#ffffff',
      fontSize: `${fontSize}px`,
    }}>
      {/* Header */}
      <div className="qa-panel-header" style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '14px 18px', borderBottom: '1px solid #e2e8f0',
        background: '#f8fafc', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '1rem' }}>🔍</span>
          <h2 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e293b', margin: 0 }}>법령 Q&amp;A</h2>
        </div>
        <span style={{ fontSize: '0.72rem', color: '#64748b' }}>{sessionId ? '세션 법령 우선' : '전체 DB 벡터 검색'}</span>
      </div>

      {/* Message history */}
      <div className="qa-message-list" style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {qaHistory.length === 0 && (
          <div style={{ margin: 'auto', textAlign: 'center', color: '#64748b', padding: '32px 16px' }}>
            <p style={{ fontSize: '1.8rem', marginBottom: '12px' }}>⚖️</p>
            <p style={{ fontSize: '0.9rem', fontWeight: 600, color: '#64748b', marginBottom: '6px' }}>법령 기반 Q&amp;A</p>
            <p style={{ fontSize: '0.82rem', lineHeight: 1.6 }}>
              {sessionId
                ? <>세션 생성 시 수집한 법령을 우선 참조하여 답변합니다.<br />해당 조례에 최적화된 법령 근거로 질문하세요.</>
                : <>질문을 임베딩하여 법령·조례 전체 DB를 벡터 검색합니다.<br />조례 초안 작성을 시작하려면 새 조례를 먼저 만드세요.</>
              }
            </p>
            {!sessionId && onNewSession && (
              <button
                className="qa-empty-action"
                onClick={onNewSession}
                style={{
                  marginTop: '16px',
                  padding: '10px 18px',
                  border: 'none',
                  borderRadius: '8px',
                  background: '#1e40af',
                  color: '#ffffff',
                  fontSize: '0.9rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                새 조례 만들기
              </button>
            )}
          </div>
        )}
        {qaHistory.map((msg, i) => (
          <QAMessageBubble
            key={i}
            msg={msg}
            currentArticleKey={currentArticleKey}
            stage={stage}
            onApply={onApplyContent}
          />
        ))}
        {isLoading && (
          <div style={{ display: 'flex', gap: '4px', alignItems: 'center', padding: '10px 14px', background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '12px', width: 'fit-content' }}>
            {[0, 200, 400].map((d) => (
              <span key={d} style={{ width: 7, height: 7, borderRadius: '50%', background: '#64748b', display: 'inline-block', animation: `bounce 1.2s ${d}ms infinite` }} />
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="qa-input-area" style={{
        display: 'flex', gap: '8px', padding: '12px 14px',
        borderTop: '1px solid #e2e8f0', background: 'white', flexShrink: 0,
        alignItems: 'flex-end',
      }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="법령·조례에 대해 질문하세요... (Shift+Enter 줄바꿈)"
          rows={2}
          disabled={isLoading}
          className="qa-input"
          id="qa-input"
          style={{
            flex: 1, padding: '9px 12px', border: '1px solid #cbd5e1', borderRadius: '8px',
            resize: 'none', fontSize: '0.88rem', fontFamily: 'inherit', outline: 'none',
            lineHeight: 1.5,
          }}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || isLoading}
          className="qa-send-btn"
          style={{
            padding: '9px 16px', background: '#1e40af', color: 'white', border: 'none',
            borderRadius: '8px', cursor: 'pointer', fontSize: '0.88rem', fontWeight: 600,
            whiteSpace: 'nowrap', opacity: (!input.trim() || isLoading) ? 0.5 : 1,
          }}
        >
          전송
        </button>
      </div>
    </div>
  )
}
