# QA 직접 검색 (qa-direct-search) PDCA 완료 보고서

> **Feature**: qa-direct-search
> **Completed**: 2026-04-21
> **Author**: Mikang87
> **Match Rate**: 98.8%
> **Phase**: Design → Do (module-1, 2, 3) → Check → Report

---

## Executive Summary

### 1.1 Overview

| 관점 | 내용 |
|------|------|
| **Problem** | 기존 QA 패널은 세션의 `ordinance_info`(지역·목적·대상·유형) 기반으로만 검색하여, 세션 초기나 조례와 무관한 법령 질문에서 유용한 결과를 얻기 어려웠음 |
| **Solution** | 질문 텍스트 자체를 Gemini Embedding으로 벡터화하여 Neo4j 전체 DB를 검색하는 독립 엔드포인트(`POST /api/v1/qa`)와 프론트엔드 모드 전환 UI를 구현 |
| **UX Effect** | QAPanel에서 "세션 기반" / "직접 검색" 토글 버튼 한 번으로 전환 — 세션 없이도, 세션 초기에도 법령 질의응답 가능 |
| **Core Value** | 기존 세션 기반 QA를 완전히 유지하면서 직접 검색 경로를 추가 (비파괴적 확장). AuraDB degraded 환경(Provision 임베딩 미적재)도 Ordinance fallback으로 자동 처리 |

### 1.2 Success Criteria Status

| 기준 | 상태 | 근거 |
|------|:----:|------|
| `POST /api/v1/qa` 엔드포인트 동작 (세션 독립) | MET | `chat.py:532` — Firebase Auth + Rate Limit 포함 |
| QAPanel 모드 전환 토글 UI 동작 | MET | `QAPanel.tsx:256-270` — 파란 강조 표시 포함 |
| 기존 `/session/{id}/qa` 완전 비파괴 | MET | 기존 엔드포인트 코드 변경 없음 |
| `GraphDBInterface` ABC 확장 (Mock↔Neo4j) | MET | `base.py:126,147` — abstract method 2개 추가 |
| AuraDB degraded mode 처리 | MET | `qa_service.py` — Provision 없으면 Ordinance 벡터 fallback |

**Overall Success Rate: 5/5 (100%)**

### 1.3 Value Delivered

| 관점 | 결과 |
|------|------|
| **기능** | 세션 없이도 법령·조례 질의응답 가능. 질문 임베딩 기반 전체 DB 검색 |
| **품질** | Match Rate 98.8%. 기능적 gap 0건. Low gap 1건(score 필드 미사용) |
| **확장성** | Clean Architecture 서비스 계층 분리 — `qa_service.py` 독립 테스트 가능 |
| **안정성** | Degraded mode, DB 오류 시 LLM 단독 답변으로 graceful fallback |

---

## 2. PDCA Journey

### 2.1 Phase Summary

| Phase | 날짜 | 산출물 | 결과 |
|-------|------|--------|------|
| Design | 2026-04-21 | `docs/02-design/features/qa-direct-search.design.md` | Option B 선택 (Clean Architecture) |
| Do (module-1) | 2026-04-21 | `app/db/base.py`, `neo4j_db.py`, `mock_db.py` | DB 계층 추상화 확장 |
| Do (module-2) | 2026-04-21 | `app/services/qa_service.py`, `qa_agent.py`, `schemas.py` | 서비스 + 프롬프트 계층 |
| Do (module-3) | 2026-04-21 | `app/api/routers/chat.py`, `api.ts`, `QAPanel.tsx` | 엔드포인트 + 프론트엔드 |
| Check | 2026-04-21 | `docs/03-analysis/qa-direct-search.analysis.md` | 98.8% (1 Low gap) |
| Report | 2026-04-21 | 이 문서 | 완료 |

### 2.2 Architecture Selection — Decision Record

| 단계 | 결정 | 근거 |
|------|------|------|
| Design | Option B (독립 엔드포인트 + 서비스 계층) 선택 | 세션 완전 독립, 서비스 레이어 분리로 테스트 용이, 기존 비파괴 |
| Do module-1 | ABC에 추상 메서드 2개 추가 후 Neo4j/Mock 구현 순서 | 타입 안전성 우선, 구현체 순서로 컴파일 오류 방지 |
| Do module-2 | `asyncio.to_thread` + `asyncio.gather` 병렬 처리 | Provision 벡터 검색과 LegalTerm 키워드 검색을 동시 실행 |
| Do module-3 | `applicable_content=None` 고정 반환 | 세션 컨텍스트 없이 조항 키 판단 불가 — "적용하기" 버튼 자동 미표시 |

---

## 3. Implementation Summary

### 3.1 변경 파일 목록 (9개)

| 파일 | 변경 유형 | 핵심 변경 |
|------|:--------:|---------|
| `app/db/base.py` | 수정 | `vector_search_provisions()`, `vector_search_ordinances()` 추상 메서드 추가 |
| `app/db/neo4j_db.py` | 수정 | 두 메서드 구현 — `idx_provision_embedding`, `idx_ordinance_embedding` 쿼리 |
| `app/db/mock_db.py` | 수정 | Mock 구현 (시드 데이터 반환) |
| `app/prompts/qa_agent.py` | 수정 | `build_qa_human_direct()` 세션 무관 RAG 프롬프트 빌더 추가 |
| `app/services/qa_service.py` | **신규** | `direct_search_qa()` — 임베딩 → 벡터 검색 → LLM 서비스 계층 |
| `app/api/schemas.py` | 수정 | `QADirectRequest` Pydantic 모델 추가 |
| `app/api/routers/chat.py` | 수정 | `POST /api/v1/qa` 엔드포인트, Auth + Rate Limit 포함 |
| `frontend/src/api.ts` | 수정 | `searchDirectQuestion()` 클라이언트 함수 추가 |
| `frontend/src/components/QAPanel.tsx` | 수정 | `SearchMode` 타입, `searchMode` state, 토글 UI, 분기 로직 |

### 3.2 Clean Architecture 레이어 배치

```
Presentation  app/api/routers/chat.py        POST /api/v1/qa
Application   app/services/qa_service.py     direct_search_qa()
Domain        app/api/schemas.py             QADirectRequest
Infrastructure app/db/base.py               vector_search_*() (ABC)
              app/db/neo4j_db.py            Neo4j 구현
              app/db/mock_db.py             Mock 구현
              app/prompts/qa_agent.py       build_qa_human_direct()
```

---

## 4. Gap Analysis Results

### 4.1 Match Rate

| 축 | 점수 | 가중치 | 기여 |
|---|:---:|:---:|:---:|
| Structural (9/9 파일) | 100% | 0.2 | 20.0 |
| Functional (6/6 UI 항목) | 100% | 0.4 | 40.0 |
| Contract (API 3-way) | 97% | 0.4 | 38.8 |
| **Overall** | | | **98.8%** |

### 4.2 Gap 목록

| Severity | 항목 | 위치 | 영향 | 조치 |
|:--------:|------|------|:----:|------|
| LOW | `vector_search_provisions` RETURN에 `score` 필드 누락 | `neo4j_db.py:295` | 없음 | 추후 필요 시 RETURN 절 추가 |

---

## 5. Key Learnings

### 5.1 잘 된 점

- **3-Module 분리**: DB → 서비스 → 엔드포인트+프론트 순서로 의존성 방향을 따라 구현. 각 모듈 완료 후 즉시 검증 가능했음
- **Degraded mode 설계**: AuraDB 환경에서 Provision 벡터 인덱스 미적재 시 Ordinance 벡터로 자동 fallback. `try/except`로 DB 오류도 graceful 처리
- **비파괴적 확장**: 기존 `/session/{id}/qa` 코드 한 줄도 변경 없이 새 경로 추가. CLAUDE.md §16 패턴 그대로 유지

### 5.2 개선 가능한 점

- `vector_search_provisions` RETURN에 `score` 필드 추가 → 향후 신뢰도 기반 소스 정렬에 활용 가능
- 직접 검색 결과에서 `applicable_content`를 부분적으로 추론하는 로직 추가 검토 (조항 작성 중일 때)

---

## 6. Next Steps (Optional)

| 항목 | 우선순위 | 설명 |
|------|:-------:|------|
| `score` 필드 반환 추가 | Low | `neo4j_db.py` RETURN 절에 `score` 추가 |
| 직접 검색 rate limit 분리 | Low | 임베딩 비용 증가 시 `10/minute`으로 별도 제한 검토 |
| 배포 후 실 사용 테스트 | High | Cloud Run 환경에서 L1 API 테스트 (CLAUDE.md §테스트 환경 기준) |
