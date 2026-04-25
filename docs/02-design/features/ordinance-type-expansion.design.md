# Design: 조례 유형 확장 (ordinance-type-expansion)

**작성일**: 2026-04-25  
**상태**: Design  
**단계**: Design  
**선택한 아키텍처**: Option C — Pragmatic Balance

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | 현재 시스템이 "지원 조례" 한 가지 유형만 가정하고 설계되어, 설치·운영/관리·규제/복지·서비스 등 다른 유형의 조례를 작성하려는 사용자가 맞지 않는 조항 템플릿을 강요받음 |
| **WHO** | 지자체 담당 공무원, 지방의원 보좌 인력 — 특히 설치·운영/규제/복지 조례를 처음 작성하는 비전문가 |
| **RISK** | 기존 세션(지원 조례 전제)과의 State 호환 / article_planner 분기 로직 복잡도 증가 / 신규 조항의 structured options 미비 |
| **SUCCESS** | 4가지 유형 각각에서 조항 템플릿이 올바르게 표시되고 완성된 초안이 생성됨 |
| **SCOPE** | 백엔드(State + article_planner + drafting_agent) + 프론트엔드(OnboardingWizard + ArticleItemsModal + interviewOptions) 전체 |

---

## 1. Overview

### 1.1 선택 아키텍처: Option C — Pragmatic Balance

**핵심 설계 결정**:

1. **`OrdinanceBuilderState`에 `ordinance_type: Optional[str]` 최상위 필드 추가**
   - `ordinance_info` dict 안에 묻지 않고 명시적 최상위 필드로 관리 → 타입 안전
   - `None`일 때 기존 `support_type` 기반 분기로 폴백 → 하위 호환 자동 보장

2. **`article_planner.py`에 `TYPE_ARTICLE_ORDER` + 신규 `ARTICLE_TEMPLATES` 항목 추가**
   - 별도 config 모듈 없이 동일 파일 내에서 확장
   - 신규 조항 키: `설치`, `구성`, `직무`, `운영`, `간사`, `적용범위`, `관리책임`, `사용허가`, `사용료`, `위반제재`, `서비스내용`, `제공기관`, `신청접수`, `비용`

3. **`intent_analyzer.py`의 `ExtractedInfo`에 `ordinance_type` 추가**
   - OnboardingWizard에서 이미 유형 선택 → 채팅 메시지에 유형 정보 포함 → Gemini가 추출

4. **`OnboardingWizard.tsx`에 Step 0 추가 (유형 선택)**
   - 4개 유형 칩 — 선택에 따라 이후 Step 제목/예시가 동적 변경
   - `handleSubmit()`이 유형 정보를 메시지에 포함

5. **`interviewOptions.ts`에 신규 조항 구조화 옵션 추가**

### 1.2 데이터 흐름

```
[OnboardingWizard 유형 선택 흐름]
Step 0: 조례 유형 선택 (4개 칩)
  → ordinanceType state 저장
  → Step 1~4: 유형에 맞는 title/options 표시
  → handleSubmit()
  → 메시지: "{region}에서 {type} 유형 {purpose} 조례를 만들고 싶습니다..."
  → intent_analyzer: ordinance_type 추출
  → article_planner: TYPE_ARTICLE_ORDER[ordinance_type] 분기
  → ArticleItemsModal: 유형별 조항 목록 표시

[하위 호환 폴백 흐름 (기존 세션)]
ordinance_type == None
  → article_planner: _legacy_order(support_type) 그대로 실행
  → 기존 세션 영향 없음
```

---

## 2. 컴포넌트 설계

### 2.1 백엔드 변경

#### `app/graph/state.py`

```python
class OrdinanceBuilderState(TypedDict):
    ...기존 필드 유지...
    ordinance_type: Optional[str]   # 신규: "지원" | "설치·운영" | "관리·규제" | "복지·서비스" | None
```

#### `app/graph/nodes/intent_analyzer.py`

```python
class ExtractedInfo(BaseModel):
    region: Optional[str] = ...
    purpose: Optional[str] = ...
    target_group: Optional[str] = ...
    support_type: Optional[str] = ...
    budget_range: Optional[str] = ...
    industry_sector: Optional[str] = ...
    enforcement_scope: Optional[str] = ...
    ordinance_type: Optional[str] = Field(   # 신규
        None,
        description="조례 유형. '지원', '설치·운영', '관리·규제', '복지·서비스' 중 하나"
    )
    missing_fields: list[str] = ...
```

`intent_analyzer_node`에서 `ordinance_type` 머지 처리 추가:
```python
for field in [
    "region", "purpose", "target_group", "support_type",
    "budget_range", "industry_sector", "enforcement_scope",
    "ordinance_type",   # 신규
]:
    ...
return {
    "ordinance_info": updated_info,
    "ordinance_type": extracted.ordinance_type or state.get("ordinance_type"),  # 신규
    ...
}
```

#### `app/graph/nodes/article_planner.py`

```python
# 신규: 유형별 조항 순서 상수
TYPE_ARTICLE_ORDER: dict[str, list[str]] = {
    "설치·운영": ["목적", "정의", "설치", "구성", "직무", "운영", "간사", "위임"],
    "관리·규제": ["목적", "정의", "적용범위", "관리책임", "사용허가", "사용료", "위반제재", "위임"],
    "복지·서비스": ["목적", "정의", "지원대상", "서비스내용", "제공기관", "신청접수", "비용", "위임"],
}

# 신규 조항 템플릿 항목 (ARTICLE_TEMPLATES에 추가)
"설치": {
    "title": "설치 조항",
    "question": "위원회/자문단/심의회의 설치 근거와 명칭을 작성해 주세요..."
},
"구성": { ... },
"직무": { ... },
"운영": { ... },
"간사": { ... },
"적용범위": { ... },
"관리책임": { ... },
"사용허가": { ... },
"사용료": { ... },
"위반제재": { ... },
"서비스내용": { ... },
"제공기관": { ... },
"신청접수": { ... },
"비용": { ... },

# article_planner_node 분기 로직 수정
def article_planner_node(state):
    ordinance_type = state.get("ordinance_type")
    if ordinance_type and ordinance_type in TYPE_ARTICLE_ORDER:
        article_order = list(TYPE_ARTICLE_ORDER[ordinance_type])
    else:
        article_order = _legacy_order(support_type)   # 기존 로직 함수로 추출
```

#### `app/prompts/drafting_agent.py`

`build_drafting_human()`에 `ordinance_type` 파라미터 추가:

```python
def build_drafting_human(
    info: dict,
    legal_basis: list,
    similar: list,
    article_contents: dict | None = None,
    legal_terms: list | None = None,
    ordinance_type: str | None = None,    # 신규
) -> str:
    ...
    type_hint = ""
    if ordinance_type and ordinance_type != "지원":
        type_hint = f"\n\n## 조례 유형 참고\n  이 조례는 **{ordinance_type} 조례**입니다. 지원금·보조금 중심이 아닌 {ordinance_type}에 적합한 조문 구조를 사용하세요."
    ...
```

`drafting_agent_node`에서 `state.get("ordinance_type")` 전달.

#### `app/api/schemas.py`

```python
class SessionStateResponse(BaseModel):
    ...기존 필드 유지...
    ordinance_type: Optional[str] = None    # 신규

class SessionCreateResponse(BaseModel):
    ...기존 필드 유지...
    ordinance_type: Optional[str] = None    # 신규

class ChatResponse(BaseModel):
    ...기존 필드 유지...
    ordinance_type: Optional[str] = None    # 신규
```

#### `app/api/routers/chat.py`

`create_session`, `chat`, `get_session_state` 핸들러에서 `ordinance_type` 반환 추가.

---

### 2.2 프론트엔드 변경

#### `frontend/src/types.ts`

```typescript
interface SessionCreateResponse {
    ...
    ordinance_type?: string | null   // 신규
}

interface ChatResponse {
    ...
    ordinance_type?: string | null   // 신규
}

interface SessionStateResponse {
    ...
    ordinance_type?: string | null   // 신규
}
```

#### `frontend/src/components/OnboardingWizard.tsx`

현재 `STEPS` 배열(4개)을 5개로 확장 — Step 0 "조례 유형 선택" 추가:

```typescript
// Step 0: 조례 유형 선택 (칩 전용, 텍스트 입력 없음)
const ORDINANCE_TYPE_STEP = {
  field: 'ordinance_type',
  title: '어떤 종류의 조례를 만드시겠습니까?',
  description: '조례 유형을 선택하면 적합한 조항 구조로 안내해 드립니다.',
  placeholder: '',
  options: ['지원 조례', '설치·운영 조례', '관리·규제 조례', '복지·서비스 조례'],
  descriptions: {
    '지원 조례': '보조금·임대료·교육비 등 지원금을 제공하는 조례',
    '설치·운영 조례': '위원회·자문단·심의회 설치 및 운영 근거 조례',
    '관리·규제 조례': '공공시설 관리, 허가·금지·과태료 규정 조례',
    '복지·서비스 조례': '돌봄·의료비·식사 제공 등 서비스 기준 조례',
  }
}
```

Step 1~4 (region, purpose, target_group, support_type)의 `title`/`description`/`options`를 선택된 유형에 따라 동적으로 결정:

```typescript
// 유형별 Step 오버라이드 설정
const TYPE_STEP_CONFIG: Record<string, Partial<Step>[]> = {
  '설치·운영 조례': [
    {},  // region: 동일
    { title: '어떤 기관을 설치하시겠습니까?', placeholder: '예: 청년정책위원회', options: ['청년정책위원회', '산업진흥위원회', '복지심의위원회', '문화예술위원회'] },
    { title: '위원회 참여 대상은 누구입니까?', placeholder: '예: 관련 분야 전문가 및 공무원', options: ['전문가 및 공무원', '지역 주민 대표', '민간 전문가', '관계 기관 임직원'] },
    { title: '어떤 방식으로 운영하시겠습니까?', placeholder: '예: 분기별 정기회의', options: ['월 1회 정기회의', '분기 1회 정기회의', '반기 1회 정기회의', '필요 시 수시 개최'] },
  ],
  '관리·규제 조례': [
    {},
    { title: '어떤 시설·대상을 관리하시겠습니까?', placeholder: '예: 공공체육시설', options: ['공공체육시설', '문화시설', '공원·녹지', '공유재산'] },
    { title: '관리 대상 주체는 누구입니까?', placeholder: '예: 민간 위탁 사업자', options: ['민간 위탁 사업자', '지역 주민', '기업·법인', '비영리단체'] },
    { title: '어떤 방식으로 규제하시겠습니까?', placeholder: '예: 사용허가 + 사용료 부과', options: ['사용허가제', '등록·신고제', '과태료 부과', '사용료 징수'] },
  ],
  '복지·서비스 조례': [
    {},
    { title: '어떤 복지 서비스를 제공하시겠습니까?', placeholder: '예: 노인 돌봄 서비스', options: ['노인 돌봄 서비스', '장애인 지원 서비스', '아동·청소년 서비스', '저소득층 지원'] },
    { title: '서비스 수혜 대상은 누구입니까?', placeholder: '예: 만 65세 이상 독거노인', options: ['노인(65세 이상)', '장애인', '저소득 가정', '한부모 가정'] },
    { title: '어떤 방식으로 서비스를 제공하시겠습니까?', placeholder: '예: 방문 돌봄 서비스', options: ['방문 제공', '시설 이용', '바우처 지급', '현물 지원'] },
  ],
}
// 지원 조례: 기존 STEPS 그대로
```

`handleSubmit()`이 생성하는 메시지에 유형 포함:
```typescript
const type = textInputs['ordinance_type']?.trim() || selections['ordinance_type'] || '지원 조례'
const typeLabel = type === '지원 조례' ? '지원' : type.replace(' 조례', '')
const msg = `${region}에서 ${typeLabel} 유형의 ${purpose} 조례를 만들고 싶습니다. 대상은 ${target}이며, ${support} 방식으로 진행합니다. (조례유형: ${type})`
```

#### `frontend/src/App.tsx`

```typescript
// 신규 상태
const [ordinanceType, setOrdinanceType] = useState<string | null>(null)

// applyResponse에 추가
if (res.ordinance_type != null) setOrdinanceType(res.ordinance_type)

// handleSelectSession에 추가
if (state.ordinance_type != null) setOrdinanceType(state.ordinance_type)

// resetState에 추가
setOrdinanceType(null)
```

#### `frontend/src/constants/interviewOptions.ts`

신규 조항에 대한 `ARTICLE_STRUCTURED_OPTIONS` 항목 추가:

```typescript
구성: {
  fields: [
    { key: '위원수', label: '위원 수', type: 'single', options: ['5인 이내', '7인 이내', '9인 이내', '11인 이내'] },
    { key: '임기', label: '임기', type: 'single', options: ['1년', '2년', '3년'] },
  ]
},
운영: {
  fields: [
    { key: '회의주기', label: '회의 주기', type: 'single', options: ['월 1회', '분기 1회', '반기 1회', '필요 시 수시'] },
  ]
},
사용료: {
  fields: [
    { key: '기준', label: '요금 기준', type: 'single', options: ['시간제', '일제', '월제', '연제'] },
  ]
},
위반제재: {
  fields: [
    { key: '과태료', label: '과태료 상한', type: 'single', options: ['50만원 이하', '100만원 이하', '200만원 이하', '500만원 이하'] },
  ]
},
서비스내용: {
  fields: [
    { key: 'items', label: '서비스 유형', type: 'multi', options: ['방문 돌봄', '주거 지원', '의료비 지원', '식사 제공', '심리 상담', '이동 지원'] },
  ]
},
신청접수: {
  fields: [
    { key: 'channels', label: '접수 채널', type: 'multi', options: ['방문 접수', '온라인 접수', '전화 신청', '우편 접수'] },
  ]
},
비용: {
  fields: [
    { key: '부담방식', label: '본인부담 방식', type: 'single', options: ['무료', '소득 연동 차등', '정액 본인부담'] },
  ]
},
```

---

## 3. API 설계

### 3.1 변경 엔드포인트

모든 엔드포인트는 기존 경로 유지. 응답 스키마에 `ordinance_type` 추가만.

| 엔드포인트 | 스키마 변경 |
|-----------|------------|
| `POST /api/v1/session` | `SessionCreateResponse.ordinance_type` 추가 |
| `POST /api/v1/session/{id}/chat` | `ChatResponse.ordinance_type` 추가 |
| `GET /api/v1/session/{id}` | `SessionStateResponse.ordinance_type` 추가 |

### 3.2 스키마 변경 요약

```python
# 3개 Response 모두 동일 패턴
ordinance_type: Optional[str] = None
```

**하위 호환**: `None` 기본값 → 기존 클라이언트 영향 없음.

---

## 4. 상태 머신 변경

### 4.1 LangGraph 워크플로우 — 변경 없음

노드·엣지 구조 변경 없음. `article_planner_node` 내부 로직만 확장.

### 4.2 `OrdinanceBuilderState` 확장

```
기존: ordinance_info(dict) ← region/purpose/target_group/support_type 포함
신규: ordinance_type(str | None) ← 최상위 독립 필드
```

### 4.3 폴백 보장

```python
if ordinance_type and ordinance_type in TYPE_ARTICLE_ORDER:
    article_order = TYPE_ARTICLE_ORDER[ordinance_type]
else:
    # 기존 로직 그대로 (support_type 키워드 기반)
    if "컨설팅" in support_type or ...:
        article_order = [...]
    elif "시설" in support_type:
        article_order = [...]
    else:
        article_order = list(DEFAULT_ARTICLE_ORDER)
```

---

## 5. 데이터 모델

### 5.1 신규 조항 템플릿 목록

| 조항 키 | 유형 | 조문 제목 예시 |
|---------|------|--------------|
| `설치` | 설치·운영 | 설치 조항 |
| `구성` | 설치·운영 | 구성 조항 |
| `직무` | 설치·운영 | 직무 조항 |
| `운영` | 설치·운영 | 운영 조항 |
| `간사` | 설치·운영 | 간사 조항 |
| `적용범위` | 관리·규제 | 적용 범위 조항 |
| `관리책임` | 관리·규제 | 관리 책임 조항 |
| `사용허가` | 관리·규제 | 사용 허가 조항 |
| `사용료` | 관리·규제 | 사용료 조항 |
| `위반제재` | 관리·규제 | 위반 및 제재 조항 |
| `서비스내용` | 복지·서비스 | 서비스 내용 조항 |
| `제공기관` | 복지·서비스 | 서비스 제공 기관 조항 |
| `신청접수` | 복지·서비스 | 신청 및 접수 조항 |
| `비용` | 복지·서비스 | 비용 및 본인부담 조항 |

---

## 6. 파일 수정 목록

| 파일 | 변경 유형 | 주요 변경 내용 |
|------|-----------|--------------|
| `app/graph/state.py` | 수정 | `ordinance_type: Optional[str]` 추가 |
| `app/graph/nodes/intent_analyzer.py` | 수정 | `ExtractedInfo.ordinance_type` + 머지 로직 |
| `app/graph/nodes/article_planner.py` | 수정 | `TYPE_ARTICLE_ORDER` + 14개 신규 템플릿 + 분기 로직 |
| `app/graph/nodes/drafting_agent.py` | 수정 | `ordinance_type` 파라미터 + 유형별 힌트 |
| `app/prompts/drafting_agent.py` | 수정 | `build_drafting_human()` 파라미터 추가 |
| `app/api/schemas.py` | 수정 | 3개 Response에 `ordinance_type` 필드 추가 |
| `app/api/routers/chat.py` | 수정 | 3개 핸들러에서 `ordinance_type` 반환 |
| `frontend/src/types.ts` | 수정 | 3개 인터페이스에 `ordinance_type` 추가 |
| `frontend/src/App.tsx` | 수정 | `ordinanceType` 상태 추가 + 3곳 반영 |
| `frontend/src/components/OnboardingWizard.tsx` | 수정 | Step 0 추가 + 동적 Step 구성 |
| `frontend/src/constants/interviewOptions.ts` | 수정 | 7개 신규 조항 구조화 옵션 추가 |

**신규 파일 없음.**

---

## 7. 테스트 계획

### L1 — 백엔드 유닛 테스트

| 테스트 | 검증 내용 |
|--------|---------|
| `article_planner_node(ordinance_type="설치·운영")` | article_order == ["목적","정의","설치","구성","직무","운영","간사","위임"] |
| `article_planner_node(ordinance_type=None)` | 기존 DEFAULT_ARTICLE_ORDER 반환 |
| `intent_analyzer` 메시지 "설치·운영 유형" | `ordinance_type == "설치·운영"` 추출 |

### L2 — API 계약 테스트

| 엔드포인트 | 검증 |
|-----------|------|
| `POST /api/v1/session` 응답 | `ordinance_type` 필드 존재 (null 허용) |
| `GET /api/v1/session/{id}` 복원 | `ordinance_type` 올바르게 반환 |

### L3 — E2E 시나리오

| 시나리오 | 기대 결과 |
|---------|---------|
| OnboardingWizard → "설치·운영 조례" 선택 → 완료 | ArticleItemsModal에 "구성/직무/운영/간사" 조항 표시 |
| 기존 지원 조례 세션 복원 | 기존 조항 목록 그대로 표시 |
| 관리·규제 조례 → 초안 생성 | "사용허가/사용료/위반제재" 조문 포함된 초안 생성 |

---

## 8. 리스크 및 완화

| 리스크 | 완화 방안 |
|--------|---------|
| `ordinance_type`이 OnboardingWizard에서만 설정되고 채팅 경로에서는 누락 | `intent_analyzer`에서 메시지 텍스트로부터도 추출 + 기존 폴백 보장 |
| 신규 조항 템플릿에 대한 `drafting_agent` 출력 품질 미검증 | `drafting_agent.py` 프롬프트에 유형별 조문 예시 포함 |
| `article_planner`에서 신규 조항 키가 `ARTICLE_TEMPLATES`에 없을 시 KeyError | 신규 14개 조항 모두 `ARTICLE_TEMPLATES`에 추가 후 테스트 |
| 프론트엔드 `ordinanceType` 상태가 세션 리셋 시 누락 | `resetState()`에 `setOrdinanceType(null)` 포함 |

---

## 9. 구현 가이드

### 9.1 구현 순서 (의존성 순)

```
[1] state.py: ordinance_type 필드 추가
[2] intent_analyzer.py: ExtractedInfo + 머지 로직
[3] article_planner.py: TYPE_ARTICLE_ORDER + 14개 신규 ARTICLE_TEMPLATES + 분기 로직
[4] drafting_agent.py + prompts/drafting_agent.py: ordinance_type 파라미터
[5] schemas.py: 3개 Response 필드 추가
[6] routers/chat.py: 3개 핸들러 반환값
[7] types.ts: 3개 인터페이스 필드 추가
[8] App.tsx: ordinanceType 상태 + 반영
[9] OnboardingWizard.tsx: Step 0 + 동적 Step
[10] interviewOptions.ts: 7개 신규 조항 옵션
```

### 9.2 구현 시 주의사항

- `article_planner.py` — `ARTICLE_TEMPLATES[key]` 참조 전에 반드시 해당 키가 dict에 있는지 확인. 신규 조항 14개 모두 추가 완료 후 분기 로직 연결.
- `intent_analyzer_node` — `ordinance_type`은 `ordinance_info` dict가 아닌 State 최상위로 반환해야 함. `return { ..., "ordinance_type": ... }`.
- `routers/chat.py` — `get_session_state`, `create_session`, `chat` 세 핸들러 모두 업데이트 (CLAUDE.md §10 패턴 참고).
- `App.tsx` — `applyResponse`, `handleSelectSession`, `resetState` 세 곳에서 `ordinanceType` 반영.

### 9.3 Session Guide

| Module | 범위 | 예상 시간 |
|--------|------|---------|
| M1 — 백엔드 State + 추출 | state.py, intent_analyzer.py | 20분 |
| M2 — article_planner 확장 | article_planner.py (14개 템플릿) | 40분 |
| M3 — API 스키마 + 라우터 | schemas.py, routers/chat.py | 15분 |
| M4 — 프론트엔드 State + 타입 | types.ts, App.tsx | 15분 |
| M5 — OnboardingWizard Step 0 | OnboardingWizard.tsx | 30분 |
| M6 — interviewOptions 확장 | interviewOptions.ts | 20분 |
| M7 — drafting_agent 프롬프트 | drafting_agent.py, prompts/ | 20분 |

**권장 세션 분할**:
- Session 1: M1 + M2 + M3 (백엔드 완성)
- Session 2: M4 + M5 + M6 + M7 (프론트엔드 완성)
