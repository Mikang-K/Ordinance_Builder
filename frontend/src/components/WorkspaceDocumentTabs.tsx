import { useRef } from 'react'

export type WorkspaceDocumentTab = 'articles' | 'draft' | 'final'

interface TabItem {
  id: WorkspaceDocumentTab
  label: string
  disabled?: boolean
  disabledReason?: string
}

interface Props {
  activeTab: WorkspaceDocumentTab
  tabs: TabItem[]
  onChange: (tab: WorkspaceDocumentTab) => void
}

export default function WorkspaceDocumentTabs({ activeTab, tabs, onChange }: Props) {
  const refs = useRef<Array<HTMLButtonElement | null>>([])
  const moveFocus = (currentIndex: number, direction: -1 | 1 | 'home' | 'end') => {
    const enabled = tabs.map((tab, index) => ({ tab, index })).filter(({ tab }) => !tab.disabled)
    if (!enabled.length) return
    const enabledIndex = enabled.findIndex(({ index }) => index === currentIndex)
    const next = direction === 'home' ? enabled[0] : direction === 'end'
      ? enabled[enabled.length - 1]
      : enabled[(enabledIndex + direction + enabled.length) % enabled.length]
    refs.current[next.index]?.focus()
    onChange(next.tab.id)
  }

  return (
    <div className="workspace-tabs" role="tablist" aria-label="조례 문서 작업 보기">
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          ref={(node) => { refs.current[index] = node }}
          id={`workspace-tab-${tab.id}`}
          type="button"
          role="tab"
          aria-selected={activeTab === tab.id}
          aria-controls={`workspace-panel-${tab.id}`}
          aria-disabled={tab.disabled || undefined}
          tabIndex={activeTab === tab.id ? 0 : -1}
          className={activeTab === tab.id ? 'active' : ''}
          onClick={() => !tab.disabled && onChange(tab.id)}
          onKeyDown={(event) => {
            if (event.key === 'ArrowLeft') { event.preventDefault(); moveFocus(index, -1) }
            if (event.key === 'ArrowRight') { event.preventDefault(); moveFocus(index, 1) }
            if (event.key === 'Home') { event.preventDefault(); moveFocus(index, 'home') }
            if (event.key === 'End') { event.preventDefault(); moveFocus(index, 'end') }
          }}
          title={tab.disabled ? tab.disabledReason : undefined}
        >
          <span>{tab.label}</span>
        </button>
      ))}
    </div>
  )
}
