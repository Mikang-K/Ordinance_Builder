import type { SessionCreateResponse, ChatResponse, FinalizeResponse, SessionSummary, SessionStateResponse } from './types'

export async function createSession(initialMessage: string): Promise<SessionCreateResponse> {
  const res = await fetch('/api/v1/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ initial_message: initialMessage }),
  })
  if (!res.ok) throw new Error(`세션 생성 실패: ${res.status}`)
  return res.json()
}

export async function sendMessage(
  sessionId: string,
  message: string,
  draftText?: string,
): Promise<ChatResponse> {
  const res = await fetch(`/api/v1/session/${sessionId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, draft_text: draftText ?? null }),
  })
  if (!res.ok) throw new Error(`메시지 전송 실패: ${res.status}`)
  return res.json()
}

export async function submitArticlesBatch(
  sessionId: string,
  articles: Record<string, string | null>,
): Promise<ChatResponse> {
  const res = await fetch(`/api/v1/session/${sessionId}/articles_batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ articles }),
  })
  if (!res.ok) throw new Error(`상세 항목 전송 실패: ${res.status}`)
  return res.json()
}

export async function finalizeSession(
  sessionId: string,
  draftText: string,
): Promise<FinalizeResponse> {
  const res = await fetch(`/api/v1/session/${sessionId}/finalize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ draft_text: draftText }),
  })
  if (!res.ok) throw new Error(`확정 요청 실패: ${res.status}`)
  return res.json()
}

export async function listSessions(): Promise<SessionSummary[]> {
  const res = await fetch('/api/v1/sessions')
  if (!res.ok) throw new Error(`세션 목록 조회 실패: ${res.status}`)
  return res.json()
}

export async function getSessionState(sessionId: string): Promise<SessionStateResponse> {
  const res = await fetch(`/api/v1/session/${sessionId}`)
  if (!res.ok) throw new Error(`세션 상태 조회 실패: ${res.status}`)
  return res.json()
}
