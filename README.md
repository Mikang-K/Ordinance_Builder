# 조례 빌더 AI

> **대화형 AI로 지방자치단체 조례 초안을 자동 생성·검증하는 풀스택 서비스**

법령 전문 지식 없이도 자연어 대화만으로 법적으로 타당한 지방 조례 초안을 단계별로 작성할 수 있습니다.  
Neo4j 그래프 DB 기반 법령 검색과 멀티 LLM 파이프라인이 상위법 준수 여부를 실시간으로 검증합니다.

**배포 주소**: https://ordinance-builder-b9f6c.web.app

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **대화형 인터뷰** | 자연어 입력으로 조례 필수 정보(지역·목적·대상·지원유형)를 단계적으로 수집 |
| **그래프 기반 법령 검색** | DELEGATES → BASED_ON → 키워드 → 벡터 유사도 4단계 우선순위로 상위법 탐색 |
| **조문별 세부 입력** | 9개 조문 템플릿(목적·정의·지원대상·금액·신청·심사·환수 등)을 개별 인터뷰 |
| **자동 초안 생성** | Claude Opus 4.6이 수집 정보·법령 근거·유사 조례를 바탕으로 완전한 조례문 출력 |
| **AI 자체 검토** | 초안을 AI가 스스로 검토하고, 사용자 피드백을 반영해 즉시 수정 |
| **법적 정합성 검증** | GPT-4o가 상위법 충돌을 HIGH·MEDIUM·LOW 3단계 심각도로 분류해 고지 |
| **GraphRAG Q&A** | 워크플로우와 무관하게 언제든 법령·조례 내용을 질의응답 가능 |
| **조례 유형 분기** | 지원·설치·운영·관리·규제·복지·서비스 유형별로 필수 필드 및 인터뷰 경로 분기 |

---

## 기술 스택

### 백엔드

| 역할 | 기술 |
|------|------|
| API 서버 | Python · FastAPI · Uvicorn / Gunicorn |
| AI 오케스트레이션 | LangGraph · LangChain |
| 정보 추출 LLM | Gemini 2.5 Pro (`langchain-google-genai`) |
| 초안 생성·검토 LLM | Claude Opus 4.6 (`langchain-anthropic`) |
| 법률 검증 LLM | GPT-4o (`langchain-openai`) |
| 임베딩 | `models/gemini-embedding-001` (3072차원) |
| 그래프 DB | Neo4j 5.23 (로컬) · AuraDB (프로덕션) |
| 세션 체크포인트 | PostgreSQL · `langgraph-checkpoint-postgres` |
| 인증 | Firebase Admin SDK |
| Rate Limiting | slowapi |

### 프론트엔드

| 역할 | 기술 |
|------|------|
| UI 프레임워크 | React 18 · TypeScript · Vite |
| 인증 | Firebase Auth (`signInWithRedirect`) |

### 인프라

| 역할 | 기술 |
|------|------|
| 백엔드 배포 | GCP Cloud Run |
| 프론트엔드 배포 | Firebase Hosting |
| 컨테이너 (로컬) | Docker Compose |
| ETL 데이터 소스 | 국가법령정보센터 Open API |

---

## 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────┐
│           React + TypeScript (Firebase Hosting)           │
│   ChatWindow · DraftModal · ArticleItemsModal · QAPanel  │
└────────────────────┬─────────────────────────────────────┘
                     │ REST API (JSON + Firebase JWT)
┌────────────────────▼─────────────────────────────────────┐
│              FastAPI  ·  GCP Cloud Run                    │
│  ┌───────────────────────────────────────────────────┐   │
│  │             LangGraph Workflow                    │   │
│  │                                                   │   │
│  │  START → route_at_start                           │   │
│  │     ├─[legal_review]  → legal_checker  (GPT-4o)   │   │
│  │     ├─[draft_review]  → draft_reviewer (Claude)   │   │
│  │     ├─[article_*]     → article_interviewer       │   │
│  │     └─[default]       → intent_analyzer (Gemini)  │   │
│  │                              │                    │   │
│  │              [필드 누락] → interviewer → END       │   │
│  │              [정보 완비] → graph_retriever         │   │
│  │                              │                    │   │
│  │              [큐 없음]  → article_planner → END    │   │
│  │              [큐 있음]  → article_interviewer      │   │
│  │                              │                    │   │
│  │              [조항 완료] → drafting_agent (Claude) │   │
│  │                              └─ → draft_reviewer  │   │
│  │                                  └─ → legal_checker│  │
│  └───────────────────────────────────────────────────┘   │
│  PostgreSQL  (LangGraph 체크포인트 + 세션 메타데이터)       │
└────────────────────┬─────────────────────────────────────┘
                     │ Bolt (7687)
┌────────────────────▼─────────────────────────────────────┐
│            Neo4j AuraDB  (벡터 인덱스 3072d cosine)        │
│  Statute · Provision · Ordinance · LegalTerm 노드         │
│  DELEGATES · BASED_ON · SIMILAR_TO · CONFLICTS_WITH 관계  │
└────────────────────┬─────────────────────────────────────┘
                     ▲
          ┌──────────┘  ETL Pipeline (독립 모듈)
          │  국가법령정보센터 Open API (XML)
          │  LawApiClient → SchemaMapper → Neo4jLoader
          └──────────────────────────────────────────────
```

---

## LangGraph 멀티 LLM 워크플로우

각 노드에 역할에 최적화된 LLM을 배정한 상태 머신입니다.  
`messages` 필드만 `add_messages` 리듀서로 누적하고, 나머지 상태는 덮어쓰기로 관리합니다.  
LangGraph `interrupt` 없이 `/chat` 요청마다 그래프 진입점에 재진입하는 방식으로 인터뷰 루프를 구현합니다.

| 노드 | LLM | 역할 | 구조화 출력 |
|------|-----|------|------------|
| `intent_analyzer` | Gemini 2.5 Pro | 자연어 → 필드 추출 | `ExtractedInfo` |
| `interviewer` | — | 누락 필드 질문 생성 | — |
| `graph_retriever` | — | Neo4j 법령 근거·유사 조례 탐색 | — |
| `article_planner` | — | 9개 조문 큐 구성 | — |
| `article_interviewer` | — | 조문별 세부 내용 수집 | — |
| `drafting_agent` | Claude Opus 4.6 | 완전한 조례 초안 생성 | `OrdinanceDraft` |
| `draft_reviewer` | Claude Opus 4.6 | AI 자체 검토 및 수정 | `ReviewDecision` |
| `legal_checker` | GPT-4o | 상위법 충돌 검증 | `LegalCheckResult` |

### 조건부 분기 (5개)

```
route_at_start          → legal_checker | draft_reviewer | article_interviewer | intent_analyzer
route_after_intent      → interviewer (필드 누락) | graph_retriever (완비)
route_after_retriever   → article_planner (큐 없음) | drafting_agent (큐 있음)
route_after_article     → drafting_agent (완료) | END (다음 /chat 대기)
route_after_draft_review → legal_checker (confirm) | END (revise)
```

---

## Neo4j 그래프 데이터 모델

### 노드 타입

| 레이블 | 주요 속성 | 설명 |
|--------|-----------|------|
| `Statute` | id · title · category · enforcement_date · embedding | 상위 법령 |
| `Provision` | id · article_no · content_text · is_penalty_clause · embedding | 법령 조문 |
| `Ordinance` | id · region_name · title · enforcement_date · embedding | 지자체 조례 |
| `LegalTerm` | term_name · definition · synonyms | 핵심 법률 용어 |

### 관계 타입

| 관계 | 방향 | 탐색 우선순위 |
|------|------|--------------|
| `DELEGATES` | Statute → Ordinance | 1순위 — 명시적 위임 |
| `BASED_ON` | Ordinance → Statute | 2순위 — 조례 법령 근거 |
| `CONTAINS` | Statute → Provision | — |
| `SIMILAR_TO` | Ordinance ↔ Ordinance | 벡터 유사도 기반 |
| `CONFLICTS_WITH` | Ordinance → Statute | 충돌 감지 |
| `SUPERIOR_TO` | Statute → Ordinance | 법적 위계 |

### 벡터 인덱스

```cypher
CREATE VECTOR INDEX idx_ordinance_embedding
  FOR (o:Ordinance) ON o.embedding
  OPTIONS {indexConfig: {`vector.dimensions`: 3072, `vector.similarity_function`: 'cosine'}}
```

Neo4j 5.23+ 권장 쿼리 패턴 (`db.index.vector.queryNodes` deprecated 대응):

```cypher
MATCH (o:Ordinance)
WHERE o.embedding IS NOT NULL
WITH o, vector.similarity.cosine(o.embedding, $embedding) AS score
ORDER BY score DESC LIMIT $limit
```

---

## OWL 온톨로지

법령 도메인 개념을 Protégé로 모델링한 `ordinance.rdf` — Neo4j 스키마의 개념적 기반입니다.

```
법규범
├── 상위법률   ──→  :Statute 노드
└── 자치법규
    └── 조례   ──→  :Ordinance 노드

조문구조
└── 조(條)     ──→  :Provision 노드
    └── 항·호·목

객체 속성 (OWL → Neo4j 관계)
  위임하다       → DELEGATES
  위임근거를_가지다 → BASED_ON
  상충하다       → CONFLICTS_WITH
  포함하다       → CONTAINS
  정의하다       → DEFINES
```

---

## ETL 파이프라인

국가법령정보센터 Open API에서 법령·조례를 수집해 Neo4j에 MERGE 방식으로 적재합니다.

```
LawApiClient (XML 파싱)
    ↓
SchemaMapper (API 응답 → Graph 노드 객체)
    ↓
Neo4jLoader (MERGE + 관계 구축 + Gemini Embedding)
```

**초기 적재 4단계** (`initial_load.py`):

| Phase | 내용 |
|-------|------|
| 1 | 필수 법령 6개 강제 적재 (지방자치법·청년기본법·보조금관리법 등) |
| 2 | 도메인 키워드 기반 법령 검색 및 적재 |
| 3 | 도메인 키워드 기반 전국 지자체 조례 수집 |
| 4 | 관계 구축 (BASED_ON·SIMILAR_TO·DELEGATES 등) + 벡터 임베딩 생성 |

**조례 유형별 확장 적재** (`type_load.py`):  
`--type 설치·운영 | 관리·규제 | 복지·서비스 | all` 인자로 유형별 선택 적재.  
`SKIP_PROVISION_EMBEDDING=true` 내부 기본 적용 (AuraDB 8GB 용량 보호).

---

## 프로젝트 구조

```
Ordinance_Builder/
├── app/
│   ├── main.py                     # FastAPI 진입점 (lifespan, 미들웨어)
│   ├── api/routers/
│   │   ├── chat.py                 # /session · /chat · /articles_batch · /finalize
│   │   └── debug.py                # 개발용 디버그 엔드포인트
│   ├── core/
│   │   ├── config.py               # 환경변수 (pydantic-settings)
│   │   ├── llm.py                  # provider별 LLM 팩토리 (Gemini/OpenAI/Anthropic)
│   │   └── embedder.py             # Gemini 임베딩 클라이언트
│   ├── db/
│   │   ├── base.py                 # GraphDBInterface (ABC)
│   │   ├── neo4j_db.py             # Neo4j 구현체 (프로덕션)
│   │   └── session_store.py        # PostgreSQL 세션 CRUD (psycopg-pool)
│   ├── graph/
│   │   ├── state.py                # OrdinanceBuilderState (TypedDict)
│   │   ├── workflow.py             # LangGraph 조립 + 싱글톤
│   │   ├── nodes/                  # 8개 노드 구현 (모두 async def)
│   │   └── edges/conditions.py     # 5개 조건부 분기 함수
│   └── prompts/                    # LLM 프롬프트 템플릿
│
├── pipeline/                       # 국가법령정보센터 → Neo4j ETL
│   ├── api/law_api_client.py       # Open API 호출 + XML 파싱
│   ├── transform/schema_mapper.py  # API 응답 → Graph 스키마 변환
│   ├── loaders/neo4j_loader.py     # MERGE 적재 + 임베딩
│   ├── sync/change_detector.py     # enforcement_date 비교 증분 업데이트
│   └── scripts/
│       ├── initial_load.py         # 최초 4단계 전체 적재
│       ├── type_load.py            # 조례 유형별 추가 적재
│       ├── embed_ordinances.py     # 미임베딩 Ordinance 선택적 임베딩
│       └── incremental_update.py   # 주기적 증분 업데이트
│
├── frontend/src/
│   ├── App.tsx                     # 상태 관리, 인증, 뷰 전환
│   ├── components/
│   │   ├── ChatWindow.tsx
│   │   ├── DraftModal.tsx          # 초안 편집 + 법률 검증 요청
│   │   ├── ArticleItemsModal.tsx   # 조문별 세부 입력 (일괄 제출 지원)
│   │   ├── QAPanel.tsx             # GraphRAG 법령 Q&A 슬라이딩 패널
│   │   ├── LegalIssuesPanel.tsx    # 법률 이슈 severity 색상 코딩
│   │   ├── LoadingModal.tsx        # API 호출 중 오버레이
│   │   └── OnboardingWizard.tsx    # 첫 방문 사용자 안내
│   └── api.ts                      # FastAPI 연동 클라이언트
│
├── docker-compose.yml              # postgres + neo4j + backend + frontend
├── Dockerfile
├── requirements.txt
└── ordinance.rdf                   # OWL 온톨로지
```

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/sessions` | 세션 목록 조회 |
| `POST` | `/api/v1/session` | 세션 생성 (첫 메시지 포함) |
| `GET` | `/api/v1/session/{id}` | 세션 상태 복원 |
| `DELETE` | `/api/v1/session/{id}` | 세션 삭제 (소유자 검증) |
| `POST` | `/api/v1/session/{id}/chat` | 대화 계속 |
| `POST` | `/api/v1/session/{id}/articles_batch` | 조문 일괄 제출 |
| `POST` | `/api/v1/session/{id}/finalize` | 초안 확정 |
| `POST` | `/api/v1/session/{id}/qa` | GraphRAG 법령 Q&A |

---

## 로컬 실행

### 1. 환경변수 설정

```bash
cp .env.example .env
```

| 변수 | 역할 |
|------|------|
| `GOOGLE_API_KEY` | Gemini LLM + Embedding |
| `ANTHROPIC_API_KEY` | Claude (초안 생성·검토) |
| `OPENAI_API_KEY` | GPT-4o (법률 검증) |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | 그래프 DB |
| `POSTGRES_PASSWORD` | PostgreSQL |
| `FIREBASE_CREDENTIALS_PATH` | 서버사이드 Firebase 인증 |

### 2. Docker Compose 시작

```bash
docker compose up -d
docker logs ordinance_builder-backend-1 -f
# "Application startup complete" 확인 후 http://localhost:3000 접속
```

### 3. ETL 파이프라인 실행 (최초 1회)

```bash
pip install -r pipeline/requirements.txt
python -m pipeline.scripts.initial_load
```

---

## 배포

```bash
# 백엔드 — GCP Cloud Run
gcloud builds submit --tag gcr.io/ordinance-builder-b9f6c/backend
gcloud run deploy ordinance-backend \
  --image gcr.io/ordinance-builder-b9f6c/backend \
  --set-env-vars "CORS_ORIGINS=https://ordinance-builder-b9f6c.web.app"

# 프론트엔드 — Firebase Hosting
cd frontend && npm run build
firebase deploy --only hosting
```

---

## 핵심 설계 결정

| 결정 | 이유 |
|------|------|
| **노드별 LLM 분리** (Gemini/Claude/GPT-4o) | 각 태스크 특성에 최적화 — 한국어 추출·장문 생성·비판적 분석 역할 분리 |
| **interrupt 없는 인터뷰 루프** | 체크포인트 재진입 방식으로 LangGraph 복잡도 제거, 상태 일관성 보장 |
| **GraphDBInterface 추상화** (ABC) | Mock ↔ Neo4j ↔ AuraDB 교체를 코드 변경 없이 환경변수로 제어 |
| **모든 LLM 노드 async** | FastAPI async 워커 블로킹 방지 — 수십 초 LLM 응답 중 동시 요청 처리 가능 |
| **PostgreSQL 커넥션 풀** (psycopg-pool) | Cloud Run 부하 시 매 요청 신규 연결 생성 방지 |
| **CORS_ORIGINS를 str 타입** | pydantic-settings v2의 `list[str]` JSON 디코딩 우회 — Cloud Run 배포 안정성 확보 |
| **signInWithRedirect** | COOP 정책으로 signInWithPopup 차단 → 리다이렉트 방식으로 전환 |
| **AuraDB authDomain=web.app** | Chrome 120+ Bounce Tracking 방지 기능 우회 — firebaseapp.com 저장소 삭제 문제 해결 |
