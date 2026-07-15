import { useEffect, useState } from 'react'
import type { SessionSummary } from '../types'
import { listSessions, deleteSession } from '../api'
import type { User } from '../firebase'

interface Props {
  onSelectSession: (sessionId: string) => void
  onNewSession: () => void
  onTutorial?: () => void
  user?: User | null
  onLogout?: () => void
}

const STAGE_LABELS: Record<string, string> = {
  intent_analysis: '시작',
  interviewing: '인터뷰 중',
  retrieving: '법령 검색 중',
  article_interviewing: '조항 작성 중',
  drafting: '초안 생성 중',
  draft_review: '초안 검토 중',
  legal_review_requested: '법률 검토 요청',
  legal_checking: '법률 검토 중',
  completed: '완료',
}

function formatDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('ko-KR', {
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function SessionListScreen({ onSelectSession, onNewSession, onTutorial, user, onLogout }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  useEffect(() => {
    listSessions()
      .then(setSessions)
      .catch(() => setError('세션 목록을 불러오지 못했습니다.'))
      .finally(() => setIsLoading(false))
  }, [])

  const handleDelete = async (sessionId: string, title: string) => {
    if (!window.confirm(`"${title}" 세션을 삭제하시겠습니까?\n삭제 후에는 복구할 수 없습니다.`)) return
    setDeletingId(sessionId)
    try {
      await deleteSession(sessionId)
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId))
    } catch {
      setError('세션 삭제에 실패했습니다. 다시 시도해 주세요.')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="session-list-screen">
      <div className="session-list-hero">
        {user && onLogout && (
          <div className="session-list-user">
            {user.photoURL && (
              <img src={user.photoURL} alt="프로필" className="session-list-avatar" referrerPolicy="no-referrer" />
            )}
            <span className="session-list-username">
              {user.displayName || user.email}
            </span>
            <button className="session-list-logout-btn" onClick={onLogout}>
              로그아웃
            </button>
          </div>
        )}
        <div className="session-hero-eyebrow"><span>AI LEGISLATIVE WORKBENCH</span><span className="session-hero-rule" /></div>
        <h1 className="session-list-title">근거에서 조문까지,<br /><span>신뢰할 수 있는 조례 설계</span></h1>
        <p className="session-list-subtitle">법령 근거와 유사 조례를 바탕으로 초안 작성부터 법률 검토까지 지원합니다.</p>
        <div className="session-hero-actions">
          <button id="btn-new-session" className="new-session-btn" onClick={onNewSession}>
            <span aria-hidden="true">＋</span> 새 조례 설계 시작
          </button>
          {onTutorial && (
            <button onClick={onTutorial} className="session-tutorial-btn">
              사용 안내 <span aria-hidden="true">→</span>
            </button>
          )}
        </div>
        <div className="session-workflow" aria-label="조례 설계 절차">
          {['기본정보', '근거 탐색', '조문 설계', '법률 검토', '초안 확정'].map((label, index) => (
            <div className="session-workflow-step" key={label}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <strong>{label}</strong>
            </div>
          ))}
        </div>
      </div>

      <div className="session-list-body">
        <div className="session-body-heading">
          <div>
            <span className="session-section-kicker">WORKSPACE</span>
            <h2>조례 설계 작업함</h2>
            <p>진행 중인 업무를 이어가거나 새로운 조례 설계를 시작하세요.</p>
          </div>
          <div className="session-trust-mark"><span>✓</span><div><strong>근거 중심 설계</strong><small>법령 · 유사 조례 연계</small></div></div>
        </div>
        {isLoading && (
          <p className="session-list-empty">불러오는 중...</p>
        )}

        {error && (
          <p className="session-list-error">{error}</p>
        )}

        {!isLoading && !error && sessions.length === 0 && (
          <p className="session-list-empty">
            이전에 작성한 조례가 없습니다.<br />새 조례를 만들어 보세요.
          </p>
        )}

        {sessions.length > 0 && (
          <>
            <h2 className="session-list-section-title">최근 작업 <span>{sessions.length}</span></h2>
            <ul className="session-list">
              {sessions.map((s) => (
                <li key={s.session_id} className="session-card">
                  <div className="session-card-info">
                    <span className="session-card-title">{s.title}</span>
                    <div className="session-card-meta">
                      <span className={`session-stage-badge ${s.stage === 'completed' ? 'completed' : 'in-progress'}`}>
                        {STAGE_LABELS[s.stage] ?? s.stage}
                      </span>
                      <span className="session-card-date">{formatDate(s.created_at)}</span>
                    </div>
                  </div>
                  <div className="session-card-actions">
                    <button
                      className="session-resume-btn"
                      onClick={() => onSelectSession(s.session_id)}
                      disabled={deletingId === s.session_id}
                    >
                      계속 작성
                    </button>
                    <button
                      className="session-delete-btn"
                      onClick={() => handleDelete(s.session_id, s.title)}
                      disabled={deletingId === s.session_id}
                      aria-label="세션 삭제"
                    >
                      {deletingId === s.session_id ? '삭제 중…' : '삭제'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}
