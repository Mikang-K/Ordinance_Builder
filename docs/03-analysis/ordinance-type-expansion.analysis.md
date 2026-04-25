# Analysis: 조례 유형 확장 (ordinance-type-expansion)

> **Status**: Complete
>
> **Analysis Date**: 2026-04-25
> **Method**: Static Analysis (gap-detector agent)
> **Match Rate**: 100%

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

## Match Rate

```
Overall Match Rate: 100%
─────────────────────────────────────────────
Structural  (×0.2): 100%  11/11 파일 요구사항 충족
Functional  (×0.4): 100%  모든 분기 로직 완성, placeholder 없음
Contract    (×0.4): 100%  3-way API 계약 일치 (Design ↔ Server ↔ Client)
─────────────────────────────────────────────
Overall = (1.00×0.2) + (1.00×0.4) + (1.00×0.4) = 1.00
```

---

## 파일별 분석 결과

| # | 파일 | Structural | Functional | Contract | 상태 |
|---|------|:----------:|:----------:|:--------:|:----:|
| 1 | `app/graph/state.py` | ✅ | ✅ | N/A | ✅ |
| 2 | `app/graph/nodes/intent_analyzer.py` | ✅ | ✅ | N/A | ✅ |
| 3 | `app/graph/nodes/article_planner.py` | ✅ | ✅ | N/A | ✅ |
| 4 | `app/graph/nodes/drafting_agent.py` | ✅ | ✅ | N/A | ✅ |
| 5 | `app/prompts/drafting_agent.py` | ✅ | ✅ | N/A | ✅ |
| 6 | `app/api/schemas.py` | ✅ | ✅ | ✅ | ✅ |
| 7 | `app/api/routers/chat.py` | ✅ | ✅ | ✅ | ✅ |
| 8 | `frontend/src/types.ts` | ✅ | ✅ | ✅ | ✅ |
| 9 | `frontend/src/App.tsx` | ✅ | ✅ | ✅ | ✅ |
| 10 | `frontend/src/components/OnboardingWizard.tsx` | ✅ | ✅ | N/A | ✅ |
| 11 | `frontend/src/constants/interviewOptions.ts` | ✅ | ✅ | N/A | ✅ |

**추가 보완 완료** (분석 후 수정):
- `chat.py` `submit_articles_batch` 핸들러에 `ordinance_type` 반환 추가
- `App.tsx` 헤더에 조례 유형 뱃지 표시 추가

---

## 갭 목록

**Critical/Important 이슈**: 없음

**Minor (수정 완료)**:

| 항목 | 위치 | 수정 내용 |
|------|------|---------|
| `submit_articles_batch` ChatResponse에 `ordinance_type` 누락 | `chat.py:407-420` | `ordinance_type=result.get("ordinance_type")` 추가 |
| `ordinanceType` 상태 UI 미활용 | `App.tsx` | 헤더에 조례 유형 뱃지 뷰 추가 |

---

## 런타임 검증 계획 (L1-L3)

### L1 — API Endpoint Tests
- `POST /session` with 설치·운영 메시지 → `ordinance_type === "설치·운영"` 검증
- `POST /session` with 관리·규제 메시지 → 큐에 `적용범위/사용료/위반제재` 검증
- `GET /session/{id}` → `ordinance_type` 복원 검증
- `POST /articles_batch` → `ordinance_type` 반환 검증

### L2 — UI Action Tests
- OnboardingWizard Step 0 유형 카드 선택 → ✓ 표시 확인
- 설치·운영 선택 → 제출 → ArticleItemsModal에 `구성/직무/운영/간사` 표시 확인

### L3 — E2E Scenario Tests
- 설치·운영 전체 플로우: 유형 선택 → 조항 입력 → 초안 생성 (위원회 설치 조항 포함)
- 기존 지원 조례 세션 복원: ordinance_type null → 기존 동작 유지
