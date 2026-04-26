# Plan: AuraDB 조례 유형 확장 데이터 적재

> **Status**: Plan
>
> **Created**: 2026-04-26
> **Feature**: auradb-ordinance-type-expansion

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | AuraDB에 지원 조례 관련 데이터(청년·창업·소상공인)만 적재되어 있어, 설치·운영 / 관리·규제 / 복지·서비스 조례 작성 시 `graph_retriever`가 유사 조례와 법령 근거를 제공하지 못함 |
| **Solution** | `pipeline/config.py`에 3개 신규 유형별 domain_keywords + mandatory_statutes 추가 후 증분 적재 실행 |
| **UX Effect** | 비지원 조례 사용자도 "참고 가능한 유사 조례 N건", "관련 법령 근거 N건"을 안내받아 초안 품질 향상 |
| **Core Value** | 4가지 유형 모두에서 데이터 기반 법적 조문 생성이 가능한 완전한 지식 그래프 구축 |

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | 설치·운영/관리·규제/복지·서비스 조례 선택 시 graph_retriever가 빈 결과를 반환 — 유사 조례 참고 없이 AI가 조문을 생성하므로 초안 품질이 낮아짐 |
| **WHO** | 비지원 조례(설치·운영/규제/복지)를 작성하는 지자체 담당 공무원 |
| **RISK** | AuraDB 용량 초과(Pro Basic 8GB 한도) / 국가법령정보센터 API 호출 한도(일 10,000건) / Gemini Embedding API 비용·속도 |
| **SUCCESS** | 4개 유형 각각에서 `graph_retriever`가 유사 조례 3건 이상 + 관련 법령 1건 이상 반환 |
| **SCOPE** | `pipeline/config.py` + `pipeline/scripts/incremental_update.py` 수정, AuraDB 데이터 적재 실행 |

---

## 1. 현황 분석

### 1.1 현재 적재 데이터 (지원 조례 중심)

| 항목 | 수량 | 저장 용량 |
|------|------|---------|
| Provision 노드 | ~316,943개 | ~7.8GB (임베딩 포함) |
| Ordinance 노드 | ~20,888개 | ~0.5GB (임베딩 포함) |
| domain_keywords | 11개 | 청년·창업·소상공인 중심 |
| mandatory_statutes | 6개 | 지방자치법·청년기본법·보조금법 등 |

### 1.2 현재 AuraDB 용량 상태

- **AuraDB Free**: 최대 200MB → 임베딩 제외 필수 (§12 참조)
- **AuraDB Professional Basic**: 최대 8GB → 현재 약 8.3GB 추정으로 이미 초과 위험
- **결론**: `SKIP_PROVISION_EMBEDDING=true` 유지 필수. Ordinance 임베딩만 선택적 허용.

---

## 2. 신규 적재 대상

### 2.1 설치·운영 조례

**추가할 domain_keywords (10개)**:
```
"위원회", "센터설치", "기관설립", "협의회", "자문위원회",
"심의위원회", "지원센터", "조정위원회", "운영위원회", "지방공기업"
```

**추가할 mandatory_statutes (3개)**:
```
"지방자치단체 출자·출연 기관의 운영에 관한 법률",
"공공기관의 운영에 관한 법률",
"행정기관 소속 위원회의 설치·운영에 관한 법률"
```

**예상 수집 데이터**:
| 구분 | 예상 수량 | 근거 |
|------|---------|------|
| Ordinance 노드 | 500~800개 | 전국 지자체 위원회 설치 조례 다수 |
| Provision 노드 | 5,000~16,000개 | 조례당 평균 10~20조 |
| Statute 노드 | 3~5개 | mandatory + 연관 법령 |

### 2.2 관리·규제 조례

**추가할 domain_keywords (10개)**:
```
"공유재산", "시설관리", "사용허가", "도로점용", "하천점용",
"공원관리", "과태료", "사용료", "행정제재", "허가취소"
```

**추가할 mandatory_statutes (4개)**:
```
"공유재산 및 물품 관리법",
"도로법",
"하천법",
"공중위생관리법"
```

**예상 수집 데이터**:
| 구분 | 예상 수량 | 근거 |
|------|---------|------|
| Ordinance 노드 | 400~600개 | 공유재산·시설관리 조례 보편적 |
| Provision 노드 | 4,000~12,000개 | 조례당 평균 10~20조 |
| Statute 노드 | 4~6개 | mandatory + 연관 법령 |

### 2.3 복지·서비스 조례

**추가할 domain_keywords (10개)**:
```
"사회서비스", "돌봄", "노인복지", "장애인복지", "아동복지",
"청소년복지", "여성복지", "기초생활", "복지급여", "방문서비스"
```

**추가할 mandatory_statutes (5개)**:
```
"사회보장기본법",
"노인복지법",
"장애인복지법",
"아동복지법",
"사회서비스 이용 및 이용권 관리에 관한 법률"
```

**예상 수집 데이터**:
| 구분 | 예상 수량 | 근거 |
|------|---------|------|
| Ordinance 노드 | 600~1,000개 | 복지 조례는 전국 매우 많음 |
| Provision 노드 | 6,000~20,000개 | 조례당 평균 10~20조 |
| Statute 노드 | 5~8개 | mandatory + 연관 법령 |

---

## 3. 예상 용량 및 시간

### 3.1 신규 데이터 용량 추정

| 구분 | 노드 수 | 텍스트만 (임베딩 없음) | 임베딩 포함 |
|------|--------|---------------------|-----------|
| 신규 Ordinance | 1,500~2,400개 | ~50MB | ~0.6GB |
| 신규 Provision | 15,000~48,000개 | ~100MB | ~0.4~1.2GB |
| 신규 Statute | 12~19개 | ~5MB | 무시 가능 |
| **합계 (임베딩 없음)** | | **~155MB** | — |
| **합계 (Ordinance 임베딩만)** | | — | **~0.65GB** |
| **합계 (전체 임베딩)** | | — | **~1~1.8GB** |

> **권장**: Provision 임베딩 제외(`SKIP_PROVISION_EMBEDDING=true`) + Ordinance 임베딩 포함
> → **AuraDB 추가 사용량: ~0.65GB** (Pro Basic 8GB 내 여유)

### 3.2 적재 소요 시간 추정

| 단계 | 작업 | 예상 시간 | 비고 |
|------|------|---------|------|
| Phase 1 | mandatory_statutes 신규 12개 | ~10분 | 0.5s × 12 × API 왕복 |
| Phase 2 | domain_keywords 신규 30개 × 법령 검색 | ~25분 | 0.5s × ~3,000 결과 |
| Phase 3 | domain_keywords 신규 30개 × 조례 수집 | ~25~35분 | 0.5s × 1,500~2,400건 |
| Phase 4 | 관계 구축 (기존 + 신규) | ~15분 | SIMILAR_TO 계산 포함 |
| Phase 5 | Ordinance 임베딩 (~2,000건) | ~2~4시간 | Gemini API 배치 20건/요청 |
| Phase 5 | Provision 임베딩 (권장: 생략) | ~20~40시간 | **생략 권장** |
| **합계 (Provision 임베딩 제외)** | | **~3~5시간** | |
| **합계 (전체 임베딩)** | | **~23~45시간** | **비권장** |

> **API 호출 한도 주의**: 국가법령정보센터 Open API 일 10,000건 한도.
> 신규 키워드 30개 × 최대 100결과 = 최대 3,000건 → 1일 내 완료 가능.
> 하지만 개별 법령·조례 상세 조회까지 포함 시 ~4,000~6,000건 → **2일에 나눠 실행 권장**.

### 3.3 실행 전략 (2일 분할)

**Day 1**: 설치·운영 + 관리·규제
```bash
SKIP_PROVISION_EMBEDDING=true \
NEO4J_URI="neo4j+s://da425acb.databases.neo4j.io" \
KEYWORDS_FILTER="설치운영,관리규제" \
python -m pipeline.scripts.incremental_update
```

**Day 2**: 복지·서비스 + Ordinance 임베딩
```bash
SKIP_PROVISION_EMBEDDING=true \
NEO4J_URI="neo4j+s://da425acb.databases.neo4j.io" \
KEYWORDS_FILTER="복지서비스" \
python -m pipeline.scripts.incremental_update

# Ordinance 임베딩 별도 실행
NEO4J_URI="neo4j+s://da425acb.databases.neo4j.io" \
python -m pipeline.scripts.embed_ordinances
```

---

## 4. 구현 범위

### 4.1 수정 파일

| 파일 | 변경 내용 |
|------|---------|
| `pipeline/config.py` | `domain_keywords` 30개 추가, `mandatory_statutes` 12개 추가, `ordinance_type_keywords` 맵 신규 추가 |
| `pipeline/scripts/incremental_update.py` | `KEYWORDS_FILTER` 환경변수 지원 추가 (유형별 분할 실행) |

### 4.2 신규 파일 (선택)

| 파일 | 용도 |
|------|------|
| `pipeline/scripts/embed_ordinances.py` | Ordinance 노드만 선택적 임베딩 (Provision 제외) |

### 4.3 검증 방법

```bash
# AuraDB에서 유형별 데이터 수 확인
MATCH (o:Ordinance) RETURN count(o)
MATCH (s:Statute) RETURN count(s)
MATCH (p:Provision) WHERE p.embedding IS NOT NULL RETURN count(p)

# graph_retriever 동작 확인 (curl)
curl -X POST https://.../api/v1/session \
  -d '{"initial_message": "서울특별시 노인 돌봄 위원회 설치 조례 작성"}'
# → similar_ordinances 3건 이상 반환 여부 확인
```

---

## 5. 위험 요소 및 대응

| 위험 | 가능성 | 대응 |
|------|--------|------|
| AuraDB 용량 초과 | 중 | SKIP_PROVISION_EMBEDDING=true 필수, 적재 전 현재 사용량 확인 |
| API 일 호출 한도 초과 | 중 | Day 1 / Day 2 분할 실행, 진행 로그로 중단점 기록 |
| Gemini Embedding API 비용 | 낮 | Ordinance ~2,000건 × 3072d — 약 $0.5 이내 (gemini-embedding-001 기준) |
| 중복 데이터 적재 | 낮 | `MERGE` 쿼리 사용으로 idempotent 보장 |
| AuraDB 일시정지 재발 | 중 | graph_retriever graceful fallback 적용 완료 (2026-04-26) |

---

## 6. 성공 기준

| 기준 | 측정 방법 |
|------|---------|
| 설치·운영 조례 유사 조례 3건 이상 반환 | `/session` POST → `similar_ordinances` 필드 확인 |
| 관리·규제 조례 법령 근거 1건 이상 반환 | `/session` POST → `legal_basis` 필드 확인 |
| 복지·서비스 조례 유사 조례 3건 이상 반환 | `/session` POST → `similar_ordinances` 필드 확인 |
| AuraDB 용량 8GB 미만 유지 | Neo4j Aura 콘솔 Storage 탭 확인 |
| 총 적재 소요 시간 5시간 이내 | `incremental_update.py` 실행 로그 |
