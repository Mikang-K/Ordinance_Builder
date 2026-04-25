# Plan: 조례 인터뷰 UX 재설계 (interview-ux-redesign)

**작성일**: 2026-04-25  
**상태**: Planning  
**단계**: Plan

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **문제** | 기본정보 자유 대화 + 조항 텍스트에어리어 방식은 법률 비전문가에게 진입장벽이 높고, 어떤 값을 입력해야 할지 몰라 이탈이 발생함 |
| **해결** | 채팅 AI 메시지 하단에 버튼 칩 선택지를 추가하고, 조항 모달의 각 항목에 구조화 선택 UI를 병합 — 직접 입력과 선택지 클릭을 모두 허용 |
| **기능 UX 효과** | 빈 화면 앞 이탈률 감소 / 필드 완성 속도 향상 / 입력 오류 최소화 / "AI에게 맡기기" 외 중간 지점 제공 |
| **핵심 가치** | 법률 비전문가도 선택지만 클릭해도 완성도 높은 조례 초안을 생성할 수 있는 경험 |

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | 현재 인터뷰 UX가 법령 지식이 없는 사용자에게 너무 많은 자유도를 주어 완성률이 낮음 |
| **WHO** | 지자체 담당 공무원, 지방의원 보좌 인력 — 법령 초안 작성 경험 적음 |
| **RISK** | 선택지가 너무 많으면 오히려 인지 부하 증가 / 선택지 범위가 좁으면 자유도 침해 |
| **SUCCESS** | 기본정보 4개 필드를 선택지 클릭만으로도 완성 가능 / 조항 상세 최소 3개 항목에 구조화 입력 제공 |
| **SCOPE** | 프론트엔드 + 백엔드 API 응답 스키마 확장 / LangGraph 워크플로우 구조는 변경 없음 |

---

## 1. 배경 및 목표

### 현재 문제

**기본정보 수집 단계** (채팅):
- AI가 자연어로 질문 → 사용자가 빈 입력창에 자유 텍스트 입력
- "어떤 지원 방식인가요?" → 사용자가 "보조금 지급" 같은 법률 용어를 스스로 알아야 함
- 첫 화면의 빈 입력창이 이탈 포인트

**조항 상세 입력 단계** (ArticleItemsModal):
- 9개 조항 각각 텍스트에어리어만 있음
- "기본값 사용" (AI 자동) vs "직접 입력" 두 가지 선택지만 존재
- 중간 지점 없음: 금액·기간 등 수치는 알지만 법적 문장은 못 쓰는 사용자 이탈

### 목표

1. 채팅 AI 응답에 **버튼 칩 선택지** 추가 (필요한 질문에 한해)
2. ArticleItemsModal 각 조항에 **구조화 선택 UI** 추가 (텍스트에어리어와 공존)
3. 선택지 클릭 시 기존 LangGraph 플로우 그대로 동작 (텍스트 메시지 전송과 동일)
4. 백엔드 drafting_agent가 선택값 구조체를 받아 법적 조문으로 변환

---

## 2. 범위 (Scope)

### 포함

| 구성요소 | 변경 내용 |
|----------|-----------|
| `frontend/src/types.ts` | `SuggestedOption` 인터페이스, `ChatMessage.suggested_options` 필드 추가 |
| `frontend/src/components/ChatWindow.tsx` | AI 메시지 하단 선택지 칩 렌더링 + 클릭 시 메시지 자동 전송 |
| `frontend/src/components/ArticleItemsModal.tsx` | 조항별 구조화 선택 UI 추가 (금액·기간·방법 등) |
| `frontend/src/api.ts` | `suggested_options` 응답 처리 |
| `app/api/schemas.py` | `ChatResponse.suggested_options` 필드 추가 |
| `app/graph/nodes/interviewer.py` | 질문별 `suggested_options` 데이터 생성 로직 추가 |
| `app/prompts/drafting_agent.py` | 구조화 article_contents 처리 (선택값 포함) 프롬프트 업데이트 |

### 제외

- LangGraph 워크플로우 구조 변경 없음 (노드 추가/삭제 없음)
- Neo4j 쿼리 변경 없음
- 채팅 대화 경로 제거 없음 (완전 대체가 아닌 병존)
- 기본정보 마법사 UI 별도 화면으로 분리 없음 (채팅 내 삽입 방식)

---

## 3. 상세 요구사항

### 3.1 채팅 선택지 칩 (기본정보 수집 단계)

#### 요구사항

**R-01**: `ChatResponse`에 `suggested_options?: SuggestedOption[]` 필드 추가

```typescript
interface SuggestedOption {
  label: string   // 표시 텍스트: "보조금 지급"
  value: string   // 전송 값: "보조금 지급" (label과 동일하거나 더 상세한 표현)
}
```

**R-02**: `interviewer.py`가 각 누락 필드별 선택지를 생성

| 필드 | 선택지 예시 |
|------|------------|
| `support_type` | 보조금 지급, 현물 지원, 바우처, 교육·컨설팅, 시설 이용권 |
| `target_group` | 청년(19~39세), 노인(65세 이상), 장애인, 소상공인, 다문화가족 |
| `purpose` | 창업 지원, 주거 안정, 복지 증진, 경제 활성화, 문화·체육 활동 |
| `region` | 서울특별시, 부산광역시, (기타 광역시) — 직접 입력 유도 |

**R-03**: AI 메시지 하단에 칩 버튼이 렌더링되고, 클릭 시 `value`가 입력창에 채워지며 자동 전송

**R-04**: 선택지 클릭 후 해당 칩 비활성화 (중복 선택 방지)

**R-05**: 입력창에 직접 타이핑도 여전히 가능 (칩 클릭과 직접 입력 공존)

#### 동작 시나리오

```
AI: "어떤 지원 방식을 원하시나요?"
    [보조금 지급] [현물 지원] [바우처] [교육·컨설팅] [시설 이용권]

사용자: "보조금 지급" 칩 클릭
→ 입력창에 "보조금 지급" 자동 입력 후 전송
→ intent_analyzer 노드 → support_type = "보조금 지급" 추출
→ 다음 질문으로 진행 (기존 flow 그대로)
```

---

### 3.2 조항 구조화 선택 UI (ArticleItemsModal)

#### 요구사항

**R-06**: 9개 조항 중 구조화 입력이 유의미한 **5개 조항**에 선택 UI 추가

| 조항 | 구조화 입력 유형 | 선택지/입력 |
|------|----------------|-------------|
| **지원금액** | 금액 범위 칩 + 숫자 직접입력 | [100만원] [300만원] [500만원] [1,000만원] / 지원기간: [1년] [2년] [3년] / 지원비율: [50%] [70%] [100%] |
| **지원내용** | 다중 선택 체크박스 칩 | 창업 초기비용, 임대료, 교육비, 장비 구입, 마케팅비 |
| **신청방법** | 다중 선택 체크박스 칩 | 방문 접수, 온라인 접수, 우편 접수 |
| **심사선정** | 단일 선택 칩 | 서류 심사, 발표 심사, 서류+발표 혼합, 선착순 |
| **환수제재** | 미리 정의된 표준 조항 선택 | 표준 환수 조항 사용, 직접 작성 |

**R-07**: 구조화 선택 UI는 텍스트에어리어 **위에** 배치. 선택값이 있으면 텍스트에어리어를 채우거나 힌트로 표시

**R-08**: 기존 "AI에게 맡기기(기본값)" 버튼은 유지

**R-09**: 구조화 선택값 + 텍스트에어리어 값이 함께 `article_contents`에 포함되어 전송

```typescript
// articles_batch 전송 시 구조화 데이터 포함
interface StructuredArticleContent {
  structured?: Record<string, string | string[]>  // 선택값 모음
  text?: string                                    // 자유 입력 텍스트
}
// article_contents 값: string(기존) | StructuredArticleContent(신규) | null(AI 자동)
```

**R-10**: `drafting_agent` 프롬프트 업데이트 — 구조화 데이터를 법적 조문으로 변환

```
입력 예시:
지원금액: { structured: { amount: "500만원", period: "2년", ratio: "70%" }, text: "" }

출력 조문 예시:
"제5조(지원금액) ① 시장은 제4조의 지원 대상자에게 예산 범위 내에서
총 사업비의 100분의 70 이내의 금액을 지원할 수 있다. 다만, 1인당
지원금액은 500만원을 초과할 수 없다.
② 지원 기간은 최대 2년으로 하되..."
```

---

### 3.3 선택지 데이터 관리

**R-11**: 선택지 데이터는 **프론트엔드에 정적 상수**로 관리 (백엔드 DB 조회 없음, Phase 1)

```typescript
// frontend/src/constants/interviewOptions.ts
export const SUPPORT_TYPE_OPTIONS = [
  { label: '보조금 지급', value: '보조금 지급' },
  { label: '현물 지원', value: '현물 지원 (물품, 서비스 등)' },
  ...
]
```

**R-12**: 백엔드 `interviewer.py`는 질문 텍스트와 함께 해당 필드명을 포함한 응답 반환

```python
# interviewer.py 응답 예시 (suggested_options는 field_name 기반으로 생성)
{
  "response_to_user": "어떤 지원 방식을 원하시나요?",
  "suggested_options": [
    {"label": "보조금 지급", "value": "보조금 지급"},
    {"label": "현물 지원", "value": "현물 지원"},
    ...
  ]
}
```

---

## 4. 비기능 요구사항

| 항목 | 요구사항 |
|------|---------|
| **하위 호환성** | `suggested_options` 없는 기존 응답도 정상 처리 (optional 필드) |
| **모바일 대응** | 칩 버튼 줄 바꿈 처리 (flex-wrap), 터치 타겟 44px 이상 |
| **성능** | 선택지 렌더링이 채팅 메시지 로딩을 블로킹하지 않음 |
| **접근성** | 칩 버튼에 `aria-label` 적용, 키보드 탭 이동 가능 |

---

## 5. 구현 순서 (우선순위)

```
Phase 1 (MVP)
├── [1] 백엔드: ChatResponse에 suggested_options 필드 추가 (schemas.py)
├── [2] 백엔드: interviewer.py — 4개 필드별 suggested_options 생성
├── [3] 프론트: SuggestedOption 타입 + ChatWindow 칩 렌더링
├── [4] 프론트: 칩 클릭 → 메시지 자동 전송 처리
├── [5] 프론트: ArticleItemsModal — 지원금액 구조화 UI 추가
└── [6] 프론트: ArticleItemsModal — 지원내용, 신청방법 구조화 UI 추가

Phase 2 (후속)
├── [7] 백엔드: drafting_agent 프롬프트 — 구조화 데이터 처리 업데이트
├── [8] 프론트: 심사선정, 환수제재 구조화 UI
└── [9] 선택지 데이터 다국어 확장 또는 DB 연동
```

---

## 6. 리스크

| 리스크 | 가능성 | 영향 | 대응 |
|--------|--------|------|------|
| 선택지 클릭 후 intent_analyzer가 잘못 파싱 | 낮음 | 중간 | value를 명확한 법률 용어로 설정, intent_analyzer 프롬프트에 예시 추가 |
| 구조화 데이터 형식 변경으로 기존 세션 호환 깨짐 | 낮음 | 중간 | article_contents 값 타입을 union으로 처리, 기존 string 형식 병행 지원 |
| 선택지가 너무 많아 인지 부하 증가 | 중간 | 낮음 | 칩은 최대 5개로 제한, 나머지는 "직접 입력" 유도 |
| 모달 레이아웃 깨짐 (구조화 UI 추가) | 중간 | 낮음 | 기존 스크롤 영역 높이 조정, 가이드 패널 maxHeight 유지 |

---

## 7. 성공 기준

1. **기본정보 완성률**: 선택지 칩으로만 4개 필드 모두 완성 가능
2. **조항 입력 속도**: "지원금액" 조항을 칩 클릭만으로 30초 내 입력 완료 가능
3. **하위 호환성**: 기존 방식(직접 타이핑)이 그대로 동작
4. **초안 품질**: 구조화 데이터 입력 시 drafting_agent 출력이 기존 대비 동등 이상

---

## 8. 관련 파일

| 파일 | 역할 |
|------|------|
| `app/api/schemas.py` | `SuggestedOption` 모델, `ChatResponse` 필드 추가 |
| `app/graph/nodes/interviewer.py` | 필드별 선택지 생성 로직 |
| `app/prompts/drafting_agent.py` | 구조화 데이터 처리 프롬프트 업데이트 |
| `frontend/src/types.ts` | `SuggestedOption`, `ChatMessage` 타입 확장 |
| `frontend/src/components/ChatWindow.tsx` | 칩 렌더링 + 클릭 핸들러 |
| `frontend/src/components/ArticleItemsModal.tsx` | 조항별 구조화 선택 UI |
| `frontend/src/constants/interviewOptions.ts` | 선택지 정적 데이터 (신규) |
