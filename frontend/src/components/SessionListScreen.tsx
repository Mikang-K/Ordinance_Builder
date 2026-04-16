import { useEffect, useState } from 'react'
import type { SessionSummary } from '../types'
import { listSessions, deleteSession } from '../api'
import type { User } from '../firebase'

interface Props {
  onSelectSession: (sessionId: string) => void
  onNewSession: () => void
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

export default function SessionListScreen({ onSelectSession, onNewSession, user, onLogout }: Props) {
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
        <h1 className="session-list-title">조례 빌더 AI</h1>
        <p className="session-list-subtitle">지방 조례 초안 자동 생성 서비스</p>
        <button className="new-session-btn" onClick={onNewSession}>
          + 새 조례 만들기
        </button>
      </div>

      <div className="session-list-body">
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
            <h2 className="session-list-section-title">이전 작업</h2>
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
