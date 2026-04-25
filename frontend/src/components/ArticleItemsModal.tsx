import { useState, useEffect } from 'react'
import type { SimilarOrdinance } from '../types'
import { ARTICLE_STRUCTURED_OPTIONS, formatSelectionAsText } from '../constants/interviewOptions'

interface Props {
  articles: string[]
  isLoading: boolean
  onSubmit: (articles: Record<string, string | null>) => void
  onClose: () => void
  fontSize: number
  onFontSizeChange: (size: number) => void
  similarOrdinances?: SimilarOrdinance[]
  pendingQAContent?: string | null
  onQAContentApplied?: () => void
  onOpenQA?: () => void
}

const ARTICLE_GUIDES: Record<string, { title: string; hint: string; example?: string }> = {
  "목적": {
    title: "목적 조항 (제1조)",
    hint: "이 조례가 달성하고자 하는 목적을 작성해 주세요.\n• 무엇을 지원/규제하는 조례인지\n• 궁극적으로 실현하고자 하는 공익적 가치",
    example: "예시: '청년의 창업 활동을 지원하고 지역 경제 활성화에 이바지함을 목적으로 한다.'"
  },
  "정의": {
    title: "정의 조항 (제2조)",
    hint: "이 조례에서 사용하는 핵심 용어의 정의를 작성해 주세요.\n• 대상자 정의\n• 기타 주요 용어",
    example: "예시: '청년'이란 만 19세 이상 39세 이하인 사람을 말한다."
  },
  "지원대상": {
    title: "지원 대상 및 자격 조항",
    hint: "지원 대상의 자격 요건을 구체적으로 작성해 주세요.\n• 필수 요건 (거주지, 연령, 사업 기간 등)\n• 지원 제외 대상 (해당 시)",
    example: "예시: '공고일 기준 해당 지역에 6개월 이상 주소를 둔 만 19~39세 청년'"
  },
  "지원내용": {
    title: "지원 내용 조항",
    hint: "구체적인 지원 내용을 작성해 주세요.\n• 지원 항목 (예: 창업 초기비용, 임대료, 교육비 등)\n• 지원 방식 (현금, 현물, 바우처 등)",
    example: "예시: '예산 범위 내에서 창업 공간 임대료의 50% 이내를 보조금으로 지급한다.'"
  },
  "지원금액": {
    title: "지원 금액 및 기준 조항",
    hint: "지원 금액 및 산정 기준을 작성해 주세요.\n• 1인당 지원 한도 금액\n• 지원 기간 및 비율 (예: 최대 2년, 총비용의 70%)"
  },
  "신청방법": {
    title: "신청 방법 및 절차 조항",
    hint: "신청 절차 및 제출 서류를 작성해 주세요.\n• 신청 기관 및 방법 (방문 / 온라인)\n• 필요 서류 목록"
  },
  "심사선정": {
    title: "심사 및 선정 조항",
    hint: "심사 및 선정 방법을 작성해 주세요.\n• 심사 기관 및 위원회 구성\n• 심사 기준 (배점 등)"
  },
  "환수제재": {
    title: "환수 및 제재 조항",
    hint: "지원금 환수 및 제재 조건을 작성해 주세요.\n• 환수 사유 (허위 신청 등)\n• 환수 비율 및 지원 제한 기간"
  },
  "위임": {
    title: "위임 조항",
    hint: "세부 사항 위임 규정을 작성해 주세요.\n일반적으로 규칙으로 위임합니다.",
    example: "예시: '이 조례의 시행에 필요한 사항은 규칙으로 정한다.'"
  },
}

export default function ArticleItemsModal({
  articles,
  isLoading,
  onSubmit,
  onClose,
  fontSize,
  onFontSizeChange,
  similarOrdinances = [],
  pendingQAContent,
  onQAContentApplied,
  onOpenQA,
}: Props) {
  // values: null means "AI default". string means "User Input". undefined means "not evaluated yet".
  const [values, setValues] = useState<Record<string, string | null>>({})
  const [currentIndex, setCurrentIndex] = useState(0)
  const [structuredSelections, setStructuredSelections] = useState<Record<string, Record<string, string | string[]>>>({})

  // Specifically for the "정의" article
  const [definitions, setDefinitions] = useState<{ term: string; desc: string }[]>([{ term: '', desc: '' }])

  useEffect(() => {
    const initial: Record<string, string | null> = {}
    articles.forEach((key) => {
      initial[key] = '' // empty by default
    })
    setValues(initial)
    setStructuredSelections({})
    setCurrentIndex(0)
    setDefinitions([{ term: '', desc: '' }])
  }, [articles])

  // Sync definitions back to values['정의'] — only reacts to definitions changes, not navigation
  useEffect(() => {
    if (!('정의' in values)) return
    if (definitions.length === 1 && !definitions[0].term.trim() && !definitions[0].desc.trim()) {
      setValues((prev) => ({ ...prev, '정의': prev['정의'] === null ? null : '' }))
    } else {
      const compiled = definitions
        .filter(d => d.term.trim() || d.desc.trim())
        .map(d => `- ${d.term.trim()}: ${d.desc.trim()}`)
        .join('\n')
      setValues((prev) => {
        if (prev['정의'] === null) return prev
        return { ...prev, '정의': compiled }
      })
    }
  }, [definitions]) // eslint-disable-line react-hooks/exhaustive-deps

  // Pre-fill from QA panel "apply" action
  useEffect(() => {
    if (!pendingQAContent) return
    const currentKey = articles[currentIndex]
    if (!currentKey || currentKey === '정의') {
      onQAContentApplied?.()
      return
    }
    if (window.confirm(`Q&A 답변 내용을 '${currentKey}' 조항에 적용하시겠습니까?\n\n기존 입력 내용이 대체됩니다.`)) {
      setValues((prev) => ({ ...prev, [currentKey]: pendingQAContent }))
    }
    onQAContentApplied?.()
  }, [pendingQAContent, currentIndex, articles, onQAContentApplied])

  const handleAllDefaults = () => {
    if (window.confirm("입력하지 않은 나머지 모든 항목을 '기본값(AI 자동 작성)'으로 넘기고 조례 초안을 생성하시겠습니까?")) {
      const submitData: Record<string, string | null> = {}
      articles.forEach((key) => {
        submitData[key] = buildSubmitValue(key)
      })
      onSubmit(submitData)
    }
  }

  const handleSetDefault = (key: string) => {
    setValues((prev) => ({ ...prev, [key]: null }))
    setStructuredSelections((prev) => { const next = { ...prev }; delete next[key]; return next })
  }

  const handleChange = (key: string, val: string) => {
    setValues((prev) => ({ ...prev, [key]: val }))
  }

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose()
  }

  const handleNext = () => {
    if (currentIndex < articles.length - 1) {
      setCurrentIndex((p) => p + 1)
    } else {
      handleSubmit()
    }
  }

  const handlePrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex((p) => p - 1)
    }
  }

  const handleSubmit = () => {
    const submitData: Record<string, string | null> = {}
    articles.forEach((key) => {
      submitData[key] = buildSubmitValue(key)
    })
    onSubmit(submitData)
  }

  const handleAddDefinition = () => {
    setDefinitions([...definitions, { term: '', desc: '' }])
  }

  const handleRemoveDefinition = (index: number) => {
    setDefinitions(definitions.filter((_, i) => i !== index))
  }

  const handleDefinitionChange = (index: number, field: 'term' | 'desc', val: string) => {
    const newDefs = definitions.map((d, i) => i === index ? { ...d, [field]: val } : d)
    setDefinitions(newDefs)
  }

  const handleRestoreDefinitionManual = () => {
    handleChange('정의', '')
    setDefinitions([{ term: '', desc: '' }])
  }

  const handleStructuredSelect = (articleKey: string, field: string, value: string, type: 'single' | 'multi') => {
    setStructuredSelections(prev => {
      const articleSels = prev[articleKey] || {}
      if (type === 'single') {
        const next = articleSels[field] === value ? '' : value
        return { ...prev, [articleKey]: { ...articleSels, [field]: next } }
      } else {
        const current = (articleSels[field] as string[]) || []
        const next = current.includes(value)
          ? current.filter(v => v !== value)
          : [...current, value]
        return { ...prev, [articleKey]: { ...articleSels, [field]: next } }
      }
    })
  }

  const buildSubmitValue = (key: string): string | null => {
    const textVal = values[key]
    if (textVal === null) return null
    const sels = structuredSelections[key]
    const structuredText = sels ? formatSelectionAsText(sels) : ''
    const parts = [structuredText, textVal].filter(s => s && s.trim())
    const combined = parts.join('\n')
    return combined || null
  }

  if (articles.length === 0) return null
  const currentKey = articles[currentIndex]
  const val = values[currentKey]
  const isDefault = val === null
  const guide = ARTICLE_GUIDES[currentKey]

  return (
    <div 
      className="draft-modal-backdrop" 
      onClick={handleBackdropClick} 
      style={{ justifyContent: 'center', alignItems: 'center' }}
    >
      <div 
        className="draft-modal" 
        style={{ 
          maxWidth: '1200px', 
          width: '95vw', 
          height: 'min(90vh, 850px)', 
          borderRadius: '12px',
          display: 'flex',
          flexDirection: 'column',
          animation: 'none', // Override slideInRight
          boxShadow: '0 8px 32px rgba(0,0,0,0.18)'
        }}
      >
        <div className="draft-modal-header" style={{ padding: '16px 24px', height: '70px', boxSizing: 'border-box', flexShrink: 0 }}>
          <div className="draft-modal-title">
            <span className="draft-modal-icon">📋</span>
            <h2>조례 상세 조항 설정</h2>
            <span style={{ fontSize: '0.95rem', color: '#64748b', marginLeft: '8px', fontWeight: 600 }}>
              ( {currentIndex + 1} / {articles.length} )
            </span>
          </div>
          <div className="header-actions" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            {onOpenQA && (
              <button
                onClick={onOpenQA}
                style={{ fontSize: '0.85rem', padding: '6px 14px', background: '#0f766e', color: 'white', border: 'none', borderRadius: '6px', fontWeight: 600, cursor: 'pointer' }}
                title="법령 Q&A 패널 열기"
              >
                🔍 질문하기
              </button>
            )}
            <button
              className="draft-modal-review-btn"
              onClick={handleAllDefaults}
              disabled={isLoading}
              style={{ fontSize: '0.85rem', padding: '6px 14px', background: '#e2e8f0', color: '#1e293b', border: 'none', fontWeight: 600 }}
              title="비어있는 값을 모두 기본값으로 두고 제출합니다."
            >
              전체 기본값 및 즉시 제출
            </button>
            <div className="font-size-slider" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <span style={{ fontSize: '0.85rem', color: '#64748b' }}>폰트 크기</span>
              <input
                type="range"
                min="12"
                max="24"
                step="0.5"
                value={fontSize}
                onChange={(e) => onFontSizeChange(Number(e.target.value))}
                style={{ width: '120px', accentColor: '#1e40af' }}
                title="폰트 크기"
              />
            </div>
            <button className="draft-modal-close" onClick={onClose} aria-label="닫기">
              ✕
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
          {/* Left Panel: Sidebar */}
          <div style={{ width: '320px', background: '#f8fafc', borderRight: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '20px 16px', flex: 1, overflowY: 'auto' }}>
              <h3 style={{ fontSize: '0.85rem', color: '#64748b', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>진행 목차</h3>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {articles.map((k, idx) => {
                  const isActive = idx === currentIndex
                  const isDone = idx < currentIndex
                  return (
                    <li 
                      key={k} 
                      style={{ 
                        padding: '8px 12px', 
                        borderRadius: '6px', 
                        background: isActive ? '#e0e7ff' : (isDone ? '#f1f5f9' : 'transparent'),
                        color: isActive ? '#3730a3' : (isDone ? '#94a3b8' : '#64748b'),
                        fontWeight: isActive ? 700 : 500,
                        fontSize: '0.9rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                      }}
                    >
                      <span style={{ fontSize: '0.75rem', opacity: isActive ? 1 : 0.6 }}>{isDone ? '✓' : idx + 1}</span>
                      {k}
                    </li>
                  )
                })}
              </ul>
              {similarOrdinances.length > 0 && (
                <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid #e2e8f0' }}>
                  <h3 style={{ fontSize: '0.85rem', color: '#64748b', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>유사 조례</h3>
                  <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {similarOrdinances.slice(0, 3).map((o) => (
                      <li key={o.ordinance_id} style={{ fontSize: '0.82rem', color: '#475569' }}>
                        <div style={{ fontWeight: 600, color: '#334155', marginBottom: '2px' }}>{o.region_name}</div>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
                          <span style={{ flex: 1, lineHeight: '1.4' }}>{o.title}</span>
                          <a
                            href={`https://www.law.go.kr/ordinSc.do?query=${encodeURIComponent(o.title)}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ fontSize: '0.75rem', color: '#2563eb', whiteSpace: 'nowrap', textDecoration: 'none', border: '1px solid #bfdbfe', borderRadius: '4px', padding: '1px 6px', background: '#eff6ff', flexShrink: 0, marginTop: '1px' }}
                          >
                            원문 ↗
                          </a>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Guide Panel */}
            {guide && (
              <div style={{ padding: '20px 16px', background: '#fffbeb', borderTop: '1px solid #fde68a', overflowY: 'auto', maxHeight: '280px' }}>
                <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: '#b45309', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>💡</span> 작성 가이드
                </h4>
                <div style={{ fontSize: '0.85rem', color: '#92400e', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>
                  {guide.hint}
                </div>
                {guide.example && (
                  <div style={{ marginTop: '10px', fontSize: '0.8rem', color: '#047857', background: '#ecfdf5', padding: '8px 10px', borderRadius: '6px' }}>
                    {guide.example}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right Panel: Content Form */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#ffffff' }}>
            <div className="article-items-container" style={{ padding: '24px 32px', flex: 1, overflowY: 'auto' }}>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <div>
                  <h3 style={{ fontWeight: '700', color: '#1e293b', fontSize: '1.3rem', marginBottom: '4px' }}>
                    {guide?.title || currentKey}
                  </h3>
                  <p style={{ fontSize: '0.85rem', color: '#64748b' }}>
                    {ARTICLE_STRUCTURED_OPTIONS[currentKey]
                      ? '빠른 선택 또는 직접 입력 · AI 기본값을 사용할 수 있습니다.'
                      : '직접 입력하거나 AI 기본값을 사용할 수 있습니다.'}
                  </p>
                </div>
                {!isDefault ? (
                  <button
                    onClick={() => handleSetDefault(currentKey)}
                    style={{ background: 'white', border: '1px solid #cbd5e1', borderRadius: '6px', padding: '6px 14px', fontSize: '0.85rem', cursor: 'pointer', color: '#475569', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}
                    disabled={isLoading}
                  >
                    초기화 및 기본값(AI) 사용
                  </button>
                ) : (
                  <span style={{ fontSize: '0.85rem', color: '#2563eb', fontWeight: '600', background: '#dbeafe', padding: '6px 14px', borderRadius: '6px' }}>
                    ✨ AI 기본값 적용됨
                  </span>
                )}
              </div>

              {isDefault ? (
                <div 
                  style={{ padding: '30px 20px', color: '#64748b', fontSize: '1.05rem', background: '#f8fafc', borderRadius: '8px', cursor: 'pointer', textAlign: 'center', border: '2px dashed #cbd5e1', transition: 'all 0.2s' }} 
                  onClick={() => handleChange(currentKey, '')}
                >
                  <p style={{ marginBottom: '8px' }}>현재 <strong>기본값(AI 자동 생성)</strong>이 선택되어 있습니다.</p>
                  <p style={{ fontSize: '0.9rem', color: '#94a3b8' }}>마우스로 클릭하여 ✏️ 직접 내용을 입력할 수 있습니다.</p>
                </div>
              ) : (
                <>
                  {ARTICLE_STRUCTURED_OPTIONS[currentKey] && (
                    <div className="structured-input-panel" style={{ marginBottom: '16px' }}>
                      <p style={{ fontSize: '0.82rem', color: '#475569', marginBottom: '12px', fontWeight: 600 }}>
                        ✅ 빠른 선택 <span style={{ fontWeight: 400, color: '#94a3b8' }}>(아래 텍스트 입력과 함께 제출됩니다)</span>
                      </p>
                      {Object.entries(ARTICLE_STRUCTURED_OPTIONS[currentKey]).map(([field, config]) => {
                        const sels = structuredSelections[currentKey] || {}
                        const current = sels[field]
                        return (
                          <div key={field} style={{ marginBottom: '14px' }}>
                            <p style={{ fontSize: '0.82rem', color: '#64748b', marginBottom: '8px', fontWeight: 600 }}>{config.label}</p>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                              {config.options.map(opt => {
                                const isSelected = config.type === 'single'
                                  ? current === opt
                                  : Array.isArray(current) && current.includes(opt)
                                return (
                                  <button
                                    key={opt}
                                    className={`option-chip${isSelected ? ' selected' : ''}`}
                                    onClick={() => handleStructuredSelect(currentKey, field, opt, config.type)}
                                    disabled={isLoading}
                                  >
                                    {opt}
                                  </button>
                                )
                              })}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                  {currentKey === '정의' ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {definitions.map((def, idx) => (
                    <div key={idx} style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                      <input
                        type="text"
                        placeholder="용어 (예: 청년)"
                        value={def.term}
                        onChange={(e) => handleDefinitionChange(idx, 'term', e.target.value)}
                        style={{ padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: '6px', width: '30%', fontSize: '0.95rem' }}
                        disabled={isLoading}
                      />
                      <input
                        type="text"
                        placeholder="설명 (예: 만 19세 이상 39세 이하인 사람을 말한다.)"
                        value={def.desc}
                        onChange={(e) => handleDefinitionChange(idx, 'desc', e.target.value)}
                        style={{ padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: '6px', flex: 1, fontSize: '0.95rem' }}
                        disabled={isLoading}
                      />
                      <button
                        onClick={() => handleRemoveDefinition(idx)}
                        disabled={isLoading || definitions.length === 1}
                        style={{ padding: '10px', color: '#ef4444', background: 'none', border: 'none', cursor: 'pointer', opacity: definitions.length === 1 ? 0.3 : 1 }}
                        title="삭제"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                  <button
                    onClick={handleAddDefinition}
                    disabled={isLoading}
                    style={{ alignSelf: 'flex-start', padding: '8px 16px', background: '#f8fafc', border: '1px dashed #cbd5e1', borderRadius: '6px', color: '#475569', cursor: 'pointer', fontSize: '0.9rem', marginTop: '4px', fontWeight: 600 }}
                  >
                    + 용어 추가
                  </button>
                </div>
              ) : (
                <textarea
                  value={val || ''}
                  onChange={(e) => handleChange(currentKey, e.target.value)}
                  style={{ width: '100%', height: 'calc(100% - 80px)', minHeight: '200px', padding: '16px', border: '1px solid #cbd5e1', borderRadius: '6px', resize: 'none', fontSize: '1rem', lineHeight: '1.6', fontFamily: 'inherit' }}
                  placeholder={`${currentKey} 조항에 들어갈 내용이나 주요 키워드를 자유롭게 입력하세요.\n개행을 활용해 세부 항목을 나눌 수 있습니다.`}
                  disabled={isLoading}
                />
              )}
                </>
              )}
            </div>

            {/* Footer buttons */}
            <div className="draft-modal-footer" style={{ padding: '16px 32px', display: 'flex', gap: '12px', justifyContent: 'space-between', background: '#f8fafc', borderTop: '1px solid #e2e8f0' }}>
              <button
                onClick={handlePrev}
                disabled={isLoading || currentIndex === 0}
                style={{ padding: '12px 28px', background: currentIndex === 0 ? 'transparent' : '#ffffff', color: currentIndex === 0 ? 'transparent' : '#475569', border: currentIndex === 0 ? 'none' : '1px solid #cbd5e1', borderRadius: '8px', cursor: currentIndex === 0 ? 'default' : 'pointer', fontWeight: 600, fontSize: '0.95rem', boxShadow: currentIndex === 0 ? 'none' : '0 1px 2px rgba(0,0,0,0.05)' }}
              >
                이전
              </button>
              
              <button
                onClick={handleNext}
                disabled={isLoading}
                style={{ flex: 1, padding: '12px', background: '#1e40af', color: 'white', border: 'none', borderRadius: '8px', fontWeight: 700, fontSize: '1.05rem', cursor: 'pointer', boxShadow: '0 4px 6px -1px rgba(30, 64, 175, 0.4)' }}
              >
                {isLoading ? '처리 중...' : currentIndex < articles.length - 1 ? '다음 단계로' : '확인 및 조례 초안 생성'}
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
