import { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import type { CSSProperties } from 'react'
import type { EvidenceApplyRequest, LegalIssue, QAMessage, SimilarOrdinance, Stage } from './types'
import { createSession, sendMessage, finalizeSession, getSessionState, markEvidenceApplied, submitArticlesBatch } from './api'
import { auth, loginWithGoogle, logout, onAuthStateChanged, getRedirectResult } from './firebase'
import type { User } from './firebase'
import DraftModal from './components/DraftModal'
import SessionListScreen from './components/SessionListScreen'
import ArticleItemsModal from './components/ArticleItemsModal'
import LoadingModal from './components/LoadingModal'
import CompletedDraftModal from './components/CompletedDraftModal'
import QAPanel from './components/QAPanel'
import OnboardingWizard from './components/OnboardingWizard'
import TutorialOverlay, { TUTORIAL_STEP_COUNT } from './components/TutorialOverlay'
import ModelStatus from './components/ModelStatus'
import WorkspaceHeader from './components/WorkspaceHeader'

type AppRoute =
  | { kind: 'list' }
  | { kind: 'new' }
  | { kind: 'session'; sessionId: string }

function readRoute(pathname = window.location.pathname): AppRoute {
  if (pathname === '/' || pathname === '') return { kind: 'list' }
  if (pathname === '/sessions/new' || pathname === '/sessions/new/') return { kind: 'new' }

  const match = pathname.match(/^\/sessions\/([^/]+)\/?$/)
  if (match) {
    try {
      return { kind: 'session', sessionId: decodeURIComponent(match[1]) }
    } catch {
      return { kind: 'list' }
    }
  }

  return { kind: 'list' }
}

export default function App() {
  const [route, setRoute] = useState<AppRoute>(() => readRoute())
  const routeRef = useRef<AppRoute>(route)
  const requestGenerationRef = useRef(0)
  const sessionLoadIdRef = useRef(0)

  const navigate = useCallback((path: string, options?: { replace?: boolean }) => {
    const method = options?.replace ? 'replaceState' : 'pushState'
    window.history[method](null, '', path)
    const nextRoute = readRoute(path)
    requestGenerationRef.current += 1
    routeRef.current = nextRoute
    setRoute(nextRoute)
  }, [])

  useEffect(() => {
    const handlePopState = () => {
      const nextRoute = readRoute()
      requestGenerationRef.current += 1
      routeRef.current = nextRoute
      setRoute(nextRoute)
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    if (route.kind === 'list' && window.location.pathname !== '/') {
      window.history.replaceState(null, '', '/')
    }
  }, [route])

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
    navigate('/', { replace: true })
  }
  // ──────────────────────────────────────────────────────────────────────────

  const [isOnboardingOpen, setIsOnboardingOpen] = useState(false)
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
  const [qaHistory, setQaHistory] = useState<QAMessage[]>([])
  const [pendingApplication, setPendingApplication] = useState<EvidenceApplyRequest | null>(null)
  const [evidenceRefreshKey, setEvidenceRefreshKey] = useState(0)
  const [hasSession, setHasSession] = useState(false)
  const [ordinanceType, setOrdinanceType] = useState<string | null>(null)
  const [workspaceTab, setWorkspaceTab] = useState<'articles' | 'draft'>('articles')

  // Tutorial state
  const [tutorialStep, setTutorialStep] = useState(-1)   // -1 = inactive, 0~4 = active step
  const TUTORIAL_KEY = 'ordinance_tutorial_completed'

  const getInitialTutorialStep = () => {
    if (stage === 'completed') return 4
    if (stage === 'draft_review' || stage === 'legal_review_requested' || stage === 'legal_checking') return 3
    if (stage === 'article_interviewing' || stage === 'article_complete' || stage === 'drafting') return 2
    if (isOnboardingOpen) return 1
    return 0
  }

  const sessionIdRef = useRef<string | null>(null)
  const [fontSize, setFontSize] = useState<number>(() => {
    const saved = Number(localStorage.getItem('ordinance_workspace_font_size'))
    return saved >= 12 && saved <= 24 ? saved : 16
  })
  const handleFontSizeCommit = useCallback((value: number) => {
    setFontSize(value)
    localStorage.setItem('ordinance_workspace_font_size', String(value))
  }, [])
  const workspaceRef = useRef<HTMLElement>(null)
  const handleFontSizePreview = useCallback((value: number) => {
    workspaceRef.current?.style.setProperty('--workspace-font-size', `${value}px`)
  }, [])

  // Auto-trigger tutorial on first login
  useEffect(() => {
    if (user && !localStorage.getItem(TUTORIAL_KEY)) {
      setTutorialStep(0)
    }
  }, [user])  // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-advance tutorial steps based on app state
  useEffect(() => {
    if (tutorialStep < 0) return
    if (tutorialStep === 0 && isOnboardingOpen) { setTutorialStep(1); return }
    if (tutorialStep === 1 && !isOnboardingOpen && stage === 'article_interviewing') { setTutorialStep(2); return }
    if (tutorialStep === 2 && stage === 'draft_review') { setTutorialStep(3); return }
    if (tutorialStep === 3 && stage === 'completed') { setTutorialStep(4); return }
  }, [tutorialStep, isOnboardingOpen, stage])

  const handleTutorialNext = () => {
    if (tutorialStep >= TUTORIAL_STEP_COUNT - 1) {
      setTutorialStep(-1)
      localStorage.setItem(TUTORIAL_KEY, 'true')
    }
  }

  const handleTutorialPrev = () => {
    setTutorialStep(s => Math.max(0, s - 1))
  }

  const handleTutorialSkip = () => {
    setTutorialStep(-1)
    localStorage.setItem(TUTORIAL_KEY, 'true')
  }

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
    ordinance_type?: string | null
  }) => {
    setStage(res.stage as Stage)

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
      setWorkspaceTab('draft')
    }

    // Legal check result received → update issues in modal, keep modal open
    if (res.stage === 'legal_checking') {
      if (res.draft) setPendingDraft(res.draft)
      if (res.legal_issues !== undefined) setPendingLegalIssues(res.legal_issues ?? null)
      setIsLegallyValid(res.is_legally_valid ?? null)
      setIsDraftModalOpen(true)  // ensure modal stays open
      setWorkspaceTab('draft')
    }

    // Workflow fully completed (after /finalize)
    if (res.is_complete) {
      if (res.draft) setCompletedDraft(res.draft)
      if (res.legal_issues) setFinalLegalIssues(res.legal_issues)
      setIsDraftModalOpen(false)
      setIsCompletedDraftModalOpen(true)
    }
  }

  const handleWizardStart = async (message: string, ordinanceType: string) => {
    const requestGeneration = requestGenerationRef.current
    setIsOnboardingOpen(false)
    setIsLoading(true)
    setLoadingMessage('기본 정보를 분석하고 있습니다...')
    try {
      const res = await createSession(message, ordinanceType)
      if (requestGenerationRef.current !== requestGeneration || routeRef.current.kind !== 'new') return
      sessionIdRef.current = res.session_id
      setHasSession(true)
      applyResponse({ ...res, is_complete: false })
      navigate(`/sessions/${encodeURIComponent(res.session_id)}`, { replace: true })
    } catch (e) {
      if (requestGenerationRef.current !== requestGeneration || routeRef.current.kind !== 'new') return
      setError(e instanceof Error ? e.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      if (requestGenerationRef.current !== requestGeneration || routeRef.current.kind !== 'new') return
      setIsLoading(false)
      setLoadingMessage(null)
    }
  }

  const handleLegalReview = async (editedDraft: string) => {
    if (!sessionIdRef.current || isLoading) return

    const requestGeneration = requestGenerationRef.current
    const requestSessionId = sessionIdRef.current
    setError(null)
    setIsLoading(true)
    setLoadingMessage('법률 조항을 검증하고 있습니다...')

    try {
      const res = await sendMessage(requestSessionId, '법률 검증을 요청합니다.', editedDraft)
      if (
        requestGenerationRef.current !== requestGeneration ||
        routeRef.current.kind !== 'session' ||
        routeRef.current.sessionId !== requestSessionId
      ) return
      applyResponse(res)
    } catch (e) {
      if (requestGenerationRef.current !== requestGeneration) return
      setError(e instanceof Error ? e.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      if (requestGenerationRef.current !== requestGeneration) return
      setIsLoading(false)
      setLoadingMessage(null)
    }
  }

  const handleFinalize = async (finalDraft: string) => {
    if (!sessionIdRef.current || isLoading) return

    const requestGeneration = requestGenerationRef.current
    const requestSessionId = sessionIdRef.current
    setError(null)
    setIsLoading(true)
    setLoadingMessage('조례 초안을 확정하는 중입니다...')

    try {
      const res = await finalizeSession(requestSessionId, finalDraft)
      if (
        requestGenerationRef.current !== requestGeneration ||
        routeRef.current.kind !== 'session' ||
        routeRef.current.sessionId !== requestSessionId
      ) return
      setCompletedDraft(res.draft)
      setFinalLegalIssues(res.legal_issues?.length ? res.legal_issues : null)
      setIsDraftModalOpen(false)
      setStage('completed')
      setIsCompletedDraftModalOpen(true)
    } catch (e) {
      if (requestGenerationRef.current !== requestGeneration) return
      setError(e instanceof Error ? e.message : '확정 중 오류가 발생했습니다.')
    } finally {
      if (requestGenerationRef.current !== requestGeneration) return
      setIsLoading(false)
      setLoadingMessage(null)
    }
  }

  const resetState = () => {
    sessionIdRef.current = null
    setIsLoading(false)
    setLoadingMessage(null)
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
    setQaHistory([])
    setPendingApplication(null)
    setHasSession(false)
    setOrdinanceType(null)
    setError(null)
  }

  const handleReset = () => {
    resetState()
    navigate('/')
  }

  const handleNewSession = () => {
    navigate('/sessions/new')
  }

  const handleOpenQAFromArticleModal = () => {
    setHideArticleModal(true)
    window.setTimeout(() => {
      document.getElementById('qa-input')?.focus()
    }, 0)
  }

  const handleSelectSession = (sessionId: string) => {
    navigate(`/sessions/${encodeURIComponent(sessionId)}`)
  }

  useEffect(() => {
    if (!user) return

    const loadId = ++sessionLoadIdRef.current
    if (route.kind === 'list') {
      resetState()
      setIsOnboardingOpen(false)
      return
    }
    if (route.kind === 'new') {
      resetState()
      setIsOnboardingOpen(true)
      return
    }

    resetState()
    setIsOnboardingOpen(false)
    setIsLoading(true)
    setLoadingMessage('작업 내용을 불러오고 있습니다...')

    getSessionState(route.sessionId)
      .then((state) => {
        if (sessionLoadIdRef.current !== loadId) return
        sessionIdRef.current = state.session_id
        setHasSession(true)
        setStage(state.stage as Stage)

        if (state.similar_ordinances?.length) setSimilarOrdinances(state.similar_ordinances)
        if (state.article_queue != null) setArticleQueue(state.article_queue)
        if (state.current_article_key !== undefined) setCurrentArticleKey(state.current_article_key)
        if (state.ordinance_type != null) setOrdinanceType(state.ordinance_type)
        if (state.qa_history != null) setQaHistory(state.qa_history)

        if (state.stage === 'completed') {
          if (state.draft) setCompletedDraft(state.draft)
          if (state.legal_issues?.length) setFinalLegalIssues(state.legal_issues)
          setIsCompletedDraftModalOpen(true)
        } else if (state.draft) {
          setPendingDraft(state.draft)
          if (state.legal_issues) setPendingLegalIssues(state.legal_issues)
          if (state.stage === 'draft_review' || state.stage === 'legal_checking') {
            setIsDraftModalOpen(true)
            setWorkspaceTab('draft')
          }
        }
      })
      .catch((e) => {
        if (sessionLoadIdRef.current !== loadId) return
        setError(e instanceof Error ? e.message : '세션을 불러오지 못했습니다.')
      })
      .finally(() => {
        if (sessionLoadIdRef.current !== loadId) return
        setIsLoading(false)
        setLoadingMessage(null)
      })
  }, [route, user])

  const handleArticlesSubmit = async (articles: Record<string, string | null>) => {
    if (!sessionIdRef.current || isLoading) return
    const requestGeneration = requestGenerationRef.current
    const requestSessionId = sessionIdRef.current
    setError(null)
    setIsLoading(true)
    setLoadingMessage('조례 초안을 생성하고 있습니다...')
    try {
      const res = await submitArticlesBatch(requestSessionId, articles)
      if (
        requestGenerationRef.current !== requestGeneration ||
        routeRef.current.kind !== 'session' ||
        routeRef.current.sessionId !== requestSessionId
      ) return
      applyResponse(res)
    } catch (e) {
      if (requestGenerationRef.current !== requestGeneration) return
      setError(e instanceof Error ? e.message : '항목 전송에 실패했습니다.')
    } finally {
      if (requestGenerationRef.current !== requestGeneration) return
      setIsLoading(false)
      setLoadingMessage(null)
    }
  }

  const mappedArticles = useMemo(
    () => currentArticleKey ? [currentArticleKey, ...articleQueue] : [],
    [currentArticleKey, articleQueue]
  )
  const isArticleModalOpen = stage === 'article_interviewing' && mappedArticles.length > 0
  const handleApplicationApplied = useCallback((request: EvidenceApplyRequest) => {
    setPendingApplication(null)
    const requestSessionId = sessionIdRef.current
    const requestGeneration = requestGenerationRef.current
    if (requestSessionId && request.evidenceId) {
      const isCurrentSession = () => (
        requestGenerationRef.current === requestGeneration &&
        routeRef.current.kind === 'session' &&
        routeRef.current.sessionId === requestSessionId
      )
      void markEvidenceApplied(requestSessionId, request.evidenceId, request.targetArticleKey)
        .then(() => {
          if (isCurrentSession()) setEvidenceRefreshKey((value) => value + 1)
        })
        .catch(() => {
          if (isCurrentSession()) {
            setError('근거 적용 상태를 저장하지 못했습니다. 조문 내용은 유지됩니다.')
          }
        })
    }
  }, [])

  // ── 인증 게이트 ────────────────────────────────────────────────────────────
  if (authLoading) {
    return (
      <div style={loginPageStyle}>
        <p role="status" style={{ color: '#ffffff', fontSize: '1rem', fontWeight: 600 }}>인증 확인 중...</p>
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

  if (route.kind === 'list') {
    return (
      <>
        <ModelStatus />
        <SessionListScreen
          onSelectSession={handleSelectSession}
          onNewSession={handleNewSession}
          onTutorial={() => setTutorialStep(0)}
          user={user}
          onLogout={handleLogout}
        />
        {tutorialStep >= 0 && (
          <TutorialOverlay
            step={tutorialStep}
            onNext={handleTutorialNext}
            onPrev={handleTutorialPrev}
            onSkip={handleTutorialSkip}
          />
        )}
      </>
    )
  }

  return (
    <div className="app">
      <WorkspaceHeader
        ordinanceType={ordinanceType}
        stage={stage}
        fontSize={fontSize}
        onFontSizePreview={handleFontSizePreview}
        onFontSizeCommit={handleFontSizeCommit}
        articleAction={isArticleModalOpen && hideArticleModal ? () => setHideArticleModal(false) : undefined}
        draftAction={pendingDraft && !isDraftModalOpen && stage !== 'completed' ? () => setIsDraftModalOpen(true) : undefined}
        completedAction={completedDraft && !isCompletedDraftModalOpen ? () => setIsCompletedDraftModalOpen(true) : undefined}
        onNewSession={() => {
          if (hasSession && !window.confirm('현재 진행 중인 조례 작업이 있습니다. 새로 시작하시겠습니까?')) return
          handleNewSession()
        }}
        onTutorial={() => setTutorialStep(getInitialTutorialStep())}
        onBackToList={handleReset}
        onLogout={handleLogout}
        userName={user.displayName || user.email || '사용자'}
        userPhotoURL={user.photoURL}
      />
      <main ref={workspaceRef} className="app-main workspace-font-scope" style={{ '--workspace-font-size': `${fontSize}px` } as CSSProperties}>
        <div className="workspace-shell">
          <aside className="workspace-qa-panel" aria-label="법령 Q&A">
          <QAPanel
            sessionId={sessionIdRef.current}
            stage={stage}
            currentArticleKey={currentArticleKey}
            qaHistory={qaHistory}
            onAddMessages={(msgs) => setQaHistory((prev) => [...prev, ...msgs])}
            onApplyContent={(request) => {
              setPendingApplication({
                ...request,
                requestId: Date.now(),
              })
              setWorkspaceTab('articles')
              if (isArticleModalOpen && hideArticleModal) setHideArticleModal(false)
            }}
            onNewSession={handleNewSession}
            fontSize={fontSize}
            evidenceRefreshKey={evidenceRefreshKey}
          />

          {error && (
            <div className="error-bar" role="alert">
              ⚠️ {error}
              <button type="button" onClick={() => setError(null)} aria-label="오류 메시지 닫기">✕</button>
            </div>
          )}
          </aside>

          <section className="workspace-editor-pane" aria-label="조례 작업 영역">
            <div className="workspace-tabs" role="tablist" aria-label="조례 작업 보기">
              <button
                type="button"
                role="tab"
                aria-selected={workspaceTab === 'articles'}
                className={workspaceTab === 'articles' ? 'active' : ''}
                onClick={() => setWorkspaceTab('articles')}
                disabled={!isArticleModalOpen}
              >
                상세 조례
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={workspaceTab === 'draft'}
                className={workspaceTab === 'draft' ? 'active' : ''}
                onClick={() => setWorkspaceTab('draft')}
                disabled={!pendingDraft}
              >
                조례 초안
              </button>
            </div>

            <div className="workspace-tab-content">
              {workspaceTab === 'articles' && isArticleModalOpen ? (
                <ArticleItemsModal
                  embedded
                  articles={mappedArticles}
                  isLoading={isLoading}
                  onSubmit={handleArticlesSubmit}
                  onClose={() => undefined}
                  fontSize={fontSize}
                  onFontSizeChange={handleFontSizeCommit}
                  similarOrdinances={similarOrdinances}
                  pendingApplication={pendingApplication}
                  onApplicationApplied={handleApplicationApplied}
                  onApplicationCancelled={() => setPendingApplication(null)}
                  onCurrentArticleChange={setCurrentArticleKey}
                  onOpenQA={() => document.getElementById('qa-input')?.focus()}
                />
              ) : workspaceTab === 'draft' && pendingDraft ? (
                <DraftModal
                  embedded
                  draft={pendingDraft}
                  isLoading={isLoading}
                  legalIssues={pendingLegalIssues}
                  isLegallyValid={isLegallyValid}
                  onRequestLegalReview={handleLegalReview}
                  onFinalize={handleFinalize}
                  onClose={() => undefined}
                />
              ) : (
                <div className="workspace-empty">
                  <span aria-hidden="true">§</span>
                  <h2>조례 작업 영역</h2>
                  <p>새 조례 설계를 시작하면 상세 조문과 조례 초안을 이곳에서 함께 편집할 수 있습니다.</p>
                  <button type="button" onClick={handleNewSession}>새 조례 설계 시작</button>
                </div>
              )}
            </div>
          </section>
        </div>
      </main>

      <OnboardingWizard
        isOpen={isOnboardingOpen}
        onClose={() => {
          setIsOnboardingOpen(false)
          if (route.kind === 'new') navigate('/', { replace: true })
        }}
        onStart={handleWizardStart}
        isLoading={isLoading}
      />

      {isCompletedDraftModalOpen && completedDraft && sessionIdRef.current && (
        <CompletedDraftModal
          sessionId={sessionIdRef.current}
          draft={completedDraft}
          legalIssues={finalLegalIssues}
          onClose={() => setIsCompletedDraftModalOpen(false)}
        />
      )}

      {isLoading && loadingMessage && <LoadingModal message={loadingMessage} />}

      {tutorialStep >= 0 && (
        <TutorialOverlay
          step={tutorialStep}
          onNext={handleTutorialNext}
          onPrev={handleTutorialPrev}
          onSkip={handleTutorialSkip}
        />
      )}
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
  padding: '20px',
}

const loginCardStyle: React.CSSProperties = {
  background: '#ffffff',
  borderRadius: '16px',
  padding: 'clamp(28px, 8vw, 48px) clamp(20px, 7vw, 40px)',
  textAlign: 'center',
  boxShadow: '0 20px 60px rgba(0, 0, 0, 0.2)',
  width: 'min(100%, 420px)',
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
