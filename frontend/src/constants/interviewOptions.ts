export type SelectionType = 'single' | 'multi'

export interface StructuredFieldConfig {
  label: string
  type: SelectionType
  options: readonly string[]
}

export type ArticleStructuredOptions = Record<string, StructuredFieldConfig>

export const ARTICLE_STRUCTURED_OPTIONS: Record<string, ArticleStructuredOptions> = {
  // ── 지원 조례 ──────────────────────────────────────────────────────────────
  지원금액: {
    amount: { label: '지원 한도', type: 'single', options: ['100만원', '300만원', '500만원', '1,000만원'] },
    period: { label: '지원 기간', type: 'single', options: ['1년', '2년', '3년'] },
    ratio:  { label: '지원 비율', type: 'single', options: ['50% 이내', '70% 이내', '100% 이내'] },
  },
  지원내용: {
    items: {
      label: '지원 항목 (복수 선택 가능)',
      type: 'multi',
      options: ['창업 초기비용', '임대료', '교육비', '장비 구입비', '마케팅비'],
    },
  },
  신청방법: {
    channels: {
      label: '신청 방법 (복수 선택 가능)',
      type: 'multi',
      options: ['방문 접수', '온라인 접수', '우편 접수'],
    },
  },
  심사선정: {
    method: {
      label: '심사 방식',
      type: 'single',
      options: ['서류 심사', '발표 심사', '서류+발표 혼합', '선착순'],
    },
  },

  // ── 설치·운영 조례 ─────────────────────────────────────────────────────────
  구성: {
    total: {
      label: '위원 정수',
      type: 'single',
      options: ['7명 이내', '9명 이내', '11명 이내', '15명 이내'],
    },
    term: {
      label: '위원 임기',
      type: 'single',
      options: ['1년', '2년', '3년'],
    },
    types: {
      label: '위원 구성 (복수 선택)',
      type: 'multi',
      options: ['당연직 공무원', '전문가 위촉', '시민 대표', '업계 대표', '학계 전문가'],
    },
  },
  운영: {
    quorum: {
      label: '의결 정족수',
      type: 'single',
      options: ['재적 과반수 출석·출석 과반수 의결', '재적 3분의 2 이상 출석·출석 과반수 의결'],
    },
    freq: {
      label: '정기회의 개최 주기',
      type: 'single',
      options: ['연 1회', '반기 1회', '분기 1회', '월 1회'],
    },
  },

  // ── 관리·규제 조례 ─────────────────────────────────────────────────────────
  사용료: {
    basis: {
      label: '사용료 부과 기준',
      type: 'single',
      options: ['시간당 부과', '일당 부과', '월 정액', '면적·규모 기준'],
    },
    reduction: {
      label: '감면 대상 (복수 선택)',
      type: 'multi',
      options: ['국가·지자체', '비영리단체', '저소득 취약계층', '장애인', '국가유공자'],
    },
  },
  위반제재: {
    fine: {
      label: '과태료 상한',
      type: 'single',
      options: ['50만원 이하', '100만원 이하', '200만원 이하', '500만원 이하'],
    },
    action: {
      label: '행정 제재 유형 (복수 선택)',
      type: 'multi',
      options: ['사용 중지', '허가 취소', '시정 명령', '원상 복구 명령'],
    },
  },

  // ── 복지·서비스 조례 ───────────────────────────────────────────────────────
  서비스내용: {
    items: {
      label: '제공 서비스 (복수 선택)',
      type: 'multi',
      options: ['방문 돌봄', '이동 지원', '식사 제공', '상담·교육', '의료 연계', '생활용품 지원'],
    },
    freq: {
      label: '서비스 제공 주기',
      type: 'single',
      options: ['상시', '주 1회', '주 2회', '월 2회', '필요시'],
    },
  },
  신청접수: {
    channels: {
      label: '신청 방법 (복수 선택)',
      type: 'multi',
      options: ['읍·면·동 주민센터', '온라인(앱·홈페이지)', '전화 신청', '복지관 방문'],
    },
    docs: {
      label: '제출 서류 (복수 선택)',
      type: 'multi',
      options: ['신청서', '소득 증빙', '건강보험료 납부확인서', '장애 진단서', '거주 확인서'],
    },
  },
  비용: {
    copay: {
      label: '본인 부담 방식',
      type: 'single',
      options: ['무료 (전액 지원)', '소득 수준별 차등 부담', '정액 본인 부담', '비율 본인 부담'],
    },
    exemption: {
      label: '면제 대상 (복수 선택)',
      type: 'multi',
      options: ['기초생활수급자', '차상위계층', '장애인', '국가유공자'],
    },
  },
}

/** 구조화 선택값을 drafting_agent가 이해할 수 있는 자연어 텍스트로 변환 */
export function formatSelectionAsText(
  selections: Record<string, string | string[]>
): string {
  const parts: string[] = []
  for (const [field, value] of Object.entries(selections)) {
    if (Array.isArray(value)) {
      if (value.length > 0) parts.push(`${fieldKorLabel(field)}: ${value.join(', ')}`)
    } else if (value) {
      parts.push(`${fieldKorLabel(field)}: ${value}`)
    }
  }
  return parts.join(' | ')
}

function fieldKorLabel(field: string): string {
  const map: Record<string, string> = {
    // 지원 조례
    amount: '지원 한도',
    period: '지원 기간',
    ratio: '지원 비율',
    items: '지원 항목',
    channels: '신청 방법',
    method: '심사 방식',
    // 설치·운영 조례
    total: '위원 정수',
    term: '위원 임기',
    types: '위원 구성',
    quorum: '의결 정족수',
    freq: '개최 주기',
    // 관리·규제 조례
    basis: '사용료 부과 기준',
    reduction: '감면 대상',
    fine: '과태료 상한',
    action: '행정 제재 유형',
    // 복지·서비스 조례
    docs: '제출 서류',
    copay: '본인 부담 방식',
    exemption: '면제 대상',
  }
  return map[field] ?? field
}
