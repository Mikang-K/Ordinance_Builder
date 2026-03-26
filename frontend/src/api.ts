import type { SessionCreateResponse, ChatResponse, FinalizeResponse } from './types'

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
