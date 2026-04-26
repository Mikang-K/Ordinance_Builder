# Design: AuraDB 조례 유형 확장 데이터 적재

> **Status**: Design
>
> **Created**: 2026-04-26
> **Feature**: auradb-ordinance-type-expansion
> **Architecture**: Option B — Clean Architecture

---

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | AuraDB에 지원 조례 데이터만 있어 설치·운영/관리·규제/복지·서비스 조례 작성 시 유사 조례·법령 근거 0건 반환 |
| **WHO** | 비지원 조례(설치·운영/규제/복지)를 작성하는 지자체 담당 공무원 |
| **RISK** | AuraDB 8GB 한도 / API 일 10,000건 한도 / 2일 분할 실행 필요 |
| **SUCCESS** | 4개 유형 각각에서 유사 조례 3건 이상 + 법령 근거 1건 이상 반환 |
| **SCOPE** | pipeline/config.py 수정 + type_load.py + embed_ordinances.py 신규 |

---

## 1. Overview

### 1.1 선택 아키텍처: Option B — Clean Architecture

타입별 완전 독립 스크립트를 추가하여 `incremental_update.py`의 기존 로직을 건드리지 않고, 3개 신규 유형 데이터를 안전하게 관리합니다.

```
pipeline/
├── config.py                  ← 수정 (ordinance_type_keywords 추가)
└── scripts/
    ├── initial_load.py        ← 기존 (변경 없음)
    ├── incremental_update.py  ← 기존 (변경 없음)
    ├── type_load.py           ← 신규 (타입별 선택적 적재)
    └── embed_ordinances.py    ← 신규 (Ordinance만 임베딩)
```

### 1.2 설계 원칙

- **기존 코드 불간섭**: `initial_load.py`, `incremental_update.py`는 수정하지 않음
- **타입 독립 실행**: `--type 설치·운영` 옵션으로 API 호출 범위 제한
- **Idempotent**: 중복 실행 시 `MERGE` 쿼리로 안전하게 덮어쓰기
- **용량 제어**: `SKIP_PROVISION_EMBEDDING=true` 기본 준수

---

## 2. config.py 변경 설계

### 2.1 추가할 데이터 구조

```python
# pipeline/config.py — 추가 필드

# 조례 유형별 키워드 매핑 (신규)
ordinance_type_keywords: dict[str, list[str]] = field(default_factory=lambda: {
    "지원": [
        "청년", "창업", "기업지원", "소상공인",
        "중소기업", "스타트업", "일자리", "보조금",
        "지방자치", "산업단지", "규제특례",
    ],
    "설치·운영": [
        "위원회", "센터설치", "기관설립", "협의회",
        "자문위원회", "심의위원회", "지원센터",
        "조정위원회", "운영위원회", "지방공기업",
    ],
    "관리·규제": [
        "공유재산", "시설관리", "사용허가", "도로점용",
        "하천점용", "공원관리", "과태료",
        "사용료", "행정제재", "허가취소",
    ],
    "복지·서비스": [
        "사회서비스", "돌봄", "노인복지", "장애인복지",
        "아동복지", "청소년복지", "여성복지",
        "기초생활", "복지급여", "방문서비스",
    ],
})

# 조례 유형별 필수 법령 (신규)
mandatory_statutes_by_type: dict[str, list[str]] = field(default_factory=lambda: {
    "지원": [
        "지방자치법",
        "청년기본법",
        "보조금 관리에 관한 법률",
        "지방재정법",
        "중소기업 창업 지원법",
        "소상공인 보호 및 지원에 관한 법률",
    ],
    "설치·운영": [
        "지방자치단체 출자·출연 기관의 운영에 관한 법률",
        "공공기관의 운영에 관한 법률",
        "행정기관 소속 위원회의 설치·운영에 관한 법률",
    ],
    "관리·규제": [
        "공유재산 및 물품 관리법",
        "도로법",
        "하천법",
        "공중위생관리법",
    ],
    "복지·서비스": [
        "사회보장기본법",
        "노인복지법",
        "장애인복지법",
        "아동복지법",
        "사회서비스 이용 및 이용권 관리에 관한 법률",
    ],
})
```

### 2.2 기존 필드 호환성

기존 `domain_keywords`와 `mandatory_statutes`는 유지합니다 (`incremental_update.py`가 이를 참조하므로). 신규 필드는 추가(append)만 합니다.

---

## 3. type_load.py 설계

### 3.1 인터페이스

```bash
# 특정 타입 적재
python -m pipeline.scripts.type_load --type 설치·운영
python -m pipeline.scripts.type_load --type 관리·규제
python -m pipeline.scripts.type_load --type 복지·서비스
python -m pipeline.scripts.type_load --type all      # 전체 신규 유형

# 환경변수로도 지정 가능
TYPE_FILTER="설치·운영" python -m pipeline.scripts.type_load

# Provision 임베딩 항상 제외 (AuraDB 용량 보호)
# SKIP_PROVISION_EMBEDDING=true 자동 적용 (type_load.py 내부 default)
```

### 3.2 처리 흐름

```
type_load.run(ordinance_type)
│
├── 1. config에서 해당 타입의 keywords + mandatory_statutes 조회
├── 2. mandatory_statutes 로드
│   └── load_statute(mst, client, loader)  # initial_load.py 재사용
├── 3. keywords → 법령 검색 + 로드
│   └── client.search_statutes(keyword) × N
├── 4. keywords → 조례 검색 + 로드
│   └── client.search_ordinances(keyword) × N
├── 5. 관계 재구축 (신규 노드가 있는 경우만)
│   ├── loader.build_based_on_relationships()
│   ├── loader.build_superior_to_relationships()
│   ├── loader.build_similar_to_relationships()
│   └── loader.build_delegates_relationships()
└── 6. 진행 상황 로그 출력 (적재 건수, 소요 시간)
```

### 3.3 코드 구조

```python
"""
Type-specific ordinance data loader.

Usage:
    python -m pipeline.scripts.type_load --type 설치·운영
    python -m pipeline.scripts.type_load --type all
"""

import argparse
import logging
import os
import time

from pipeline.api.law_api_client import LawApiClient
from pipeline.config import config
from pipeline.loaders.neo4j_loader import Neo4jLoader
from pipeline.scripts.initial_load import load_ordinance, load_statute

SUPPORTED_TYPES = ["설치·운영", "관리·규제", "복지·서비스", "지원"]


def run(ordinance_type: str) -> None:
    types_to_load = SUPPORTED_TYPES if ordinance_type == "all" else [ordinance_type]
    
    client = LawApiClient()
    with Neo4jLoader() as loader:
        for otype in types_to_load:
            _load_type(otype, client, loader)


def _load_type(otype: str, client, loader) -> None:
    keywords = config.ordinance_type_keywords.get(otype, [])
    statutes = config.mandatory_statutes_by_type.get(otype, [])
    
    # Phase 1: mandatory statutes for this type
    # Phase 2: keyword-based statutes
    # Phase 3: keyword-based ordinances
    # Phase 4: rebuild relationships
    ...


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, choices=SUPPORTED_TYPES + ["all"])
    args = parser.parse_args()
    run(args.type)
```

---

## 4. embed_ordinances.py 설계

### 4.1 인터페이스

```bash
# 모든 미임베딩 Ordinance 임베딩
python -m pipeline.scripts.embed_ordinances

# 특정 타입 조례만 임베딩 (키워드 필터)
python -m pipeline.scripts.embed_ordinances --type 설치·운영

# dry-run: 임베딩할 건수만 확인
python -m pipeline.scripts.embed_ordinances --dry-run
```

### 4.2 처리 흐름

```
embed_ordinances.run(ordinance_type=None)
│
├── 1. 미임베딩 Ordinance 노드 조회
│   MATCH (o:Ordinance) WHERE o.embedding IS NULL RETURN o.id, o.title
│   (--type 지정 시 o.title CONTAINS 관련 키워드로 필터)
├── 2. 배치 임베딩 (20건/요청, 1s 딜레이)
│   └── embedder.embed_texts(batch)
├── 3. AuraDB에 embedding 저장
│   SET o.embedding = $vector
└── 4. 진행 상황 출력 (완료 건수, 소요 시간, 예상 비용)
```

### 4.3 비용 추정 출력

```
[embed_ordinances] Ordinances to embed: 1,847
[embed_ordinances] Estimated time: ~3.5 hours (배치 20건, 1s 딜레이)
[embed_ordinances] Estimated cost: ~$0.45 (Gemini embedding-001 기준)
[embed_ordinances] Continue? (y/N):
```

---

## 5. 적재 실행 순서 (2일 분할)

### Day 1 (설치·운영 + 관리·규제)

```bash
cd d:/Project/Ordinance_Builder

# AuraDB 인스턴스 재개 확인 (일시정지 상태일 경우 Neo4j Aura 콘솔에서 Resume)
# 예상 소요: ~1.5~2시간

SKIP_PROVISION_EMBEDDING=true \
NEO4J_URI="neo4j+s://da425acb.databases.neo4j.io" \
NEO4J_PASSWORD="<password>" \
GOOGLE_API_KEY="<key>" \
LAW_API_KEY="<key>" \
python -m pipeline.scripts.type_load --type 설치·운영

# 완료 후 30분 대기 (API 호출 쿨다운)

SKIP_PROVISION_EMBEDDING=true \
NEO4J_URI="neo4j+s://da425acb.databases.neo4j.io" \
python -m pipeline.scripts.type_load --type 관리·규제
```

### Day 2 (복지·서비스 + Ordinance 임베딩)

```bash
# 복지·서비스 적재 (~1~1.5시간)
SKIP_PROVISION_EMBEDDING=true \
NEO4J_URI="neo4j+s://da425acb.databases.neo4j.io" \
python -m pipeline.scripts.type_load --type 복지·서비스

# Ordinance 임베딩 (~3~4시간)
NEO4J_URI="neo4j+s://da425acb.databases.neo4j.io" \
python -m pipeline.scripts.embed_ordinances
```

---

## 6. 데이터 모델 변경

Neo4j 그래프 스키마 변경 없음. 기존 노드/관계 타입 재사용:
- `:Ordinance`, `:Statute`, `:Provision` — 동일
- `BASED_ON`, `DELEGATES`, `SIMILAR_TO`, `SUPERIOR_TO` — 동일

신규 데이터는 기존과 동일 스키마로 적재됩니다.

---

## 7. 검증 계획

### 7.1 적재 후 AuraDB 확인 쿼리

```cypher
// 전체 노드 수 확인
MATCH (o:Ordinance) RETURN count(o) AS total_ordinances
MATCH (s:Statute) RETURN count(s) AS total_statutes
MATCH (p:Provision) WHERE p.embedding IS NOT NULL RETURN count(p) AS embedded_provisions
MATCH (o:Ordinance) WHERE o.embedding IS NOT NULL RETURN count(o) AS embedded_ordinances

// 신규 타입 법령 존재 여부
MATCH (s:Statute) WHERE s.title CONTAINS '공유재산' RETURN s.title
MATCH (s:Statute) WHERE s.title CONTAINS '노인복지' RETURN s.title
MATCH (s:Statute) WHERE s.title CONTAINS '위원회' RETURN s.title LIMIT 5
```

### 7.2 graph_retriever 동작 검증 (L1 테스트)

```bash
# 설치·운영 — 위원회 설치 조례
curl -s -X POST https://ordinance-backend-126242181039.asia-northeast3.run.app/api/v1/session \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"initial_message": "서울특별시 청년 위원회 설치 및 운영 조례 작성", "ordinance_type": "설치·운영"}' \
  | jq '.similar_ordinances | length'
# 기대값: 3 이상

# 관리·규제 — 공유재산 관리 조례
curl -s -X POST ... \
  -d '{"initial_message": "부산광역시 공유재산 사용 허가 및 관리 조례", "ordinance_type": "관리·규제"}' \
  | jq '.legal_basis | length'
# 기대값: 1 이상

# 복지·서비스 — 노인 돌봄 조례
curl -s -X POST ... \
  -d '{"initial_message": "경기도 수원시 노인 돌봄 서비스 지원 조례", "ordinance_type": "복지·서비스"}' \
  | jq '.similar_ordinances | length'
# 기대값: 3 이상
```

---

## 8. 위험 및 대응

| 위험 | 대응 |
|------|------|
| AuraDB 일시정지 재발 | 실행 전 Neo4j Aura 콘솔에서 인스턴스 상태 확인 후 Resume |
| API 한도 초과 (일 10,000건) | type별 분리 실행 + 실행 로그로 API 호출 건수 모니터링 |
| 용량 초과 | `embed_ordinances.py --dry-run`으로 임베딩 전 용량 추정 확인 |
| 부분 실패 후 재실행 | `MERGE` idempotent → 재실행 안전. 로그에서 마지막 성공 키워드 확인 후 재개 |

---

## 11. Implementation Guide

### 11.1 구현 순서

1. `pipeline/config.py` — `ordinance_type_keywords` + `mandatory_statutes_by_type` 추가
2. `pipeline/scripts/type_load.py` — 신규 작성
3. `pipeline/scripts/embed_ordinances.py` — 신규 작성
4. 로컬 테스트 (Mock DB 또는 소량 dry-run)
5. AuraDB 적재 실행 (Day 1 → Day 2)
6. 검증 쿼리 실행

### 11.2 의존성

추가 패키지 없음 — 기존 `pipeline/` 내부 모듈만 사용.

### 11.3 Session Guide

| 모듈 | 작업 | 예상 시간 |
|------|------|---------|
| M1 | config.py 수정 | 10분 |
| M2 | type_load.py 구현 | 30분 |
| M3 | embed_ordinances.py 구현 | 20분 |
| M4 | AuraDB Day 1 적재 실행 | ~2시간 |
| M5 | AuraDB Day 2 적재 + 임베딩 | ~4~5시간 |
| M6 | 검증 및 확인 | 20분 |
