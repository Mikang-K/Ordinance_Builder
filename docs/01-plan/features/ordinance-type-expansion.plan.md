# Plan: 조례 유형 확장 (ordinance-type-expansion)

**작성일**: 2026-04-25  
**상태**: Planning  
**단계**: Plan

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **문제** | 현재 시스템이 "지원 조례" 한 가지 유형만 가정하고 설계되어, 설치·운영/관리·규제/복지·서비스 등 다른 유형의 조례를 작성하려는 사용자가 맞지 않는 조항 템플릿을 강요받음 |
| **해결** | `ordinance_type` 필드를 State에 추가하고, OnboardingWizard 첫 단계에서 유형을 선택하게 한 뒤, 유형별로 조항 템플릿·구조화 UI·AI 프롬프트를 분기 |
| **기능 UX 효과** | 조례 유형에 맞는 조항 목록과 입력 가이드 제공 → 법률 비전문가도 올바른 조문 구조로 초안 작성 가능 |
| **핵심 가치** | 지방 조례의 다양한 유형(지원·설치운영·규제·복지)을 하나의 플로우로 커버하여 서비스 적용 범위를 4배 확장 |

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | 실제 지방 조례는 지원 조례 외에도 위원회 설치·운영, 시설 관리·규제, 복지서비스 제공 등 다양한 유형이 존재하며 각각 조문 구조가 상이함 |
| **WHO** | 지자체 담당 공무원, 지방의원 보좌 인력 — 특히 설치·운영/규제/복지 조례를 처음 작성하는 비전문가 |
| **RISK** | 기존 세션(지원 조례 전제)과의 State 호환 / article_planner 분기 로직 복잡도 증가 / 신규 조항의 structured options 미비 |
| **SUCCESS** | 4가지 유형 각각에서 조항 템플릿이 올바르게 표시되고 완성된 초안이 생성됨 |
| **SCOPE** | 백엔드(State + article_planner + drafting_agent) + 프론트엔드(OnboardingWizard + ArticleItemsModal + interviewOptions) 전체 |

---

## 1. 배경 및 목표

### 현재 문제

`article_planner.py`는 `support_type` 키워드 기반으로 조항 수를 결정하는 단일 로직만 존재:

```python
# 현재 분기 — 모두 "지원 조례" 전제
if "컨설팅" in support_type or "멘토링" in support_type:
    order = [목적, 정의, 지원대상, 지원내용, 신청방법, 위임]  # 6개
elif "시설" in support_type:
    order = [목적, 정의, 지원대상, 지원내용, 지원금액, 신청방법, 심사선정, 위임]  # 8개
else:
    order = DEFAULT_ARTICLE_ORDER  # 9개 (지원 조례 표준)
```

**문제점**:
- 설치·운영 조례는 "위원회 구성/직무/운영/간사"가 필수이지만 지원 조례 템플릿에 없음
- 관리·규제 조례는 "사용허가/사용료/위반제재"가 필요하지만 "환수제재"와 구조가 다름
- 복지·서비스 조례는 "서비스내용/제공기관/비용"이 필요하지만 "지원내용/지원금액"과 명칭이 다름

### 목표

1. `OrdinanceBuilderState`에 `ordinance_type` 필드 추가
2. `OnboardingWizard`의 첫 번째 단계를 "조례 유형 선택"으로 추가
3. `article_planner`가 `ordinance_type` 기반으로 올바른 조항 목록 분기
4. `ArticleItemsModal` 가이드 텍스트와 구조화 선택 UI를 유형별로 제공
5. `drafting_agent` 프롬프트에 조례 유형 컨텍스트 전달

---

## 2. 범위 (Scope)

### 포함

| 구성요소 | 변경 내용 |
|----------|-----------|
| `app/graph/state.py` | `ordinance_type: Optional[str]` 필드 추가 |
| `app/graph/nodes/intent_analyzer.py` | `ordinance_type` 추출 로직 추가 (`ExtractedInfo` 모델 확장) |
| `app/graph/nodes/article_planner.py` | `ordinance_type` 기반 4종 템플릿 분기 + `ARTICLE_TEMPLATES` 확장 |
| `app/prompts/drafting_agent.py` | `build_drafting_human()`에 `ordinance_type` 파라미터 추가 + 유형별 시스템 힌트 |
| `app/api/schemas.py` | `ChatResponse`, `SessionCreateResponse`, `SessionStateResponse`에 `ordinance_type` 필드 추가 |
| `app/api/routers/chat.py` | 각 핸들러에서 `ordinance_type` 반환 |
| `frontend/src/types.ts` | `ordinance_type?: string \| null` 필드 추가 |
| `frontend/src/App.tsx` | `ordinanceType` 상태 추가 + applyResponse/handleSelectSession 반영 |
| `frontend/src/components/OnboardingWizard.tsx` | Step 0 "조례 유형 선택" 추가 (4개 유형 칩) |
| `frontend/src/constants/interviewOptions.ts` | 신규 조항(설치, 구성, 직무, 운영, 적용범위 등)에 대한 가이드·구조화 옵션 추가 |
| `frontend/src/components/ArticleItemsModal.tsx` | `ARTICLE_GUIDES` 유형별 분기 또는 공용 가이드 확장 |

### 제외

- LangGraph 워크플로우 노드·엣지 구조 변경 없음 (분기는 `article_planner` 내부에서만)
- Neo4j 쿼리 및 graph_retriever 변경 없음 (유형 무관 탐색)
- 기존 `지원 조례` 세션 데이터 마이그레이션 없음 (null 방어 코드로 하위 호환)
- 조례 유형별 법령 근거 데이터 분리 없음 (Phase 2 과제)

---

## 3. 조례 유형별 설계

### 3.1 지원 조례 (기존 유지)

| 조항 | 키 | 구조화 UI |
|------|-----|-----------|
| 목적 | `목적` | — |
| 정의 | `정의` | term/desc 쌍 입력 |
| 지원대상 | `지원대상` | — |
| 지원내용 | `지원내용` | 다중 선택 칩 |
| 지원금액 | `지원금액` | 금액/기간/비율 단일 선택 칩 |
| 신청방법 | `신청방법` | 채널 다중 선택 칩 |
| 심사선정 | `심사선정` | 방식 단일 선택 칩 |
| 환수제재 | `환수제재` | — |
| 위임 | `위임` | — |

### 3.2 설치·운영 조례 (신규)

위원회·심의회·자문단 설치 및 운영 근거 조례

| 조항 | 키 | 구조화 UI |
|------|-----|-----------|
| 목적 | `목적` | — |
| 정의 | `정의` | term/desc 쌍 입력 |
| 설치 | `설치` | — |
| 구성 | `구성` | 위원 수·임기 단일 선택 칩 |
| 직무 | `직무` | — |
| 운영 | `운영` | 회의 주기 단일 선택 칩 |
| 간사 | `간사` | — |
| 위임 | `위임` | — |

### 3.3 관리·규제 조례 (신규)

공공시설 관리, 허가·금지·제재를 규율하는 조례

| 조항 | 키 | 구조화 UI |
|------|-----|-----------|
| 목적 | `목적` | — |
| 정의 | `정의` | term/desc 쌍 입력 |
| 적용범위 | `적용범위` | — |
| 관리책임 | `관리책임` | — |
| 사용허가 | `사용허가` | — |
| 사용료 | `사용료` | 요금 기준 단일 선택 칩 |
| 위반제재 | `위반제재` | 과태료 상한 단일 선택 칩 |
| 위임 | `위임` | — |

### 3.4 복지·서비스 조례 (신규)

복지서비스 제공 기준과 절차를 정하는 조례

| 조항 | 키 | 구조화 UI |
|------|-----|-----------|
| 목적 | `목적` | — |
| 정의 | `정의` | term/desc 쌍 입력 |
| 지원대상 | `지원대상` | — |
| 서비스내용 | `서비스내용` | 서비스 유형 다중 선택 칩 |
| 제공기관 | `제공기관` | — |
| 신청접수 | `신청접수` | 접수 채널 다중 선택 칩 |
| 비용 | `비용` | 본인부담 방식 단일 선택 칩 |
| 위임 | `위임` | — |

---

## 4. 상세 요구사항

### 4.1 State 및 백엔드

**R-01**: `OrdinanceBuilderState`에 `ordinance_type: Optional[str]` 추가 (기본값 `None`)

```python
class OrdinanceBuilderState(TypedDict):
    ...
    ordinance_type: Optional[str]  # "지원", "설치·운영", "관리·규제", "복지·서비스"
```

**R-02**: `intent_analyzer`의 `ExtractedInfo` 모델에 `ordinance_type` 추가, Gemini가 메시지에서 유형 추출

```python
class ExtractedInfo(BaseModel):
    region: Optional[str]
    purpose: Optional[str]
    target_group: Optional[str]
    support_type: Optional[str]
    ordinance_type: Optional[str]  # 신규
```

**R-03**: `article_planner`가 `ordinance_type` 기반으로 4종 분기

```python
TYPE_ARTICLE_ORDER = {
    "설치·운영": ["목적", "정의", "설치", "구성", "직무", "운영", "간사", "위임"],
    "관리·규제": ["목적", "정의", "적용범위", "관리책임", "사용허가", "사용료", "위반제재", "위임"],
    "복지·서비스": ["목적", "정의", "지원대상", "서비스내용", "제공기관", "신청접수", "비용", "위임"],
}
# 지원 조례 or None → 기존 로직 유지
```

**R-04**: `build_drafting_human()`에 `ordinance_type` 파라미터 추가 — 시스템 힌트로 포함

**R-05**: `ChatResponse`, `SessionCreateResponse`, `SessionStateResponse`에 `ordinance_type: Optional[str]` 필드 추가

### 4.2 OnboardingWizard

**R-06**: 기존 4개 Step 앞에 Step 0 "조례 유형 선택" 추가 (총 5 Steps)

```
STEPS[0]: ordinance_type 선택
  - 지원 조례 (지원금, 보조금, 인프라 등 지원)
  - 설치·운영 조례 (위원회, 자문단, 심의회 설치)
  - 관리·규제 조례 (시설 관리, 허가, 제재)
  - 복지·서비스 조례 (복지 서비스 제공 기준)

STEPS[1~4]: region, purpose, target_group, support_type
  (지원 조례가 아닌 경우 purpose/target_group/support_type 레이블을 유형에 맞게 조정)
```

**R-07**: 유형 선택에 따라 이후 Step의 `title`/`description`을 동적으로 변경

| 단계 | 지원 조례 | 설치·운영 조례 | 관리·규제 조례 | 복지·서비스 조례 |
|------|-----------|--------------|--------------|--------------|
| purpose | 어떤 목적의 조례인가요? | 어떤 위원회·기관을 설치하나요? | 어떤 시설·대상을 관리하나요? | 어떤 복지 서비스를 제공하나요? |
| target_group | 주요 지원 대상 | 위원회 참여 대상 | 관리 대상 시설·단체 | 서비스 수혜 대상 |
| support_type | 지원 방식 | 운영 방식 | 규제·관리 방식 | 서비스 제공 방식 |

**R-08**: `handleSubmit()`이 생성하는 메시지에 `ordinance_type` 포함

```typescript
// 지원 조례
"서울특별시에서 청년 창업 지원 조례를 만들고 싶습니다. ..."
// 설치·운영 조례
"경기도에서 청년정책위원회 설치·운영 조례를 만들고 싶습니다. ..."
```

### 4.3 ArticleItemsModal 및 interviewOptions

**R-09**: `interviewOptions.ts`의 `ARTICLE_STRUCTURED_OPTIONS`에 신규 조항 추가

| 신규 조항 | 구조화 옵션 |
|-----------|------------|
| `구성` | 위원수: [5인, 7인, 9인, 11인], 임기: [1년, 2년, 3년] |
| `운영` | 회의주기: [월 1회, 분기 1회, 반기 1회, 필요 시] |
| `사용료` | 기준: [시간제, 일제, 월제, 연제] |
| `위반제재` | 과태료: [50만원, 100만원, 200만원, 500만원] |
| `서비스내용` | 유형: [방문 돌봄, 주거 지원, 의료비 지원, 식사 제공, 심리 상담] 다중 선택 |
| `신청접수` | 채널: [방문, 온라인, 전화, 우편] 다중 선택 |
| `비용` | 본인부담: [무료, 소득 연동, 정액] |

**R-10**: `ARTICLE_GUIDES` (가이드 텍스트)를 신규 조항에 대해 추가

### 4.4 하위 호환성

**R-11**: `ordinance_type`이 `None`인 기존 세션은 현재 `article_planner` 로직(`support_type` 기반 분기)으로 폴백

```python
def article_planner_node(state):
    ordinance_type = state.get("ordinance_type")
    if ordinance_type and ordinance_type in TYPE_ARTICLE_ORDER:
        order = TYPE_ARTICLE_ORDER[ordinance_type]
    else:
        # 기존 로직 유지
        order = _legacy_order(state.get("support_type", ""))
```

**R-12**: 프론트엔드에서 `ordinance_type`이 없는 세션 복원 시 오류 없이 처리 (`?? null` 방어)

---

## 5. 구현 순서 (모듈별)

```
M1 — 백엔드 State + 데이터 흐름
├── state.py: ordinance_type 필드 추가
├── intent_analyzer.py: ExtractedInfo 모델 + 추출 로직
├── schemas.py: 3개 Response 스키마 필드 추가
└── routers/chat.py: 핸들러 반환값 추가

M2 — article_planner 4종 분기
├── article_planner.py: TYPE_ARTICLE_ORDER 상수 + 분기 로직
└── ARTICLE_TEMPLATES에 신규 조항 기본 힌트 추가

M3 — OnboardingWizard Step 0 추가
├── OnboardingWizard.tsx: STEPS 배열 재구성 (Step 0 + 동적 Step 1~4)
└── App.tsx: ordinanceType 상태 + applyResponse 반영

M4 — 프론트엔드 신규 조항 UI
├── interviewOptions.ts: ARTICLE_STRUCTURED_OPTIONS 신규 조항 추가
└── ArticleItemsModal.tsx: ARTICLE_GUIDES 신규 조항 추가

M5 — drafting_agent 프롬프트 업데이트
└── prompts/drafting_agent.py: ordinance_type 컨텍스트 + 유형별 조문 지침
```

---

## 6. 리스크

| 리스크 | 가능성 | 영향 | 대응 |
|--------|--------|------|------|
| intent_analyzer가 `ordinance_type`을 잘못 분류 | 중간 | 높음 | OnboardingWizard에서 명시 선택 → 채팅 추출보다 우선 적용 |
| 기존 세션의 `ordinance_type == None` 폴백 동작 검증 부족 | 낮음 | 중간 | R-11 폴백 코드 + 세션 복원 테스트 |
| 신규 조항(설치, 구성 등)에 대한 drafting_agent 출력 품질 | 중간 | 중간 | M5 프롬프트에 유형별 조문 예시 포함 |
| OnboardingWizard 5-Step화로 진입 장벽 증가 | 낮음 | 중간 | Step 0 조례 유형 선택을 4개 큰 칩으로 직관적 구성 |
| ArticleItemsModal 신규 조항에 구조화 옵션 없음 | 낮음 | 낮음 | 목적/정의/위임 등 범용 조항은 텍스트 입력만으로 충분 |

---

## 7. 성공 기준

1. **4종 유형** 각각에서 OnboardingWizard → 조항 입력 → 초안 생성 플로우가 오류 없이 완료
2. **기존 지원 조례 세션** 복원 및 이어쓰기가 정상 동작 (하위 호환)
3. **조항 목록 정확성**: 설치·운영 조례 선택 시 "구성/직무/운영/간사" 조항이 모달에 표시
4. **초안 품질**: 설치·운영 조례에서 위원회 설치·구성·운영 조문이 법적 형식으로 생성

---

## 8. 관련 파일

| 파일 | 역할 |
|------|------|
| `app/graph/state.py` | `ordinance_type` 필드 추가 |
| `app/graph/nodes/intent_analyzer.py` | `ExtractedInfo` 모델 + 유형 추출 |
| `app/graph/nodes/article_planner.py` | 4종 분기 로직 + 신규 조항 템플릿 |
| `app/prompts/drafting_agent.py` | 유형별 조문 지침 프롬프트 |
| `app/api/schemas.py` | Response 스키마 필드 추가 |
| `app/api/routers/chat.py` | 핸들러 반환값 추가 |
| `frontend/src/types.ts` | `ordinance_type` 필드 추가 |
| `frontend/src/App.tsx` | `ordinanceType` 상태 + 반영 로직 |
| `frontend/src/components/OnboardingWizard.tsx` | Step 0 추가 + 동적 Step 구성 |
| `frontend/src/constants/interviewOptions.ts` | 신규 조항 구조화 옵션 추가 |
| `frontend/src/components/ArticleItemsModal.tsx` | 신규 조항 가이드 텍스트 추가 |
