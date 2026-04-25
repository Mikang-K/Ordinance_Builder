import { useState } from 'react'

// ── Type definitions ──────────────────────────────────────────────────────────

const ORDINANCE_TYPES = [
  {
    value: '지원',
    label: '지원 조례',
    icon: '💰',
    description: '보조금·융자·세금 감면 등 경제적 지원 제공',
  },
  {
    value: '설치·운영',
    label: '설치·운영 조례',
    icon: '🏛️',
    description: '위원회·심의회·자문단 등 기구 설치 및 운영',
  },
  {
    value: '관리·규제',
    label: '관리·규제 조례',
    icon: '⚖️',
    description: '시설 사용 허가·사용료·위반 제재 등 규정',
  },
  {
    value: '복지·서비스',
    label: '복지·서비스 조례',
    icon: '🤝',
    description: '주민에게 복지 서비스를 직접 제공',
  },
]

interface StepConfig {
  field: string
  title: string
  description: string
  placeholder: string
  options: string[]
}

const REGION_STEP: StepConfig = {
  field: 'region',
  title: '어느 지역의 조례를 만드시겠습니까?',
  description: '지방자치단체를 선택하거나 직접 입력해 주세요.',
  placeholder: '예: 경상남도 창원시',
  options: [
    '서울특별시', '부산광역시', '인천광역시', '대구광역시',
    '광주광역시', '대전광역시', '울산광역시', '세종특별자치시',
    '경기도', '강원특별자치도', '충청북도', '충청남도',
    '전북특별자치도', '전라남도', '경상북도', '경상남도', '제주특별자치도',
  ],
}

const TYPE_STEPS: Record<string, StepConfig[]> = {
  '지원': [
    {
      field: 'purpose',
      title: '어떤 목적의 지원 조례를 만드시겠습니까?',
      description: '지원 사업의 주요 목적을 선택하거나 직접 입력해 주세요.',
      placeholder: '예: 청년 창업 지원',
      options: [
        '청년 창업 지원', '소상공인 지원', '스타트업 생태계 조성',
        '중소기업 지원', '사회적 기업 지원', '지역 경제 활성화',
        '청년 일자리 창출', '여성 기업인 지원', '문화·예술 지원', '농어업인 지원',
      ],
    },
    {
      field: 'target_group',
      title: '주요 지원 대상은 누구입니까?',
      description: '조례의 수혜자를 선택하거나 직접 입력해 주세요.',
      placeholder: '예: 만 18세 이상 45세 미만 청년',
      options: [
        '청년 (만 19~39세)', '소상공인', '스타트업 창업자',
        '중소기업', '사회적 기업', '예비창업자',
        '여성창업자', '청년 농업인', '장애인 기업인',
      ],
    },
    {
      field: 'support_type',
      title: '어떤 방식으로 지원하시겠습니까?',
      description: '주요 지원 유형을 선택하거나 직접 입력해 주세요.',
      placeholder: '예: 기술 개발비 및 특허 출원 비용 지원',
      options: [
        '보조금 지급', '임대료 지원', '세금 감면',
        '교육·멘토링 지원', '장비·시설 지원', '융자·투자 연계',
        '행정 지원', '네트워킹·컨설팅',
      ],
    },
  ],
  '설치·운영': [
    {
      field: 'purpose',
      title: '어떤 기구를 설치·운영하시겠습니까?',
      description: '설치할 위원회·자문단·심의회 등의 유형을 선택하거나 입력해 주세요.',
      placeholder: '예: 청년 정책 심의위원회',
      options: [
        '청년 정책 위원회', '지역 경제 자문단', '중소기업 육성 심의회',
        '사회적 기업 지원 위원회', '문화예술 진흥 위원회', '환경 보전 위원회',
        '도시 계획 자문위원회', '복지 서비스 심의위원회',
      ],
    },
    {
      field: 'target_group',
      title: '위원회의 주요 구성원은 누구입니까?',
      description: '위원회 구성 대상을 선택하거나 직접 입력해 주세요.',
      placeholder: '예: 관련 분야 전문가 및 청년 대표',
      options: [
        '관련 분야 전문가', '지역 주민 대표', '학계·연구기관 전문가',
        '시민단체 대표', '업계 전문가', '청년 대표',
        '공무원 (당연직)', '소상공인 대표',
      ],
    },
    {
      field: 'support_type',
      title: '위원회의 주요 기능은 무엇입니까?',
      description: '위원회가 수행할 주요 역할을 선택하거나 입력해 주세요.',
      placeholder: '예: 관련 정책 심의 및 의결',
      options: [
        '정책 심의·의결', '자문·건의', '계획 수립·평가',
        '사업 승인·심사', '분쟁 조정', '예산 심의',
        '사업 모니터링·평가',
      ],
    },
  ],
  '관리·규제': [
    {
      field: 'purpose',
      title: '어떤 시설이나 행위를 관리·규제하시겠습니까?',
      description: '규제 대상 시설 또는 행위를 선택하거나 입력해 주세요.',
      placeholder: '예: 공공 체육 시설 사용 관리',
      options: [
        '공공 체육 시설', '공영 주차장', '공공 광장·공원',
        '농수산물 직판장', '공공 회의실·강당', '도로·하천 점용',
        '공유 재산 관리', '영업 행위 규제',
      ],
    },
    {
      field: 'target_group',
      title: '관리·규제 적용 대상은 누구입니까?',
      description: '규제를 받는 대상을 선택하거나 직접 입력해 주세요.',
      placeholder: '예: 시설 이용자 및 입점 업체',
      options: [
        '시설 이용자 (개인)', '입점 업체·사업자', '행사·집회 주최자',
        '공공 자산 점용자', '도로 굴착 사업자', '간판·광고물 설치자',
        '특정 구역 영업자',
      ],
    },
    {
      field: 'support_type',
      title: '주요 규제 방식은 무엇입니까?',
      description: '적용할 규제·관리 방식을 선택하거나 입력해 주세요.',
      placeholder: '예: 사용 허가 및 사용료 징수',
      options: [
        '사용 허가·신고', '사용료·점용료 징수', '과태료 부과',
        '시정 명령·행정 제재', '등록·지정 취소', '사용 제한·금지',
        '행정 조사·점검',
      ],
    },
  ],
  '복지·서비스': [
    {
      field: 'purpose',
      title: '어떤 복지 서비스를 제공하시겠습니까?',
      description: '제공할 서비스 유형을 선택하거나 직접 입력해 주세요.',
      placeholder: '예: 노인 돌봄 및 일상 지원 서비스',
      options: [
        '노인 돌봄 서비스', '장애인 이동 지원', '아동 보육 지원',
        '청년 주거 지원', '취약계층 생활 지원', '정신건강 상담 서비스',
        '임산부·육아 지원', '다문화가족 지원',
      ],
    },
    {
      field: 'target_group',
      title: '서비스 수혜 대상은 누구입니까?',
      description: '서비스를 받을 주요 대상을 선택하거나 입력해 주세요.',
      placeholder: '예: 만 65세 이상 독거 노인',
      options: [
        '노인 (만 65세 이상)', '장애인', '아동·청소년',
        '임산부·영유아 가정', '저소득 취약계층', '다문화가족',
        '청년 1인 가구', '한부모 가정',
      ],
    },
    {
      field: 'support_type',
      title: '서비스 제공 방식은 무엇입니까?',
      description: '서비스를 어떤 방식으로 제공할지 선택하거나 입력해 주세요.',
      placeholder: '예: 전담 인력 파견 및 방문 서비스',
      options: [
        '전담 인력 파견', '기관 위탁 운영', '바우처·이용권 지급',
        '시설 직접 운영', '방문 서비스 제공', '온라인 플랫폼 연계',
        '민·관 협력 서비스',
      ],
    },
  ],
}

// ── Message builders ──────────────────────────────────────────────────────────

function buildMessage(type: string, fields: Record<string, string>): string {
  const { region, purpose, target_group, support_type } = fields
  switch (type) {
    case '설치·운영':
      return `${region}에서 ${purpose} 조례를 만들고 싶습니다. 조례 유형은 설치·운영 조례이며, ${target_group}으로 구성되는 위원회가 ${support_type} 역할을 수행하도록 설계하고자 합니다.`
    case '관리·규제':
      return `${region}에서 ${purpose} 관련 조례를 만들고 싶습니다. 조례 유형은 관리·규제 조례이며, ${target_group}을(를) 대상으로 ${support_type} 방식으로 관리·규제하고자 합니다.`
    case '복지·서비스':
      return `${region}에서 ${purpose} 조례를 만들고 싶습니다. 조례 유형은 복지·서비스 조례이며, ${target_group}에게 ${support_type} 방식으로 서비스를 제공하고자 합니다.`
    default: // '지원'
      return `${region}에서 ${purpose} 조례를 만들고 싶습니다. 지원 대상은 ${target_group}이며, ${support_type} 방식으로 지원하고자 합니다.`
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  onStart: (message: string) => void
  isLoading: boolean
}

export default function OnboardingWizard({ onStart, isLoading }: Props) {
  const [selectedType, setSelectedType] = useState<string>('')
  const [stepIndex, setStepIndex] = useState(-1)   // -1 = type selection screen
  const [selections, setSelections] = useState<Record<string, string>>({})
  const [textInputs, setTextInputs] = useState<Record<string, string>>({})

  const typeSteps = selectedType ? [REGION_STEP, ...(TYPE_STEPS[selectedType] ?? TYPE_STEPS['지원'])] : []
  const isTypeScreen = stepIndex === -1
  const step = isTypeScreen ? null : typeSteps[stepIndex]
  const totalSteps = typeSteps.length  // 4 steps after type selection
  const chipValue = step ? (selections[step.field] ?? '') : ''
  const textValue = step ? (textInputs[step.field] ?? '') : ''
  const currentValue = textValue.trim() || chipValue
  const canAdvance = isTypeScreen ? !!selectedType : !!currentValue

  const handleTypeSelect = (type: string) => {
    setSelectedType(prev => prev === type ? '' : type)
  }

  const handleChipClick = (opt: string) => {
    if (!step) return
    setSelections(prev => ({ ...prev, [step.field]: prev[step.field] === opt ? '' : opt }))
    setTextInputs(prev => ({ ...prev, [step.field]: '' }))
  }

  const handleTextChange = (val: string) => {
    if (!step) return
    setTextInputs(prev => ({ ...prev, [step.field]: val }))
    if (val.trim()) {
      setSelections(prev => ({ ...prev, [step.field]: '' }))
    }
  }

  const handleNext = () => {
    if (!canAdvance) return
    if (isTypeScreen) {
      setStepIndex(0)
    } else if (stepIndex < totalSteps - 1) {
      setStepIndex(s => s + 1)
    } else {
      handleSubmit()
    }
  }

  const handleBack = () => {
    if (stepIndex === 0) setStepIndex(-1)
    else if (stepIndex > 0) setStepIndex(s => s - 1)
  }

  const handleSubmit = () => {
    const get = (field: string) => textInputs[field]?.trim() || selections[field] || ''
    const fields = {
      region: get('region'),
      purpose: get('purpose'),
      target_group: get('target_group'),
      support_type: get('support_type'),
    }
    onStart(buildMessage(selectedType, fields))
  }

  const progress = isTypeScreen ? 0 : ((stepIndex + 1) / totalSteps) * 100

  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px 16px',
      background: '#f8fafc',
      overflowY: 'auto',
    }}>
      <div style={{
        width: '100%',
        maxWidth: '620px',
        background: '#ffffff',
        borderRadius: '16px',
        boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
        overflow: 'hidden',
      }}>
        {/* Progress bar */}
        <div style={{ height: '4px', background: '#e2e8f0' }}>
          <div style={{
            height: '100%',
            width: `${progress}%`,
            background: 'linear-gradient(90deg, #1e40af, #3b82f6)',
            transition: 'width 0.3s ease',
          }} />
        </div>

        <div style={{ padding: '32px 36px 28px' }}>
          {isTypeScreen ? (
            /* ── Step 0: Ordinance type selection ────────────────────────── */
            <>
              <p style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: 600, margin: '0 0 12px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                STEP 0 / {totalSteps || 4}
              </p>
              <h2 style={{ fontSize: '1.3rem', fontWeight: 700, color: '#1e293b', margin: '0 0 6px', lineHeight: 1.4 }}>
                어떤 유형의 조례를 만드시겠습니까?
              </h2>
              <p style={{ fontSize: '0.88rem', color: '#64748b', margin: '0 0 24px' }}>
                조례 유형에 따라 최적화된 조문 구조가 자동 선택됩니다.
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                {ORDINANCE_TYPES.map(t => {
                  const selected = selectedType === t.value
                  return (
                    <button
                      key={t.value}
                      onClick={() => handleTypeSelect(t.value)}
                      disabled={isLoading}
                      style={{
                        padding: '16px 14px',
                        borderRadius: '12px',
                        border: selected ? '2px solid #1e40af' : '1.5px solid #e2e8f0',
                        background: selected ? '#eff6ff' : '#f8fafc',
                        color: selected ? '#1e40af' : '#374151',
                        textAlign: 'left',
                        cursor: 'pointer',
                        transition: 'all 0.15s',
                        boxShadow: selected ? '0 0 0 3px rgba(30,64,175,0.1)' : 'none',
                      }}
                    >
                      <div style={{ fontSize: '1.5rem', marginBottom: '6px' }}>{t.icon}</div>
                      <div style={{ fontWeight: 700, fontSize: '0.92rem', marginBottom: '4px' }}>
                        {selected && '✓ '}{t.label}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: selected ? '#3b82f6' : '#94a3b8', lineHeight: 1.5 }}>
                        {t.description}
                      </div>
                    </button>
                  )
                })}
              </div>
            </>
          ) : step ? (
            /* ── Steps 1–4: Field collection ─────────────────────────────── */
            <>
              <p style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: 600, margin: '0 0 12px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                STEP {stepIndex + 1} / {totalSteps}
              </p>
              <h2 style={{ fontSize: '1.3rem', fontWeight: 700, color: '#1e293b', margin: '0 0 6px', lineHeight: 1.4 }}>
                {step.title}
              </h2>
              <p style={{ fontSize: '0.88rem', color: '#64748b', margin: '0 0 24px' }}>
                {step.description}
              </p>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '20px' }}>
                {step.options.map(opt => {
                  const selected = chipValue === opt
                  return (
                    <button
                      key={opt}
                      onClick={() => handleChipClick(opt)}
                      disabled={isLoading}
                      style={{
                        padding: '8px 16px',
                        borderRadius: '20px',
                        border: selected ? '2px solid #1e40af' : '1.5px solid #cbd5e1',
                        background: selected ? '#eff6ff' : '#ffffff',
                        color: selected ? '#1e40af' : '#475569',
                        fontWeight: selected ? 700 : 500,
                        fontSize: '0.88rem',
                        cursor: 'pointer',
                        transition: 'all 0.15s',
                        boxShadow: selected ? '0 0 0 3px rgba(30,64,175,0.1)' : 'none',
                      }}
                    >
                      {selected && '✓ '}{opt}
                    </button>
                  )
                })}
              </div>

              <div style={{ position: 'relative' }}>
                <input
                  type="text"
                  value={textValue}
                  onChange={e => handleTextChange(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') handleNext() }}
                  placeholder={step.placeholder}
                  disabled={isLoading}
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    border: textValue.trim() ? '2px solid #1e40af' : '1.5px solid #e2e8f0',
                    borderRadius: '8px',
                    fontSize: '0.95rem',
                    color: '#1e293b',
                    background: '#f8fafc',
                    outline: 'none',
                    boxSizing: 'border-box',
                    transition: 'border-color 0.15s',
                  }}
                />
                {!textValue.trim() && !chipValue && (
                  <span style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', fontSize: '0.75rem', color: '#94a3b8' }}>
                    직접 입력
                  </span>
                )}
              </div>
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div style={{
          padding: '16px 36px 24px',
          display: 'flex',
          gap: '10px',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderTop: '1px solid #f1f5f9',
        }}>
          <button
            onClick={handleBack}
            disabled={isTypeScreen || isLoading}
            style={{
              padding: '10px 20px',
              background: 'transparent',
              border: isTypeScreen ? 'none' : '1px solid #cbd5e1',
              borderRadius: '8px',
              color: isTypeScreen ? 'transparent' : '#475569',
              fontSize: '0.9rem',
              fontWeight: 600,
              cursor: isTypeScreen ? 'default' : 'pointer',
            }}
          >
            이전
          </button>

          {/* Step dots: type + 4 fields */}
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            {/* Type dot */}
            <div style={{
              width: isTypeScreen ? '18px' : '8px',
              height: '8px',
              borderRadius: '4px',
              background: isTypeScreen ? '#3b82f6' : '#1e40af',
              transition: 'all 0.2s',
            }} />
            {typeSteps.map((_, i) => (
              <div key={i} style={{
                width: i === stepIndex ? '18px' : '8px',
                height: '8px',
                borderRadius: '4px',
                background: i < stepIndex ? '#1e40af' : i === stepIndex ? '#3b82f6' : '#e2e8f0',
                transition: 'all 0.2s',
              }} />
            ))}
          </div>

          <button
            onClick={handleNext}
            disabled={!canAdvance || isLoading}
            style={{
              padding: '10px 28px',
              background: canAdvance ? '#1e40af' : '#e2e8f0',
              color: canAdvance ? '#ffffff' : '#94a3b8',
              border: 'none',
              borderRadius: '8px',
              fontSize: '0.95rem',
              fontWeight: 700,
              cursor: canAdvance ? 'pointer' : 'default',
              transition: 'all 0.15s',
              boxShadow: canAdvance ? '0 4px 12px rgba(30,64,175,0.25)' : 'none',
            }}
          >
            {isLoading ? '생성 중...' : isTypeScreen ? '다음' : stepIndex < totalSteps - 1 ? '다음' : '조례 만들기 시작'}
          </button>
        </div>
      </div>

      <p style={{ marginTop: '20px', fontSize: '0.82rem', color: '#94a3b8', textAlign: 'center' }}>
        모든 항목은 이후 대화에서 언제든지 변경할 수 있습니다
      </p>
    </div>
  )
}
