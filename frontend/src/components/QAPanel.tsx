import { useEffect, useId, useRef, useState } from 'react'
import type { EvidenceApplyRequest, EvidenceItem, QAMessage, QASource, Stage } from '../types'
import {
  askQuestion,
  createEvidence,
  deleteEvidence,
  listEvidence,
  searchDirectQuestion,
} from '../api'
import EvidencePanel from './evidence/EvidencePanel'

interface Props {
  sessionId: string | null
  stage: Stage | null
  currentArticleKey: string | null
  qaHistory: QAMessage[]
  onAddMessages: (messages: QAMessage[]) => void
  onApplyContent: (request: Omit<EvidenceApplyRequest, 'requestId'>) => void
  onNewSession?: () => void
  fontSize: number
  evidenceRefreshKey?: number
}

const relationLabels: Record<string, string> = {
  DELEGATES: '위임',
  BASED_ON: '근거',
  KEYWORD: '키워드',
  VECTOR: '유사',
}

function evidenceKey(source: QASource): string {
  return [source.source_type, source.title, source.article_no, source.content].join('\u001f')
}

function SourceItem({
  source,
  canSave,
  isSaved,
  isSaving,
  onSave,
}: {
  source: QASource
  canSave: boolean
  isSaved: boolean
  isSaving: boolean
  onSave: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const contentId = useId()
  return (
    <div className="qa-source-item">
      <div className="qa-source-heading">
        <button
          type="button"
          className="qa-source-toggle"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          aria-controls={contentId}
        >
          <span className="qa-source-relation">{relationLabels[source.relation_type] ?? '근거'}</span>
          <span className="qa-source-title">{source.title}</span>
          <span className="qa-source-article">{source.article_no}</span>
          <span aria-hidden="true">{expanded ? '−' : '+'}</span>
        </button>
        <button
          type="button"
          className="qa-source-save"
          disabled={!canSave || isSaved || isSaving}
          onClick={onSave}
          title={!canSave ? '세션을 시작한 뒤 저장할 수 있습니다.' : undefined}
        >
          {isSaved ? '저장됨' : isSaving ? '저장 중…' : '근거 저장'}
        </button>
      </div>
      {expanded && <p id={contentId} className="qa-source-content">{source.content}</p>}
    </div>
  )
}

function MessageBubble({
  message,
  stage,
  currentArticleKey,
  evidence,
  savingKey,
  onSaveSource,
  onApply,
}: {
  message: QAMessage
  stage: Stage | null
  currentArticleKey: string | null
  evidence: EvidenceItem[]
  savingKey: string | null
  onSaveSource: (source: QASource) => void
  onApply: (request: Omit<EvidenceApplyRequest, 'requestId'>) => void
}) {
  const isUser = message.role === 'user'
  const applyContent = message.applicable_content?.trim() || message.text.trim()
  const canApply = !isUser && stage === 'article_interviewing' && Boolean(currentArticleKey && applyContent)

  return (
    <article className={`qa-message-row ${isUser ? 'is-user' : 'is-assistant'}`} aria-label={isUser ? '내 질문' : 'AI 답변'}>
      <div className="qa-message-bubble">{message.text}</div>
      {!isUser && message.sources && message.sources.length > 0 && (
        <div className="qa-source-list">
          <span className="qa-source-list-label">법령 근거</span>
          {message.sources.map((source, index) => {
            const key = evidenceKey(source)
            return (
              <SourceItem
                key={`${key}-${index}`}
                source={source}
                canSave={Boolean(currentArticleKey)}
                isSaved={evidence.some((item) => evidenceKey(item as QASource) === key)}
                isSaving={savingKey === key}
                onSave={() => onSaveSource(source)}
              />
            )
          })}
        </div>
      )}
      {canApply && currentArticleKey && (
        <button
          type="button"
          className="qa-apply-btn"
          onClick={() => onApply({
            content: applyContent,
            title: 'Q&A 현재 답변',
            targetArticleKey: currentArticleKey,
          })}
        >
          현재 답변을 {currentArticleKey}에 적용
        </button>
      )}
    </article>
  )
}

export default function QAPanel({
  sessionId,
  stage,
  currentArticleKey,
  qaHistory,
  onAddMessages,
  onApplyContent,
  onNewSession,
  fontSize,
  evidenceRefreshKey = 0,
}: Props) {
  const [activeTab, setActiveTab] = useState<'qa' | 'evidence'>('qa')
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [evidence, setEvidence] = useState<EvidenceItem[]>([])
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [evidenceError, setEvidenceError] = useState<string | null>(null)
  const [evidenceLoadVersion, setEvidenceLoadVersion] = useState(0)
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [status, setStatus] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const qaScopeRef = useRef({ sessionId, version: 0 })
  const evidenceScopeRef = useRef(0)

  if (qaScopeRef.current.sessionId !== sessionId) {
    qaScopeRef.current = { sessionId, version: qaScopeRef.current.version + 1 }
  }

  useEffect(() => {
    setIsLoading(false)
    setSavingKey(null)
    setDeletingId(null)
    setActiveTab('qa')
    return () => {
      qaScopeRef.current.version += 1
    }
  }, [sessionId])

  useEffect(() => {
    const version = ++evidenceScopeRef.current
    setEvidence([])
    setEvidenceError(null)
    if (!sessionId) {
      setEvidenceLoading(false)
      return
    }
    setEvidenceLoading(true)
    void listEvidence(sessionId)
      .then((items) => {
        if (evidenceScopeRef.current === version) setEvidence(items)
      })
      .catch((error: unknown) => {
        if (evidenceScopeRef.current === version) {
          setEvidenceError(error instanceof Error ? error.message : '근거 목록을 불러오지 못했습니다.')
        }
      })
      .finally(() => {
        if (evidenceScopeRef.current === version) setEvidenceLoading(false)
      })
  }, [sessionId, evidenceLoadVersion, evidenceRefreshKey])

  useEffect(() => {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    bottomRef.current?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' })
  }, [qaHistory])

  const handleSend = async () => {
    const question = input.trim()
    if (!question || isLoading) return
    const requestVersion = ++qaScopeRef.current.version
    const requestSessionId = sessionId
    const isCurrent = () => qaScopeRef.current.version === requestVersion
      && qaScopeRef.current.sessionId === requestSessionId

    setInput('')
    setIsLoading(true)
    onAddMessages([{ role: 'user', text: question }])
    try {
      const response = requestSessionId
        ? await askQuestion(requestSessionId, question)
        : await searchDirectQuestion(question, { current_article_key: currentArticleKey })
      if (!isCurrent()) return
      onAddMessages([{
        role: 'ai',
        text: response.answer,
        sources: response.sources,
        applicable_content: response.applicable_content,
        applicable_article_key: response.applicable_article_key,
      }])
    } catch (error) {
      if (!isCurrent()) return
      onAddMessages([{ role: 'ai', text: `오류가 발생했습니다: ${error instanceof Error ? error.message : '알 수 없는 오류'}` }])
    } finally {
      if (isCurrent()) setIsLoading(false)
    }
  }

  const handleSaveSource = async (source: QASource) => {
    if (!sessionId || savingKey) return
    const requestSessionId = sessionId
    const version = evidenceScopeRef.current
    const key = evidenceKey(source)
    setSavingKey(key)
    setEvidenceError(null)
    try {
      const saved = await createEvidence(requestSessionId, {
        source_type: source.source_type,
        title: source.title,
        article_no: source.article_no,
        content: source.content,
        relation_type: source.relation_type,
        target_article_key: currentArticleKey,
      })
      if (evidenceScopeRef.current !== version || sessionId !== requestSessionId) return
      setEvidence((items) => items.some((item) => item.id === saved.id) ? items : [saved, ...items])
      setStatus(`${source.title} 근거를 저장했습니다.`)
    } catch (error) {
      if (evidenceScopeRef.current === version) {
        setEvidenceError(error instanceof Error ? error.message : '근거를 저장하지 못했습니다.')
      }
    } finally {
      if (evidenceScopeRef.current === version) setSavingKey(null)
    }
  }

  const handleDelete = async (item: EvidenceItem) => {
    if (!sessionId || deletingId || !window.confirm(`‘${item.title}’ 근거를 삭제하시겠습니까?`)) return
    const requestSessionId = sessionId
    const version = evidenceScopeRef.current
    setDeletingId(item.id)
    setEvidenceError(null)
    try {
      await deleteEvidence(requestSessionId, item.id)
      if (evidenceScopeRef.current !== version || sessionId !== requestSessionId) return
      setEvidence((items) => items.filter((candidate) => candidate.id !== item.id))
      setStatus(`${item.title} 근거를 삭제했습니다.`)
    } catch (error) {
      if (evidenceScopeRef.current === version) {
        setEvidenceError(error instanceof Error ? error.message : '근거를 삭제하지 못했습니다.')
      }
    } finally {
      if (evidenceScopeRef.current === version) setDeletingId(null)
    }
  }

  return (
    <section className="qa-panel" aria-label="Q&A와 근거 라이브러리" style={{ fontSize: `${fontSize}px` }}>
      <div className="qa-panel-tabs" role="tablist" aria-label="오른쪽 패널 보기">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'qa'}
          aria-controls="qa-panel-content"
          className={activeTab === 'qa' ? 'active' : ''}
          onClick={() => setActiveTab('qa')}
        >
          Q&amp;A
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'evidence'}
          aria-controls="evidence-panel-content"
          className={activeTab === 'evidence' ? 'active' : ''}
          onClick={() => setActiveTab('evidence')}
        >
          근거 <span className="qa-tab-count">{evidence.length}</span>
        </button>
      </div>

      <p className="sr-only" role="status" aria-live="polite">{status}</p>

      {activeTab === 'qa' ? (
        <>
          <div
            id="qa-panel-content"
            role="tabpanel"
            className="qa-message-list"
            aria-live="polite"
            aria-busy={isLoading}
          >
            {qaHistory.length === 0 && (
              <div className="qa-empty-state">
                <strong>법령 기반 Q&amp;A</strong>
                <p>법령과 유사 조례를 검색해 조문 작성에 필요한 근거를 확인하세요.</p>
                {!sessionId && onNewSession && <button type="button" onClick={onNewSession}>새 조례 만들기</button>}
              </div>
            )}
            {qaHistory.map((message, index) => (
              <MessageBubble
                key={index}
                message={message}
                stage={stage}
                currentArticleKey={currentArticleKey}
                evidence={evidence}
                savingKey={savingKey}
                onSaveSource={handleSaveSource}
                onApply={onApplyContent}
              />
            ))}
            {isLoading && <p role="status" className="qa-loading-status">답변을 작성하는 중입니다…</p>}
            <div ref={bottomRef} aria-hidden="true" />
          </div>
          <form className="qa-input-area" onSubmit={(event) => { event.preventDefault(); void handleSend() }}>
            <label className="sr-only" htmlFor="qa-input">법령 또는 조례 관련 질문</label>
            <textarea
              id="qa-input"
              className="qa-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void handleSend()
                }
              }}
              placeholder="법령·조례에 관해 질문하세요. (Shift+Enter 줄바꿈)"
              rows={2}
              disabled={isLoading}
            />
            <button type="submit" className="qa-send-btn" disabled={!input.trim() || isLoading}>전송</button>
          </form>
        </>
      ) : (
        <div id="evidence-panel-content" role="tabpanel" className="evidence-panel-content">
          {!sessionId ? (
            <div className="evidence-panel-state">
              <strong>세션을 먼저 시작해 주세요.</strong>
              <p>근거는 현재 조례 작업별로 안전하게 구분해 저장됩니다.</p>
            </div>
          ) : (
            <EvidencePanel
              items={evidence}
              currentArticleKey={currentArticleKey}
              isLoading={evidenceLoading}
              error={evidenceError}
              deletingId={deletingId}
              onRetry={() => setEvidenceLoadVersion((value) => value + 1)}
              onDelete={(item) => void handleDelete(item)}
              onApply={onApplyContent}
            />
          )}
        </div>
      )}
    </section>
  )
}
