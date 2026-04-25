import { useState, useRef, useEffect } from 'react'
import type { ChatMessage, LegalIssue, QAMessage, SimilarOrdinance, Stage, SuggestedOption } from './types'
import { createSession, sendMessage, finalizeSession, getSessionState, submitArticlesBatch } from './api'
import { auth, loginWithGoogle, logout, onAuthStateChanged, getRedirectResult } from './firebase'
import type { User } from './firebase'
import StageIndicator from './components/StageIndicator'
import ChatWindow from './components/ChatWindow'
import DraftModal from './components/DraftModal'
import SimilarOrdinancesPanel from './components/SimilarOrdinancesPanel'
import SessionListScreen from './components/SessionListScreen'
import ArticleItemsModal from './components/ArticleItemsModal'
import LoadingModal from './components/LoadingModal'
import CompletedDraftModal from './components/CompletedDraftModal'
import QAPanel from './components/QAPanel'
import OnboardingWizard from './components/OnboardingWizard'

export default function App() {
  // ── 인증 상태 ──────────────────────────────────────────────────────────────
  const [user, setUser] = useState<User | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [authError, setAuthError] = useState<string | null>(null)

  useEffect(() => {
    getRedirectResult(auth)
      .then((result) => {
        if (result?.user) setUser(result.user)
      })
      .catch((e: unknown) => {
        const code = (e as { code?: string }).code ?? 'unknown'
        const msg = (e as { message?: string }).message ?? String(e)
        console.error('redirect auth error:', e)
        setAuthError(`로그인 실패 [${code}]: ${msg}`)
      })
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser)
      setAuthLoading(false)
    })
    return unsubscribe
  }, [])

  const handleLogin = async () => {
    setAuthError(null)
    try {
      await loginWithGoogle()
    } catch (e: unknown) {
      const code = (e as { code?: string }).code ?? 'unknown'
      const msg = (e as { message?: string }).message ?? String(e)
      console.error('로그인 실패:', e)
      setAuthError(`로그인 시작 실패 [${code}]: ${msg}`)
    }
  }

  const handleLogout = async () => {
    await logout()
    resetState()
    setView('list')
  }
  // ──────────────────────────────────────────────────────────────────────────

  const [view, setView] = useState<'list' | 'chat'>('list')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [loadingMessage, setLoadingMessage] = useState<string | null>(null)
  const [stage, setStage] = useState<Stage | null>(null)

  // Draft modal state
  const [pendingDraft, setPendingDraft] = useState<string | null>(null)
  const [isDraftModalOpen, setIsDraftModalOpen] = useState(false)
  const [pendingLegalIssues, setPendingLegalIssues] = useState<LegalIssue[] | null>(null)
  const [isLegallyValid, setIsLegallyValid] = useState<boolean | null>(null)

  // Finalized result state
  const [completedDraft, setCompletedDraft] = useState<string | null>(null)
  const [finalLegalIssues, setFinalLegalIssues] = useState<LegalIssue[] | null>(null)
  const [isCompletedDraftModalOpen, setIsCompletedDraftModalOpen] = useState(false)

  // Similar ordinances (shown after retrieving stage)
  const [similarOrdinances, setSimilarOrdinances] = useState<SimilarOrdinance[]>([])

  const [error, setError] = useState<string | null>(null)
  // Article Modal State
  const [articleQueue, setArticleQueue] = useState<string[]>([])
  const [currentArticleKey, setCurrentArticleKey] = useState<string | null>(null)
  const [hideArticleModal, setHideArticleModal] = useState(false)
  // QA Panel State
  const [isQAPanelOpen, setIsQAPanelOpen] = useState(false)
  const [qaHistory, setQaHistory] = useState<QAMessage[]>([])
  const [pendingQAContent, setPendingQAContent] = useState<string | null>(null)
  const [hasSession, setHasSession] = useState(false)
  const [ordinanceType, setOrdinanceType] = useState<string | null>(null)

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
    current_article_key?: string | null
    suggested_options?: SuggestedOption[]
    ordinance_type?: string | null
  }) => {
    setStage(res.stage as Stage)
    appendMessage({ role: 'ai', text: res.message, suggested_options: res.suggested_options })

    if (res.similar_ordinances && res.similar_ordinances.length > 0) {
      setSimilarOrdinances(res.similar_ordinances)
    }

    if (res.article_queue != null) setArticleQueue(res.article_queue)
    if (res.current_article_key !== undefined) setCurrentArticleKey(res.current_article_key)
    if (res.ordinance_type != null) setOrdinanceType(res.ordinance_type)

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
      setIsDraftModalOpen(false)
      setIsCompletedDraftModalOpen(true)
    }
  }

  const sendText = async (text: string) => {
    if (!text.trim() || isLoading) return
    setError(null)
    appendMessage({ role: 'user', text })
    setIsLoading(true)
    setLoadingMessage(sessionIdRef.current ? 'AI가 응답을 준비 중입니다...' : '기본 정보를 분석하고 있습니다...')
    try {
      if (!sessionIdRef.current) {
        const res = await createSession(text)
        sessionIdRef.current = res.session_id
        setHasSession(true)
        applyResponse({ ...res, is_complete: false })
      } else {
        const res = await sendMessage(sessionIdRef.current, text)
        applyResponse(res)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      setIsLoading(false)
      setLoadingMessage(null)
    }
  }

  const handleSend = async () => {
    const text = input.trim()
    if (!text) return
    setInput('')
    await sendText(text)
  }

  const handleOptionSelect = (value: string) => {
    if (isLoading || isArticleModalOpen) return
    setInput('')
    sendText(value)
  }

  const handleLegalReview = async (editedDraft: string) => {
    if (!sessionIdRef.current || isLoading) return

    setError(null)
    appendMessage({ role: 'user', text: '법률 검증을 요청합니다.' })
    setIsLoading(true)
    setLoadingMessage('법률 조항을 검증하고 있습니다...')

    try {
      const res = await sendMessage(sessionIdRef.current, '법률 검증을 요청합니다.', editedDraft)
      applyResponse(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      setIsLoading(false)
      setLoadingMessage(null)
    }
  }

  const handleFinalize = async (finalDraft: string) => {
    if (!sessionIdRef.current || isLoading) return

    setError(null)
    setIsLoading(true)
    setLoadingMessage('조례 초안을 확정하는 중입니다...')

    try {
      const res = await finalizeSession(sessionIdRef.current, finalDraft)
      setCompletedDraft(res.draft)
      setFinalLegalIssues(res.legal_issues?.length ? res.legal_issues : null)
      setIsDraftModalOpen(false)
      setStage('completed')
      appendMessage({ role: 'ai', text: '조례 초안이 확정되었습니다.' })
      setIsCompletedDraftModalOpen(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : '확정 중 오류가 발생했습니다.')
    } finally {
      setIsLoading(false)
      setLoadingMessage(null)
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
    setIsCompletedDraftModalOpen(false)
    setSimilarOrdinances([])
    setArticleQueue([])
    setCurrentArticleKey(null)
    setHideArticleModal(false)
    setIsQAPanelOpen(false)
    setQaHistory([])
    setPendingQAContent(null)
    setHasSession(false)
    setOrdinanceType(null)
    setError(null)
    setInput('')
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
      setHasSession(true)
      setMessages(state.messages)
      setStage(state.stage as Stage)

      if (state.similar_ordinances && state.similar_ordinances.length > 0) {
        setSimilarOrdinances(state.similar_ordinances)
      }
      if (state.article_queue != null) setArticleQueue(state.article_queue)
      if (state.current_article_key !== undefined) setCurrentArticleKey(state.current_article_key)
      if (state.ordinance_type != null) setOrdinanceType(state.ordinance_type)

      if (state.stage === 'completed') {
        if (state.draft) setCompletedDraft(state.draft)
        if (state.legal_issues && state.legal_issues.length > 0) {
          setFinalLegalIssues(state.legal_issues)
        }
        setIsCompletedDraftModalOpen(true)
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
    setLoadingMessage('조례 초안을 생성하고 있습니다...')
    try {
      const res = await submitArticlesBatch(sessionIdRef.current, articles)
      applyResponse(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : '항목 전송에 실패했습니다.')
    } finally {
      setIsLoading(false)
      setLoadingMessage(null)
    }
  }

  const mappedArticles = currentArticleKey ? [currentArticleKey, ...articleQueue] : []
  const isArticleModalOpen = stage === 'article_interviewing' && mappedArticles.length > 0

  // ── 인증 게이트 ────────────────────────────────────────────────────────────
  if (authLoading) {
    return (
      <div style={loginPageStyle}>
        <p style={{ color: '#6b7280', fontSize: '1rem' }}>인증 확인 중...</p>
      </div>
    )
  }

  if (!user) {
    const inApp = isInAppBrowser()
    return (
      <div style={loginPageStyle}>
        <div style={loginCardStyle}>
          <h1 style={{ margin: '0 0 4px', fontSize: '1.6rem', fontWeight: 700, color: '#1e293b' }}>
            조례 빌더 AI
          </h1>
          <p style={{ margin: '0 0 32px', color: '#64748b', fontSize: '0.95rem' }}>
            지방 조례 초안 자동 생성 서비스
          </p>
          {inApp ? <InAppBrowserWarning /> : (
            <>
              <button onClick={handleLogin} style={googleBtnStyle}>
                <GoogleIcon />
                Google 계정으로 로그인
              </button>
              {authError && (
                <div style={{ marginTop: '16px', padding: '10px 14px', background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: '8px', color: '#dc2626', fontSize: '0.82rem', wordBreak: 'break-all', textAlign: 'left' }}>
                  {authError}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    )
  }
  // ──────────────────────────────────────────────────────────────────────────

  if (view === 'list') {
    return (
      <SessionListScreen
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        user={user}
        onLogout={handleLogout}
      />
    )
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <h1 className="app-title">조례 빌더 AI</h1>
          <span className="app-subtitle">지방 조례 초안 자동 생성 서비스</span>
          <div className="font-size-slider" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <span style={{ fontSize: '0.85em', opacity: 0.9 }}>폰트 크기</span>
            <input
              type="range"
              min="12"
              max="24"
              step="0.5"
              value={fontSize}
              onChange={(e) => setFontSize(Number(e.target.value))}
              style={{ width: '120px', accentColor: '#ffffff' }}
              title="폰트 크기"
            />
          </div>
        </div>
        <StageIndicator stage={stage} />
        {ordinanceType && (
          <span style={{
            padding: '3px 10px',
            background: 'rgba(255,255,255,0.15)',
            border: '1px solid rgba(255,255,255,0.3)',
            borderRadius: '12px',
            fontSize: '0.78rem',
            fontWeight: 600,
            color: '#ffffff',
            whiteSpace: 'nowrap',
          }}>
            {ordinanceType} 조례
          </span>
        )}
        <div className="header-actions">
          {isArticleModalOpen && hideArticleModal && (
            <button className="open-draft-btn" onClick={() => setHideArticleModal(false)}>
              상세 조항 편집
            </button>
          )}
          {pendingDraft && !isDraftModalOpen && stage !== 'completed' && (
            <button className="open-draft-btn" onClick={() => setIsDraftModalOpen(true)}>
              초안 편집 · 검증
            </button>
          )}
          {completedDraft && !isCompletedDraftModalOpen && (
            <button className="open-draft-btn" style={{ background: '#16a34a' }} onClick={() => setIsCompletedDraftModalOpen(true)}>
              확정 초안 보기
            </button>
          )}
          {hasSession && (
            <button
              onClick={() => setIsQAPanelOpen(true)}
              title="법령 Q&A 패널 열기"
              style={{ padding: '6px 14px', background: '#0f766e', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600, whiteSpace: 'nowrap' }}
            >
              🔍 질문
            </button>
          )}
          <button className="reset-btn" onClick={handleReset}>목록</button>
          <div style={userInfoStyle}>
            {user.photoURL && (
              <img src={user.photoURL} alt="프로필" style={avatarStyle} referrerPolicy="no-referrer" />
            )}
            <span style={{ fontSize: '0.85rem', opacity: 0.9, maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user.displayName || user.email}
            </span>
            <button className="reset-btn" onClick={handleLogout} style={{ marginLeft: '4px' }}>
              로그아웃
            </button>
          </div>
        </div>
      </header>

      <main className="app-main">
        <div className="chat-area">
          {messages.length === 0 && !isLoading && !hasSession ? (
            <OnboardingWizard onStart={sendText} isLoading={isLoading} />
          ) : (
          <ChatWindow messages={messages} isLoading={isLoading} onOptionSelect={handleOptionSelect} />
          )}

          {similarOrdinances.length > 0 && (
            <SimilarOrdinancesPanel ordinances={similarOrdinances} />
          )}

          {error && (
            <div className="error-bar">
              ⚠️ {error}
              <button onClick={() => setError(null)}>✕</button>
            </div>
          )}

          {!hasSession && messages.length === 0 && !isLoading ? null : isArticleModalOpen && hideArticleModal ? (
            <div className="input-area" style={{ justifyContent: 'center', background: '#f8fafc', padding: '20px' }}>
              <button
                onClick={() => setHideArticleModal(false)}
                style={{ padding: '14px 28px', background: '#1e40af', color: 'white', borderRadius: '12px', fontSize: '1rem', fontWeight: 700, border: 'none', cursor: 'pointer', boxShadow: '0 4px 12px rgba(30, 64, 175, 0.3)', transition: 'transform 0.1s' }}
                onMouseOver={(e) => e.currentTarget.style.transform = 'scale(1.02)'}
                onMouseOut={(e) => e.currentTarget.style.transform = 'scale(1)'}
              >
                👉 상세 조항 계속 작성하기 (모달 열기)
              </button>
            </div>
          ) : (
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
          )}
        </div>

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
          fontSize={fontSize}
          onFontSizeChange={setFontSize}
          similarOrdinances={similarOrdinances}
          pendingQAContent={pendingQAContent}
          onQAContentApplied={() => setPendingQAContent(null)}
          onOpenQA={() => setIsQAPanelOpen(true)}
        />
      )}

      <QAPanel
        isOpen={isQAPanelOpen}
        onClose={() => setIsQAPanelOpen(false)}
        sessionId={sessionIdRef.current}
        stage={stage}
        currentArticleKey={currentArticleKey}
        qaHistory={qaHistory}
        onAddMessages={(msgs) => setQaHistory((prev) => [...prev, ...msgs])}
        onApplyContent={(content) => {
          setPendingQAContent(content)
          setIsQAPanelOpen(false)
          if (isArticleModalOpen && hideArticleModal) setHideArticleModal(false)
        }}
        fontSize={fontSize}
      />

      {isCompletedDraftModalOpen && completedDraft && (
        <CompletedDraftModal
          draft={completedDraft}
          legalIssues={finalLegalIssues}
          onClose={() => setIsCompletedDraftModalOpen(false)}
        />
      )}

      {isLoading && loadingMessage && <LoadingModal message={loadingMessage} />}
    </div>
  )
}

// ── 로그인 페이지 스타일 ────────────────────────────────────────────────────
const loginPageStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  minHeight: '100vh',
  background: 'linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%)',
}

const loginCardStyle: React.CSSProperties = {
  background: '#ffffff',
  borderRadius: '16px',
  padding: '48px 40px',
  textAlign: 'center',
  boxShadow: '0 20px 60px rgba(0, 0, 0, 0.2)',
  minWidth: '320px',
}

const googleBtnStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '10px',
  padding: '12px 24px',
  background: '#ffffff',
  border: '1.5px solid #d1d5db',
  borderRadius: '8px',
  fontSize: '0.95rem',
  fontWeight: 600,
  color: '#374151',
  cursor: 'pointer',
  boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
  transition: 'box-shadow 0.15s, transform 0.1s',
}

// ── 헤더 사용자 정보 스타일 ────────────────────────────────────────────────
const userInfoStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '8px',
  marginLeft: '8px',
}

const avatarStyle: React.CSSProperties = {
  width: '28px',
  height: '28px',
  borderRadius: '50%',
  border: '2px solid rgba(255,255,255,0.6)',
}

// ── 인앱 브라우저 감지 ────────────────────────────────────────────────────
// Google OAuth는 WebView/인앱 브라우저에서 disallowed_useragent(403)를 반환한다.
// (카카오톡·라인·네이버·인스타그램 등 앱 내 링크 열기 시 발생)
function isInAppBrowser(): boolean {
  const ua = navigator.userAgent
  return (
    /wv/.test(ua) ||             // Android WebView (chrome custom tab 아닌 경우)
    /KAKAOTALK/i.test(ua) ||
    /Line\//i.test(ua) ||
    /NAVER/i.test(ua) ||
    /Instagram/i.test(ua) ||
    /FBAN|FBAV/i.test(ua) ||     // Facebook
    /Twitter/i.test(ua) ||
    /MicroMessenger/i.test(ua)   // WeChat
  )
}

function InAppBrowserWarning() {
  const url = window.location.href
  const isAndroid = /Android/i.test(navigator.userAgent)

  const handleOpenChrome = () => {
    // Android intent scheme으로 Chrome 강제 실행
    window.location.href =
      `intent://${url.replace(/^https?:\/\//, '')}#Intent;scheme=https;package=com.android.chrome;end`
  }

  const handleCopyUrl = () => {
    navigator.clipboard.writeText(url).catch(() => {})
  }

  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: '2.2rem', marginBottom: '12px' }}>⚠️</div>
      <p style={{ fontWeight: 700, fontSize: '1rem', color: '#111827', margin: '0 0 8px' }}>
        앱 내 브라우저에서는 Google 로그인이 차단됩니다
      </p>
      <p style={{ fontSize: '0.82rem', color: '#6b7280', margin: '0 0 24px', lineHeight: '1.7' }}>
        카카오톡·라인 등 앱에서 링크를 열면<br />
        Google 보안 정책으로 로그인이 거부됩니다.<br />
        <strong>Chrome 또는 Safari</strong>에서 직접 열어주세요.
      </p>
      {isAndroid ? (
        <button
          onClick={handleOpenChrome}
          style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '12px 24px', background: '#1967d2', color: '#fff', border: 'none', borderRadius: '8px', fontSize: '0.95rem', fontWeight: 600, cursor: 'pointer', marginBottom: '12px' }}
        >
          Chrome으로 열기
        </button>
      ) : (
        <p style={{ fontSize: '0.875rem', color: '#374151', fontWeight: 600, marginBottom: '12px' }}>
          Safari 브라우저에서 직접 접속해 주세요
        </p>
      )}
      <br />
      <button
        onClick={handleCopyUrl}
        style={{ padding: '8px 16px', background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: '6px', fontSize: '0.8rem', color: '#4b5563', cursor: 'pointer' }}
      >
        주소 복사
      </button>
      <p style={{ fontSize: '0.7rem', color: '#9ca3af', marginTop: '10px', wordBreak: 'break-all' }}>
        {url}
      </p>
    </div>
  )
}

// ── Google 아이콘 SVG ──────────────────────────────────────────────────────
function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
    </svg>
  )
}
