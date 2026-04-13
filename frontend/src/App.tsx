import { useState, useRef, useEffect } from 'react'
import type { ChatMessage, LegalIssue, SimilarOrdinance, Stage } from './types'
import { createSession, sendMessage, finalizeSession, getSessionState, submitArticlesBatch } from './api'
import StageIndicator from './components/StageIndicator'
import ChatWindow from './components/ChatWindow'
import DraftModal from './components/DraftModal'
import LegalIssuesPanel from './components/LegalIssuesPanel'
import SimilarOrdinancesPanel from './components/SimilarOrdinancesPanel'
import SessionListScreen from './components/SessionListScreen'
import ArticleItemsModal from './components/ArticleItemsModal'

export default function App() {
  const [view, setView] = useState<'list' | 'chat'>('list')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [stage, setStage] = useState<Stage | null>(null)

  // Draft modal state
  const [pendingDraft, setPendingDraft] = useState<string | null>(null)
  const [isDraftModalOpen, setIsDraftModalOpen] = useState(false)
  const [pendingLegalIssues, setPendingLegalIssues] = useState<LegalIssue[] | null>(null)
  const [isLegallyValid, setIsLegallyValid] = useState<boolean | null>(null)

  // Finalized result state
  const [completedDraft, setCompletedDraft] = useState<string | null>(null)
  const [finalLegalIssues, setFinalLegalIssues] = useState<LegalIssue[] | null>(null)

  // Similar ordinances (shown after retrieving stage)
  const [similarOrdinances, setSimilarOrdinances] = useState<SimilarOrdinance[]>([])

  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'chat' | 'result'>('chat')

  // Article Modal State
  const [articleQueue, setArticleQueue] = useState<string[]>([])
  const [currentArticleKey, setCurrentArticleKey] = useState<string | null>(null)
  const [hideArticleModal, setHideArticleModal] = useState(false)

  const sessionIdRef = useRef<string | null>(null)
  const [fontSize, setFontSize] = useState<number>(16)

  useEffect(() => {
    document.documentElement.style.fontSize = `${fontSize}px`
  }, [fontSize])

  const appendMessage = (msg: ChatMessage) =>
    setMessages((prev) => [...prev, msg])

  const applyResponse = (res: {
    stage: string
    message: string
    draft?: string
    legal_issues?: LegalIssue[]
    is_legally_valid?: boolean | null
    is_complete: boolean
    similar_ordinances?: SimilarOrdinance[]
    article_queue?: string[]
    current_article_key?: string
  }) => {
    setStage(res.stage as Stage)
    appendMessage({ role: 'ai', text: res.message })

    if (res.similar_ordinances && res.similar_ordinances.length > 0) {
      setSimilarOrdinances(res.similar_ordinances)
    }

    if (res.article_queue !== undefined) setArticleQueue(res.article_queue)
    if (res.current_article_key !== undefined) setCurrentArticleKey(res.current_article_key)


    // Draft just generated → open the editor modal
    if (res.stage === 'draft_review' && res.draft) {
      setPendingDraft(res.draft)
      setPendingLegalIssues(null)  // reset issues for new draft
      setIsLegallyValid(null)
      setIsDraftModalOpen(true)
    }

    // Legal check result received → update issues in modal, keep modal open
    if (res.stage === 'legal_checking') {
      if (res.draft) setPendingDraft(res.draft)
      if (res.legal_issues !== undefined) setPendingLegalIssues(res.legal_issues ?? null)
      setIsLegallyValid(res.is_legally_valid ?? null)
      setIsDraftModalOpen(true)  // ensure modal stays open
    }

    // Workflow fully completed (after /finalize)
    if (res.is_complete) {
      if (res.draft) setCompletedDraft(res.draft)
      if (res.legal_issues) setFinalLegalIssues(res.legal_issues)
      setActiveTab('result')
      setIsDraftModalOpen(false)
    }
  }

  const handleSend = async () => {
    const text = input.trim()
    if (!text || isLoading) return

    setInput('')
    setError(null)
    appendMessage({ role: 'user', text })
    setIsLoading(true)

    try {
      if (!sessionIdRef.current) {
        const res = await createSession(text)
        sessionIdRef.current = res.session_id
        applyResponse({ ...res, is_complete: false })
      } else {
        const res = await sendMessage(sessionIdRef.current, text)
        applyResponse(res)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleLegalReview = async (editedDraft: string) => {
    if (!sessionIdRef.current || isLoading) return

    setError(null)
    appendMessage({ role: 'user', text: '법률 검증을 요청합니다.' })
    setIsLoading(true)

    try {
      const res = await sendMessage(sessionIdRef.current, '법률 검증을 요청합니다.', editedDraft)
      applyResponse(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleFinalize = async (finalDraft: string) => {
    if (!sessionIdRef.current || isLoading) return

    setError(null)
    setIsLoading(true)

    try {
      const res = await finalizeSession(sessionIdRef.current, finalDraft)
      setCompletedDraft(res.draft)
      setFinalLegalIssues(res.legal_issues?.length ? res.legal_issues : null)
      setIsDraftModalOpen(false)
      setStage('completed')
      appendMessage({ role: 'ai', text: '조례 초안이 확정되었습니다.' })
      setActiveTab('result')
    } catch (e) {
      setError(e instanceof Error ? e.message : '확정 중 오류가 발생했습니다.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const resetState = () => {
    sessionIdRef.current = null
    setMessages([])
    setStage(null)
    setPendingDraft(null)
    setIsDraftModalOpen(false)
    setPendingLegalIssues(null)
    setIsLegallyValid(null)
    setCompletedDraft(null)
    setFinalLegalIssues(null)
    setSimilarOrdinances([])
    setArticleQueue([])
    setCurrentArticleKey(null)
    setHideArticleModal(false)
    setError(null)
    setInput('')
    setActiveTab('chat')
  }

  const handleReset = () => {
    resetState()
    setView('list')
  }

  const handleNewSession = () => {
    resetState()
    setView('chat')
  }

  const handleSelectSession = async (sessionId: string) => {
    setError(null)
    try {
      const state = await getSessionState(sessionId)
      resetState()
      sessionIdRef.current = state.session_id
      setMessages(state.messages)
      setStage(state.stage as Stage)

      if (state.similar_ordinances && state.similar_ordinances.length > 0) {
        setSimilarOrdinances(state.similar_ordinances)
      }
      if (state.article_queue !== undefined) setArticleQueue(state.article_queue)
      if (state.current_article_key !== undefined) setCurrentArticleKey(state.current_article_key)

      if (state.stage === 'completed') {
        if (state.draft) setCompletedDraft(state.draft)
        if (state.legal_issues && state.legal_issues.length > 0) {
          setFinalLegalIssues(state.legal_issues)
        }
        setActiveTab('result')
      } else if (state.draft) {
        setPendingDraft(state.draft)
        if (state.legal_issues) setPendingLegalIssues(state.legal_issues)
        if (state.stage === 'draft_review' || state.stage === 'legal_checking') {
          setIsDraftModalOpen(true)
        }
      }

      setView('chat')
    } catch (e) {
      setError(e instanceof Error ? e.message : '세션을 불러오지 못했습니다.')
    }
  }

  const handleArticlesSubmit = async (articles: Record<string, string | null>) => {
    if (!sessionIdRef.current || isLoading) return
    setError(null)
    setIsLoading(true)
    try {
      const res = await submitArticlesBatch(sessionIdRef.current, articles)
      applyResponse(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : '항목 전송에 실패했습니다.')
    } finally {
      setIsLoading(false)
    }
  }

  const hasResult = !!(completedDraft || finalLegalIssues)

  const mappedArticles = currentArticleKey ? [currentArticleKey, ...articleQueue] : []
  const isArticleModalOpen = stage === 'article_interviewing' && mappedArticles.length > 0

  if (view === 'list') {
    return (
      <SessionListScreen
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
      />
    )
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <h1 className="app-title">조례 빌더 AI</h1>
          <span className="app-subtitle">지방 조례 초안 자동 생성 서비스</span>
        </div>
        <StageIndicator stage={stage} />
        <div className="header-actions">
          <div className="font-size-slider" style={{ display: 'flex', gap: '8px', alignItems: 'center', marginRight: '8px' }}>
            <span style={{ fontSize: '0.85rem', opacity: 0.9 }}>글씨 크기</span>
            <input 
              type="range" 
              min="12" 
              max="24" 
              value={fontSize} 
              onChange={(e) => setFontSize(Number(e.target.value))} 
              style={{ width: '80px', accentColor: '#ffffff' }}
              title="글씨 크기 조절"
            />
          </div>
          {isArticleModalOpen && hideArticleModal && (
            <button className="open-draft-btn" onClick={() => setHideArticleModal(false)}>
              항목 입력하기
            </button>
          )}
          {pendingDraft && !isDraftModalOpen && stage !== 'completed' && (
            <button className="open-draft-btn" onClick={() => setIsDraftModalOpen(true)}>
              초안 편집 · 검증
            </button>
          )}
          <button className="reset-btn" onClick={handleReset}>목록</button>
        </div>
      </header>

      <main className="app-main">
        {hasResult && (
          <div className="mobile-tabs">
            <button
              className={`mobile-tab ${activeTab === 'chat' ? 'active' : ''}`}
              onClick={() => setActiveTab('chat')}
            >
              💬 채팅
            </button>
            <button
              className={`mobile-tab ${activeTab === 'result' ? 'active' : ''}`}
              onClick={() => setActiveTab('result')}
            >
              📄 확정 초안
            </button>
          </div>
        )}

        <div className={`chat-area ${hasResult && activeTab !== 'chat' ? 'mobile-hidden' : ''}`}>
          <ChatWindow messages={messages} isLoading={isLoading} />

          {similarOrdinances.length > 0 && (
            <SimilarOrdinancesPanel ordinances={similarOrdinances} />
          )}

          {error && (
            <div className="error-bar">
              ⚠️ {error}
              <button onClick={() => setError(null)}>✕</button>
            </div>
          )}

          <div className="input-area">
            <textarea
              className="message-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isArticleModalOpen ? "상세 항목 모달에서 입력을 완료해 주세요." : "메시지를 입력하세요... (Shift+Enter로 줄바꿈)"}
              rows={2}
              disabled={isLoading || isArticleModalOpen}
            />
            <button
              className="send-btn"
              onClick={handleSend}
              disabled={!input.trim() || isLoading || isArticleModalOpen}
            >
              전송
            </button>
          </div>
        </div>

        {hasResult && (
          <div className={`result-area ${activeTab !== 'result' ? 'mobile-hidden' : ''}`}>
            {completedDraft && (
              <div className="draft-panel">
                <div className="panel-header">
                  <h3>확정 조례 초안</h3>
                  <button
                    className="copy-btn"
                    onClick={() => navigator.clipboard.writeText(completedDraft)}
                  >
                    복사
                  </button>
                </div>
                <pre className="draft-text">{completedDraft}</pre>
              </div>
            )}
            {finalLegalIssues && <LegalIssuesPanel issues={finalLegalIssues} />}
          </div>
        )}
      </main>

      {isDraftModalOpen && pendingDraft && (
        <DraftModal
          draft={pendingDraft}
          isLoading={isLoading}
          legalIssues={pendingLegalIssues}
          isLegallyValid={isLegallyValid}
          onRequestLegalReview={handleLegalReview}
          onFinalize={handleFinalize}
          onClose={() => setIsDraftModalOpen(false)}
        />
      )}

      {isArticleModalOpen && !hideArticleModal && (
        <ArticleItemsModal
          articles={mappedArticles}
          isLoading={isLoading}
          onSubmit={handleArticlesSubmit}
          onClose={() => setHideArticleModal(true)}
        />
      )}
    </div>
  )
}
