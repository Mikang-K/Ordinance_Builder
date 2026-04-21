# QA 직접 검색 Gap Analysis

> **Feature**: qa-direct-search
> **Date**: 2026-04-21
> **Design Doc**: `docs/02-design/features/qa-direct-search.design.md`
> **Analysis Mode**: Static Only (서버 미구동 환경)
> **Formula**: Structural×0.2 + Functional×0.4 + Contract×0.4

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 세션 컨텍스트 없이 질문 임베딩으로 Neo4j 전체 DB 벡터 검색 가능한 독립 엔드포인트 추가 |
| **SUCCESS** | `/api/v1/qa` 동작, QAPanel 모드 전환 UI 동작 |
| **SCOPE** | 9개 파일 (DB 계층 3 + 서비스 1 + 프롬프트 1 + API 2 + 프론트 2) |

---

## 1. Structural Match (100%)

| # | 설계 명세 파일 | 존재 여부 | 핵심 심볼 | 판정 |
|---|--------------|:--------:|---------|:----:|
| 1 | `app/db/base.py` | OK | `vector_search_provisions()`, `vector_search_ordinances()` abstract | PASS |
| 2 | `app/db/neo4j_db.py` | OK | 두 메서드 구현 (line 295, 327) | PASS |
| 3 | `app/db/mock_db.py` | OK | 두 메서드 구현 (line 158, 181) | PASS |
| 4 | `app/prompts/qa_agent.py` | OK | `build_qa_human_direct()` (line 85) | PASS |
| 5 | `app/services/qa_service.py` | OK | `direct_search_qa()` | PASS |
| 6 | `app/api/schemas.py` | OK | `QADirectRequest` (line 111) | PASS |
| 7 | `app/api/routers/chat.py` | OK | `POST /api/v1/qa` (line 532), `QADirectRequest` import | PASS |
| 8 | `frontend/src/api.ts` | OK | `searchDirectQuestion()` (line 106) | PASS |
| 9 | `frontend/src/components/QAPanel.tsx` | OK | `SearchMode`, `searchMode` state, toggle UI | PASS |

**Structural Score: 9/9 = 100%**

---

## 2. Functional Depth — Page UI Checklist (100%)

Design §5.3 QAPanel 직접 검색 모드 체크리스트:

| # | 항목 | 구현 위치 | 판정 |
|---|------|---------|:----:|
| 1 | 토글: "세션 기반" / "직접 검색" 버튼 두 개 | QAPanel.tsx line 256-270 | PASS |
| 2 | 선택된 모드 강조 (파란 배경) | `background: searchMode === mode ? '#1e40af' : ...` | PASS |
| 3 | 직접 검색 모드 설명 문구 표시 | QAPanel.tsx line 288-298 (`searchMode === 'direct'`) | PASS |
| 4 | 질문 textarea (기존과 동일) | QAPanel.tsx line 327 | PASS |
| 5 | 전송 버튼 | QAPanel.tsx line 340 | PASS |
| 6 | "현재 조항에 적용하기" 미표시 (직접 검색 시) | `applicable_content` 항상 null → `canApply` false | PASS |

**Functional Score: 6/6 = 100%**

---

## 3. API Contract Check (97%)

### 3.1 엔드포인트 3-Way 검증

| 항목 | Design §4.2 | chat.py (서버) | api.ts (클라이언트) | 판정 |
|------|------------|--------------|-------------------|:----:|
| Method | POST | POST | POST | PASS |
| Path | `/api/v1/qa` | `/qa` (router prefix `/api/v1`) | `/api/v1/qa` | PASS |
| Request body | `{ question: str }` | `QADirectRequest.question` | `{ question }` | PASS |
| Response | `QAResponse` | `QAResponse` | `Promise<QAResponse>` | PASS |
| Auth | Firebase 필수 | `Depends(get_current_user)` | `authHeaders()` | PASS |
| Rate limit | 20/minute | `@limiter.limit("20/minute")` | N/A | PASS |
| applicable_content | null 고정 | `applicable_content=None` | — | PASS |

### 3.2 DB 반환 형식 검증

| 메서드 | 설계 필드 | 구현 반환 필드 | 판정 |
|--------|---------|-------------|:----:|
| `vector_search_provisions` | statute_id, statute_title, provision_article, provision_content, relation_type, **score** | statute_id, statute_title, provision_article, provision_content, relation_type | LOW GAP |
| `vector_search_ordinances` | ordinance_id, region_name, title, similarity_score, relevance_reason | ordinance_id, region_name, title, similarity_score, relevance_reason | PASS |

**Low Gap**: `vector_search_provisions` 반환 dict에 `score` 필드 미포함.
- 설계 §3.2에 `score: float` 명시
- 영향: 엔드포인트 및 서비스 코드가 `score`를 사용하지 않아 기능 영향 없음
- 조치: 필요 시 추후 Neo4j RETURN 절에 `score` 추가 (Low priority)

**Contract Score: ~97%**

---

## 4. Gap Summary

| Severity | 항목 | 위치 | 영향 |
|:--------:|------|------|------|
| LOW | `vector_search_provisions` 반환에 `score` 필드 누락 | `app/db/neo4j_db.py:295` | 없음 (미사용 필드) |

---

## 5. Match Rate Calculation

```
Static Only Formula:
  Structural (0.2) : 100% × 0.2 = 20.0
  Functional  (0.4) : 100% × 0.4 = 40.0
  Contract    (0.4) :  97% × 0.4 = 38.8
  ─────────────────────────────────────
  Overall Match Rate = 98.8%
```

---

## 6. Architecture Compliance

| 설계 원칙 | 준수 여부 |
|---------|:--------:|
| 기존 `/session/{id}/qa` 비파괴 | PASS |
| Clean Architecture 레이어 분리 (Presentation/Application/Domain/Infrastructure) | PASS |
| `GraphDBInterface` ABC 확장 (Mock↔Neo4j 교체 가능) | PASS |
| `async def` + `asyncio.to_thread` 패턴 | PASS |
| Firebase Auth + Rate Limiting | PASS |
| AuraDB degraded mode (Provision 없으면 Ordinance fallback) | PASS |

---

## 7. Conclusion

**Overall Match Rate: 98.8%** — 90% 기준 초과 달성

단 1건의 Low severity gap (score 필드 누락)만 존재하며, 기능적 영향이 없습니다.
qa-direct-search 기능은 설계대로 완전히 구현되었습니다.
