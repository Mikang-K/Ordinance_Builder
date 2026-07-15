import { useEffect, useRef, useState } from 'react'
import { getModelStatus } from '../api'
import type { ModelStatusResponse } from '../types'

const LABELS: Record<string, string> = { intent: '의도 분석', intent_analyzer: '의도 분석', drafting: '초안 작성', drafting_agent: '초안 작성', reviewer: '초안 검토', draft_reviewer: '초안 검토', legal: '법률 검증', legal_checker: '법률 검증' }
const tone = (value: string): 'available' | 'degraded' | 'unavailable' => value === 'available' || value === 'healthy' ? 'available' : value === 'degraded' ? 'degraded' : 'unavailable'
const label = (value: string) => tone(value) === 'available' ? '정상' : tone(value) === 'degraded' ? '일부 제한' : '사용 불가'

export default function ModelStatus() {
  const [data, setData] = useState<ModelStatusResponse | null>(null), [open, setOpen] = useState(false), [failed, setFailed] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => { let active = true; getModelStatus().then(v => { if (active) setData(v) }).catch(() => { if (active) setFailed(true) }); return () => { active = false } }, [])
  useEffect(() => { if (!open) return; const close = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false) }; document.addEventListener('mousedown', close); return () => document.removeEventListener('mousedown', close) }, [open])
  const overall = failed ? 'unavailable' : tone(data?.status ?? 'degraded')
  return <div className="model-status" ref={root}>
    <button type="button" className={`model-status-trigger ${overall}`} aria-expanded={open} aria-controls="model-status-panel" onClick={() => setOpen(v => !v)}><span className="model-status-dot" aria-hidden="true" /><span>{failed ? '모델 상태 확인 불가' : data ? `AI 모델 ${label(data.status)}` : 'AI 모델 확인 중'}</span></button>
    {open && <section className="model-status-panel" id="model-status-panel" aria-label="활성 AI 모델 구성">
      <div className="model-status-heading"><strong>활성 AI 모델</strong><span>서버 설정 기준</span></div>
      {failed ? <p className="model-status-message" role="status">서버의 모델 상태를 확인할 수 없습니다.</p> : !data ? <p className="model-status-message" role="status">모델 구성을 불러오는 중입니다.</p> : data.models.length === 0 ? <p className="model-status-message">표시할 모델 구성이 없습니다.</p> : <ul className="model-status-list">{data.models.map(model => <li key={`${model.role}-${model.provider}-${model.model}`}><div className="model-status-row"><strong>{LABELS[model.role] ?? model.role}</strong><span className={`model-health ${tone(model.status)}`}>{label(model.status)}</span></div><div className="model-status-meta"><span>{model.provider}</span><span>{model.model}</span><span className={`deployment-badge ${model.deployment === 'local' ? 'local' : 'cloud'}`}>{model.deployment === 'local' ? '로컬' : '클라우드'}</span></div>{model.detail && <p>{model.detail}</p>}</li>)}</ul>}
    </section>}
  </div>
}
