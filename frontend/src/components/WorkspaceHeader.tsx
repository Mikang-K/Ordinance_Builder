import { useEffect, useRef, useState } from 'react'
import type { Stage } from '../types'
import StageIndicator from './StageIndicator'
import ModelStatus from './ModelStatus'

interface Props {
  ordinanceType: string | null
  stage: Stage | null
  fontSize: number
  onFontSizePreview: (value: number) => void
  onFontSizeCommit: (value: number) => void
  articleAction?: () => void
  draftAction?: () => void
  onNewSession: () => void
  onTutorial: () => void
  onBackToList: () => void
  onLogout: () => void
  userName: string
  userPhotoURL?: string | null
}

export default function WorkspaceHeader(props: Props) {
  const [previewSize, setPreviewSize] = useState(props.fontSize)
  const [committedStatus, setCommittedStatus] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const menuButton = useRef<HTMLButtonElement>(null)
  const firstMenuItem = useRef<HTMLButtonElement>(null)
  const menuRoot = useRef<HTMLDivElement>(null)

  useEffect(() => setPreviewSize(props.fontSize), [props.fontSize])
  useEffect(() => {
    if (!menuOpen) return
    firstMenuItem.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMenuOpen(false)
        menuButton.current?.focus()
      }
    }
    const onPointerDown = (event: PointerEvent) => {
      if (!menuRoot.current?.contains(event.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [menuOpen])

  const commitSize = () => {
    if (previewSize !== props.fontSize) {
      props.onFontSizeCommit(previewSize)
      setCommittedStatus(`본문 크기가 ${previewSize}px로 적용되었습니다.`)
    }
  }
  const contextualAction = props.draftAction
    ? <button type="button" className="header-context-action" onClick={props.draftAction}>초안 편집 · 검증</button>
    : props.articleAction
      ? <button type="button" className="header-context-action" onClick={props.articleAction}>상세 조항 편집</button>
      : null

  return (
    <header className="app-header workspace-header">
      <div className="header-identity">
        <div className="header-brand">
          <h1 className="app-title">조례 빌더 AI</h1>
          <span className="app-subtitle">지방 조례 초안 자동 생성 서비스</span>
        </div>
        <div className="ordinance-context" aria-label="현재 조례 작업">
          <span className="ordinance-context-label">현재 작업</span>
          <strong title={props.ordinanceType ? `${props.ordinanceType} 조례` : '새 조례 설계'}>
            {props.ordinanceType ? `${props.ordinanceType} 조례` : '새 조례 설계'}
          </strong>
        </div>
      </div>
      <div className="header-utilities">
        <div className="header-model-status-desktop"><ModelStatus instanceId="header-model-status" /></div>
        <div className="font-size-control">
          <label className="font-size-label" htmlFor="app-font-size">본문 크기</label>
          <input id="app-font-size" className="font-size-range" type="range" min="12" max="24" step="0.5"
            value={previewSize} aria-valuetext={`${previewSize}px`}
            onChange={(event) => {
              const value = Number(event.target.value)
              setPreviewSize(value)
              props.onFontSizePreview(value)
            }}
            onPointerUp={commitSize} onKeyUp={commitSize} onBlur={commitSize} />
          <output className="font-size-value" htmlFor="app-font-size">{previewSize}px</output>
          <span className="sr-only" aria-live="polite" aria-atomic="true">{committedStatus}</span>
        </div>
        <div className="header-user-menu" ref={menuRoot}>
          <button ref={menuButton} type="button" className="header-user-trigger"
            aria-expanded={menuOpen} aria-controls="workspace-user-menu"
            onClick={() => setMenuOpen(value => !value)}>
            {props.userPhotoURL
              ? <img src={props.userPhotoURL} alt="" className="header-avatar" referrerPolicy="no-referrer" />
              : <span className="header-avatar-fallback" aria-hidden="true">{props.userName.slice(0, 1)}</span>}
            <span className="header-user-name">{props.userName}</span><span aria-hidden="true">▾</span>
          </button>
          {menuOpen && <div id="workspace-user-menu" className="header-menu" aria-label="사용자 설정">
            <div className="header-model-status-mobile"><ModelStatus instanceId="mobile-model-status" /></div>
            <button ref={firstMenuItem} type="button" onClick={() => { setMenuOpen(false); props.onTutorial() }}>사용 안내</button>
            <button type="button" onClick={() => { setMenuOpen(false); props.onLogout() }}>로그아웃</button>
          </div>}
        </div>
      </div>
      <nav className="header-navigation" aria-label="작업 화면 이동">
        <button type="button" className="header-secondary-action" onClick={props.onBackToList}>← 목록</button>
      </nav>
      <div className="header-progress"><StageIndicator stage={props.stage} /></div>
      <div className="header-actions" aria-label="현재 작업">
        {contextualAction}
        <button type="button" className="header-primary-action" id="btn-new-session-header" onClick={props.onNewSession}>새 조례 만들기</button>
      </div>
    </header>
  )
}
