import type {
  ChatResponse,
  FinalizeResponse,
  QAResponse,
  SessionCreateResponse,
  SessionStateResponse,
  SessionSummary,
  ModelRuntimeStatus,
  ModelStatusResponse,
  EvidenceCreateInput,
  EvidenceItem,
  EvidenceUpdateInput,
  WorkspaceResponse,
} from './types'
import { getIdToken } from './firebase'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`
}

async function authHeaders(): Promise<HeadersInit> {
  const token = await getIdToken()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  }
}

function normalizeModelStatus(payload: unknown): ModelStatusResponse {
  const data = (payload && typeof payload === 'object' ? payload : {}) as Record<string, unknown>
  const models = Array.isArray(data.models) ? data.models : data.roles && typeof data.roles === 'object'
    ? Object.entries(data.roles as Record<string, unknown>).map(([role, value]) => ({ role, ...(value && typeof value === 'object' ? value as Record<string, unknown> : {}) })) : []
  const normalized = models.map((value, index): ModelRuntimeStatus => {
    const item = (value && typeof value === 'object' ? value : {}) as Record<string, unknown>
    return { role: String(item.role ?? `model-${index + 1}`), provider: String(item.provider ?? 'unknown'), model: String(item.model ?? 'unknown'), deployment: String(item.deployment ?? (item.local === true ? 'local' : 'cloud')), status: String(item.status ?? 'unavailable'), detail: item.detail == null ? null : String(item.detail) }
  })
  return { status: String(data.status ?? (normalized.some(model => model.status === 'unavailable') ? 'degraded' : 'available')), models: normalized }
}

export async function getModelStatus(): Promise<ModelStatusResponse> {
  const res = await fetch(apiUrl('/api/v1/model-status'), { headers: await authHeaders() })
  if (!res.ok) throw new Error(`모델 상태 조회 실패: ${res.status}`)
  return normalizeModelStatus(await res.json())
}

export async function createSession(
  initialMessage: string,
  ordinanceType?: string,
): Promise<SessionCreateResponse> {
  const res = await fetch(apiUrl('/api/v1/session'), {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify({
      initial_message: initialMessage,
      ordinance_type: ordinanceType ?? null,
    }),
  })
  if (!res.ok) throw new Error(`세션 생성 실패: ${res.status}`)
  return res.json()
}

export async function sendMessage(
  sessionId: string,
  message: string,
  draftText?: string,
): Promise<ChatResponse> {
  const res = await fetch(apiUrl(`/api/v1/session/${sessionId}/chat`), {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify({ message, draft_text: draftText ?? null }),
  })
  if (!res.ok) throw new Error(`메시지 전송 실패: ${res.status}`)
  return res.json()
}

export async function submitArticlesBatch(
  sessionId: string,
  articles: Record<string, string | null>,
): Promise<ChatResponse> {
  const res = await fetch(apiUrl(`/api/v1/session/${sessionId}/articles_batch`), {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify({ articles }),
  })
  if (!res.ok) throw new Error(`상세 항목 전송 실패: ${res.status}`)
  return res.json()
}

export async function finalizeSession(
  sessionId: string,
  draftText: string,
): Promise<FinalizeResponse> {
  const res = await fetch(apiUrl(`/api/v1/session/${sessionId}/finalize`), {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify({ draft_text: draftText }),
  })
  if (!res.ok) throw new Error(`확정 요청 실패: ${res.status}`)
  return res.json()
}

export async function downloadFinalResult(
  sessionId: string,
  format: 'txt' | 'docx',
  filename?: string,
): Promise<Blob> {
  const params = new URLSearchParams({ format })
  if (filename) params.set('filename', filename)

  const res = await fetch(apiUrl(`/api/v1/session/${sessionId}/export?${params.toString()}`), {
    headers: await authHeaders(),
  })
  if (!res.ok) throw new Error(`파일 저장 요청 실패: ${res.status}`)
  return res.blob()
}

export async function listSessions(): Promise<SessionSummary[]> {
  const res = await fetch(apiUrl('/api/v1/sessions'), {
    headers: await authHeaders(),
  })
  if (!res.ok) throw new Error(`세션 목록 조회 실패: ${res.status}`)
  return res.json()
}

export async function getSessionState(sessionId: string): Promise<SessionStateResponse> {
  const res = await fetch(apiUrl(`/api/v1/session/${sessionId}`), {
    headers: await authHeaders(),
  })
  if (!res.ok) throw new Error(`세션 상태 조회 실패: ${res.status}`)
  return res.json()
}

async function workspaceMutation(path: string, method: 'PATCH' | 'POST', body?: object): Promise<WorkspaceResponse> {
  const res = await fetch(apiUrl(path), {
    method,
    headers: await authHeaders(),
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`작업공간 요청 실패: ${res.status}`)
  return res.json()
}

export async function getWorkspace(sessionId: string): Promise<WorkspaceResponse> {
  const res = await fetch(apiUrl(`/api/v1/session/${sessionId}/workspace`), { headers: await authHeaders() })
  if (!res.ok) throw new Error(`작업공간 조회 실패: ${res.status}`)
  return res.json()
}

export function saveRevisionArticles(sessionId: string, revisionId: string, articles: Record<string, string | null>, expectedVersion: number) {
  return workspaceMutation(`/api/v1/session/${sessionId}/revisions/${revisionId}/articles`, 'PATCH', { articles, expected_version: expectedVersion })
}

export function regenerateRevisionFromArticles(sessionId: string, expectedVersion: number) {
  return workspaceMutation(`/api/v1/session/${sessionId}/revisions/from-articles`, 'POST', { expected_version: expectedVersion })
}

export function saveRevisionDraft(sessionId: string, revisionId: string, draftText: string, expectedVersion: number) {
  return workspaceMutation(`/api/v1/session/${sessionId}/revisions/${revisionId}/draft`, 'PATCH', { draft_text: draftText, expected_version: expectedVersion })
}

export function reviewRevision(sessionId: string, revisionId: string, expectedVersion: number) {
  return workspaceMutation(`/api/v1/session/${sessionId}/revisions/${revisionId}/legal-review`, 'POST', { expected_version: expectedVersion })
}

export function finalizeRevision(sessionId: string, revisionId: string, expectedVersion: number) {
  return workspaceMutation(`/api/v1/session/${sessionId}/revisions/${revisionId}/finalize`, 'POST', { expected_version: expectedVersion })
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(apiUrl(`/api/v1/session/${sessionId}`), {
    method: 'DELETE',
    headers: await authHeaders(),
  })
  if (!res.ok) throw new Error(`세션 삭제 실패: ${res.status}`)
}

export async function askQuestion(
  sessionId: string,
  question: string,
): Promise<QAResponse> {
  const res = await fetch(apiUrl(`/api/v1/session/${sessionId}/qa`), {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify({ question }),
  })
  if (!res.ok) throw new Error(`Q&A 요청 실패: ${res.status}`)
  return res.json()
}

export async function searchDirectQuestion(
  question: string,
  context?: { current_article_key?: string | null; ordinance_info?: Record<string, string> | null },
): Promise<QAResponse> {
  const res = await fetch(apiUrl('/api/v1/qa'), {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify({ question, ...context }),
  })
  if (!res.ok) throw new Error(`직접 검색 Q&A 요청 실패: ${res.status}`)
  return res.json()
}

function evidencePath(sessionId: string, evidenceId?: string): string {
  const base = `/api/v1/session/${encodeURIComponent(sessionId)}/evidence`
  return evidenceId ? `${base}/${encodeURIComponent(evidenceId)}` : base
}

function normalizeEvidenceList(payload: unknown): EvidenceItem[] {
  if (Array.isArray(payload)) return payload as EvidenceItem[]
  if (!payload || typeof payload !== 'object') return []
  const record = payload as Record<string, unknown>
  const items = record.items ?? record.evidence
  return Array.isArray(items) ? items as EvidenceItem[] : []
}

export async function listEvidence(sessionId: string): Promise<EvidenceItem[]> {
  const res = await fetch(apiUrl(evidencePath(sessionId)), {
    headers: await authHeaders(),
  })
  if (!res.ok) throw new Error(`근거 목록을 불러오지 못했습니다: ${res.status}`)
  return normalizeEvidenceList(await res.json())
}

export async function createEvidence(
  sessionId: string,
  evidence: EvidenceCreateInput,
): Promise<EvidenceItem> {
  const res = await fetch(apiUrl(evidencePath(sessionId)), {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify(evidence),
  })
  if (!res.ok) throw new Error(`근거를 저장하지 못했습니다: ${res.status}`)
  return res.json()
}

export async function updateEvidence(
  sessionId: string,
  evidenceId: string,
  changes: EvidenceUpdateInput,
): Promise<EvidenceItem> {
  const res = await fetch(apiUrl(evidencePath(sessionId, evidenceId)), {
    method: 'PATCH',
    headers: await authHeaders(),
    body: JSON.stringify(changes),
  })
  if (!res.ok) throw new Error(`근거를 수정하지 못했습니다: ${res.status}`)
  return res.json()
}

export async function deleteEvidence(sessionId: string, evidenceId: string): Promise<void> {
  const res = await fetch(apiUrl(evidencePath(sessionId, evidenceId)), {
    method: 'DELETE',
    headers: await authHeaders(),
  })
  if (!res.ok) throw new Error(`근거를 삭제하지 못했습니다: ${res.status}`)
}

export async function markEvidenceApplied(
  sessionId: string,
  evidenceId: string,
  targetArticleKey: string,
): Promise<EvidenceItem> {
  const res = await fetch(apiUrl(`${evidencePath(sessionId, evidenceId)}/applied`), {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify({ target_article_key: targetArticleKey }),
  })
  if (!res.ok) throw new Error(`근거 적용 상태를 저장하지 못했습니다: ${res.status}`)
  return res.json()
}
