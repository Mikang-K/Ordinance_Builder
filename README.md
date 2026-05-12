# Ordinance Builder AI

> GraphRAG와 멀티 LLM 워크플로우를 활용한 지방자치단체 조례 초안 자동 생성 서비스

Ordinance Builder AI는 사용자가 만들고 싶은 조례의 목적과 정책 아이디어를 입력하면, 관련 법령과 유사 조례를 검색하고 필요한 조항 정보를 수집한 뒤 조례 초안을 생성하는 AI 기반 웹 애플리케이션입니다. 초안 작성 이후에는 사용자가 직접 내용을 편집하고, 법적 쟁점 검토를 요청하며, 최종 조례안을 확정할 수 있습니다.

이 프로젝트는 단순 챗봇이 아니라 **법령 데이터 파이프라인, Neo4j 지식 그래프, LangGraph 상태 머신, 멀티 LLM 에이전트, React 기반 문서 작성 UX**를 결합한 실무형 조례 작성 보조 시스템입니다.

## 프로젝트 배경

지방자치단체 조례는 단순한 문서가 아니라 지역 정책을 법적 형식으로 구현하는 규범 문서입니다. 조례 초안을 만들기 위해서는 다음 요소를 함께 검토해야 합니다.

- 상위 법령과의 위임 관계
- 유사 지자체 조례의 조항 구성
- 목적, 정의, 지원 대상, 사업 범위, 재정 지원, 위탁, 시행규칙 등 조항 체계
- 법률 용어의 정의와 사용 맥락
- 상위 법령과 충돌할 수 있는 제한, 의무, 제재 조항
- 조례 작성자의 의도와 실제 문안 사이의 정합성

기존 생성형 AI만으로는 이러한 구조적 검토가 어렵습니다. LLM이 법령명을 그럴듯하게 만들어내거나, 지역 조례의 실무적 구조를 놓치거나, 사용자의 의도가 충분히 수집되지 않은 상태에서 문안을 생성할 수 있기 때문입니다.

Ordinance Builder AI는 이 문제를 해결하기 위해 조례 작성 과정을 여러 단계로 분리했습니다. 먼저 사용자의 의도를 분석하고, 부족한 정보를 인터뷰로 보강합니다. 이후 Neo4j 그래프에서 관련 법령과 유사 조례를 검색하고, 조항별 세부 내용을 수집한 뒤 초안을 생성합니다. 마지막으로 법적 검토와 사용자 편집을 거쳐 최종안을 확정합니다.

## 핵심 문제와 해결 방향

| 문제 | 해결 방향 |
| --- | --- |
| 사용자의 초기 아이디어가 모호함 | 의도 분석 노드와 인터뷰 노드로 필수 정보를 단계적으로 수집 |
| LLM 단독 생성의 근거 부족 | Neo4j GraphRAG로 법령, 조례, 조문, 법률 용어를 검색 |
| 조례 문서 구조가 복잡함 | 조례 유형별 조항 큐를 만들고 조항별 입력을 분리 |
| 긴 작성 과정에서 상태 유지가 어려움 | LangGraph checkpoint와 PostgreSQL 세션 저장소 사용 |
| 사용자별 작업 내역 관리 필요 | Firebase 인증과 사용자별 세션 목록 제공 |
| 초안 생성 후 검토 UX가 부족함 | 초안 편집 모달, 법적 검토 결과, 최종안 보기 기능 제공 |

## 주요 기능

### 1. 사용자 인증과 세션 관리

- Firebase Authentication 기반 Google 로그인
- Firebase ID Token을 이용한 백엔드 API 보호
- 사용자별 조례 작성 세션 목록 조회
- 진행 중인 세션 복원
- 완료된 조례 초안 다시 보기
- 세션 삭제 API 제공

### 2. 온보딩 기반 조례 작성 시작

- 사용자가 작성하려는 조례의 목적과 배경을 자연어로 입력
- 조례 유형을 명시적으로 전달해 LLM의 추론 부담을 줄임
- 지역, 목적, 대상, 지원 방식 등 필수 정보를 수집
- 누락 정보가 있을 경우 선택지 기반 인터뷰 제공

### 3. LangGraph 기반 작성 워크플로우

- 조례 작성 과정을 독립 노드로 분리
- 현재 단계에 따라 다음 노드를 조건부 라우팅
- 세션별 `thread_id`로 상태 유지
- PostgreSQL checkpointer로 장기 세션 복원

### 4. GraphRAG 기반 법령 검색

- Neo4j에 법령, 자치법규, 조문, 법률 용어를 그래프로 적재
- 벡터 유사도 검색으로 유사 조례와 관련 조문 탐색
- `BASED_ON`, `SIMILAR_TO`, `DEFINES`, `REFERENCES`, `CONFLICTS_WITH` 등 관계 활용
- Q&A 답변에 출처 정보를 함께 제공

### 5. 조항별 상세 입력 UX

- 조례 초안 생성 전 필요한 조항 목록을 큐로 구성
- 현재 작성 중인 조항과 남은 조항을 모달에서 관리
- 조항별 내용을 직접 입력하거나 Q&A 답변을 적용
- 여러 조항을 한 번에 제출하는 일괄 입력 기능 제공

### 6. 초안 생성, 편집, 법적 검토

- 수집된 정책 정보와 법령 근거를 바탕으로 조례 초안 생성
- 사용자가 초안을 모달에서 직접 수정
- 수정된 초안을 다시 백엔드로 전달해 법적 검토 요청
- 법적 쟁점의 심각도, 관련 법령, 설명, 수정 제안 반환
- 최종 확정 후 완료 모달에서 결과 확인

### 7. 세션 기반 Q&A

- 현재 조례 작성 맥락을 반영한 질의응답
- 세션에 저장된 법령 근거와 GraphRAG 검색 결과 활용
- 답변의 출처를 법령, 조례, 법률 용어 단위로 표시
- 답변 중 조항에 적용 가능한 문구를 조항 입력에 반영 가능

## 사용자 플로우

```text
1. Google 로그인
   |
2. 세션 목록 확인 또는 새 조례 만들기
   |
3. 온보딩에서 조례 목적과 유형 입력
   |
4. AI가 부족한 정보 질문
   |
5. 관련 법령과 유사 조례 검색
   |
6. 조항별 세부 내용 입력
   |
7. 조례 초안 생성
   |
8. 사용자가 초안 편집
   |
9. 법적 검토 요청
   |
10. 쟁점 확인 및 수정
   |
11. 최종 조례안 확정
```

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Frontend | React 18, TypeScript, Vite |
| Styling/UI | CSS, 모달 기반 작성 UI, 단계 표시 컴포넌트 |
| Auth | Firebase Authentication, Firebase Admin SDK |
| Backend | FastAPI, Pydantic, Uvicorn/Gunicorn |
| Agent Workflow | LangGraph, LangChain |
| LLM Providers | Gemini, Claude, OpenAI |
| Embedding | Gemini Embedding |
| Graph Database | Neo4j 5, Vector Index, APOC |
| Persistence | PostgreSQL, LangGraph Checkpoint |
| Data Pipeline | Python, 국가법령정보센터 Open API, rdflib |
| Infra | Docker, Docker Compose, Firebase 설정, Cloud Run 대응 Dockerfile |
| Reliability | SlowAPI rate limiting, CORS 제한, 보안 헤더, 로깅 미들웨어 |

## 시스템 아키텍처

```text
┌────────────────────────────┐
│            User            │
└──────────────┬─────────────┘
               │
               v
┌────────────────────────────┐
│ React + Vite Frontend       │
│ - Google Login              │
│ - Session List              │
│ - Onboarding Wizard         │
│ - Q&A Panel                 │
│ - Draft / Article Modals    │
└──────────────┬─────────────┘
               │ Firebase ID Token
               v
┌────────────────────────────┐
│ FastAPI Backend             │
│ - Auth Guard                │
│ - REST API                  │
│ - Rate Limit                │
│ - Security Headers          │
└──────────────┬─────────────┘
               │
               v
┌────────────────────────────┐
│ LangGraph Workflow          │
│ - Intent Analysis           │
│ - Interview                 │
│ - Graph Retrieval           │
│ - Article Planning          │
│ - Draft Generation          │
│ - Draft Review              │
│ - Legal Check               │
└───────┬─────────────┬──────┘
        │             │
        v             v
┌──────────────┐  ┌────────────────┐
│ PostgreSQL   │  │ Neo4j           │
│ - Sessions   │  │ - Statutes      │
│ - Checkpoint │  │ - Ordinances    │
│ - QA History │  │ - Provisions    │
└──────────────┘  │ - Legal Terms   │
                  │ - Embeddings    │
                  └────────────────┘
```

## AI 워크플로우

LangGraph는 조례 작성 과정을 상태 기반 워크플로우로 관리합니다. 각 노드는 하나의 책임을 가지며, 현재 상태와 사용자 입력에 따라 다음 노드가 결정됩니다.

| 노드 | 역할 |
| --- | --- |
| `intent_analyzer` | 초기 입력에서 조례 목적, 대상, 지역, 지원 유형, 조례 유형 추출 |
| `interviewer` | 누락된 필수 정보를 질문하고 사용자 응답을 상태에 반영 |
| `graph_retriever` | Neo4j에서 관련 법령, 유사 조례, 법률 용어 검색 |
| `article_planner` | 조례 유형과 정책 목적에 맞는 조항 작성 큐 생성 |
| `article_interviewer` | 조항별 세부 내용을 수집하고 다음 조항으로 진행 |
| `drafting_agent` | 수집 정보와 검색 근거를 바탕으로 조례 초안 생성 |
| `draft_reviewer` | 사용자 편집 초안을 검토하고 법적 검토 단계로 라우팅 |
| `legal_checker` | 법적 쟁점, 관련 근거, 수정 제안을 구조화해 반환 |

워크플로우는 다음과 같은 단계 값을 프론트엔드와 공유합니다.

```text
intent_analysis
interviewing
retrieving
article_interviewing
article_complete
drafting
draft_review
legal_review_requested
legal_checking
completed
```

## GraphRAG 설계

이 프로젝트의 검색 계층은 단순한 벡터 검색만 사용하지 않습니다. 법령 데이터는 조문 단위로 구조화되어 있고, 조례와 법령 사이의 관계도 함께 그래프로 표현됩니다.

### 주요 노드

| 노드 | 설명 |
| --- | --- |
| `Statute` | 상위 법령 |
| `Ordinance` | 지방자치단체 자치법규 및 조례 |
| `Provision` | 법령 또는 조례의 조문 |
| `Paragraph` | 조문 내 항 |
| `Item` | 항 내 호 |
| `SubItem` | 호 내 목 |
| `LegalTerm` | 법률 용어와 정의 |

### 주요 관계

| 관계 | 의미 |
| --- | --- |
| `CONTAINS` | 법령/조례가 조문을 포함하거나 조문이 하위 구조를 포함 |
| `BASED_ON` | 조례가 특정 상위 법령에 근거함 |
| `SUPERIOR_TO` | 상위 법령이 조례보다 우선하는 법 체계 관계 |
| `SIMILAR_TO` | 조례 간 벡터 유사도 기반 유사 관계 |
| `DEFINES` | 조문이 법률 용어를 정의함 |
| `LIMITS` | 조문이 특정 법률 용어 또는 권리 주체를 제한함 |
| `REFERENCES` | 조문이 다른 조문을 인용함 |
| `CONFLICTS_WITH` | 상위 법령과 충돌 가능성이 있는 조항 |
| `PENALIZES` | 제재 조항이 특정 위반 행위를 벌칙 대상으로 삼음 |

### 검색 활용 방식

- 초안 생성 전 유사 조례와 관련 법령 근거를 검색합니다.
- Q&A에서는 세션에 이미 수집된 근거를 우선 사용하고, 부족하면 fresh search를 수행합니다.
- 법적 검토에서는 상위 법령, 조문, 법률 용어, 충돌 가능 관계를 함께 고려합니다.
- 출처 정보는 `statute`, `ordinance`, `legal_term` 타입으로 API 응답에 포함됩니다.

## 데이터 파이프라인

`pipeline/` 디렉터리는 국가법령정보센터 Open API에서 데이터를 수집하고 Neo4j에 적재하는 파이프라인입니다.

### 수집 대상

- 법령 목록과 전문
- 자치법규 및 조례 목록과 전문
- 법률 용어와 정의
- 조문 하위 구조
- 조례 검색 메타데이터

### 파이프라인 단계

1. 법령 및 조례 검색
2. 전문 XML 다운로드
3. 조문, 항, 호, 목 구조 파싱
4. 내부 데이터 모델로 변환
5. Neo4j 노드와 관계로 upsert
6. 조례 및 조문 임베딩 생성
7. 벡터 인덱스 생성
8. 유사 조례 관계 생성
9. 법령 위임, 정의, 제한, 인용, 충돌 가능성 관계 확장

### 주요 스크립트

```bash
python -m pipeline.scripts.initial_load
python -m pipeline.scripts.incremental_update
python -m pipeline.scripts.embed_ordinances
python -m pipeline.scripts.migrate_schema
python -m pipeline.scripts.migrate_relations
```

`initial_load`는 최초 데이터 적재용 스크립트입니다. 벡터 인덱스를 만들고, 필수 법령과 도메인 키워드 기반 법령/조례를 수집한 뒤 관계 생성과 임베딩을 수행합니다.

## 백엔드 구조

```text
app/
├── main.py                  # FastAPI 앱 생성, lifespan, middleware, router 등록
├── api/
│   ├── schemas.py           # API 요청/응답 모델
│   └── routers/
│       ├── chat.py          # 세션, 채팅, Q&A, finalize API
│       └── debug.py         # DEBUG_MODE에서만 노출되는 디버그 라우터
├── core/
│   ├── auth.py              # Firebase 토큰 검증
│   ├── config.py            # 환경 변수 기반 설정
│   ├── embedder.py          # 임베딩 유틸리티
│   ├── limiter.py           # rate limit 설정
│   ├── llm.py               # provider별 LLM factory
│   └── logging_config.py    # 로깅 설정
├── db/
│   ├── session_store.py     # PostgreSQL 세션 저장소
│   ├── neo4j_db.py          # GraphRAG 질의 계층
│   └── base.py              # DB 추상화
├── graph/
│   ├── workflow.py          # LangGraph 구성
│   ├── state.py             # 워크플로우 상태 타입
│   ├── edges/conditions.py  # 조건부 라우팅
│   └── nodes/               # 각 에이전트 노드
├── prompts/                 # 에이전트별 프롬프트
└── services/
    └── qa_service.py        # 직접 검색 Q&A 서비스
```

### 백엔드 설계 특징

- `lifespan`에서 PostgreSQL connection pool과 LangGraph checkpointer를 초기화합니다.
- `AsyncPostgresSaver`를 사용해 LangGraph 상태를 세션별로 유지합니다.
- 세션 메타데이터와 채팅 기록은 별도 `sessions` 테이블에 저장합니다.
- 인증된 사용자만 자신의 세션에 접근할 수 있도록 ownership 검증을 수행합니다.
- `DEBUG_MODE`가 켜진 경우에만 디버그 라우터를 등록합니다.
- CORS 허용 origin을 환경 변수로 제한합니다.
- 보안 헤더와 요청 로깅 미들웨어를 적용합니다.

## 프론트엔드 구조

```text
frontend/src/
├── App.tsx                         # 앱 상태와 전체 화면 흐름
├── api.ts                          # 백엔드 API client
├── firebase.ts                     # Firebase client auth 설정
├── types.ts                        # API 응답과 UI 상태 타입
├── constants/
│   └── interviewOptions.ts         # 온보딩 선택지
└── components/
    ├── SessionListScreen.tsx       # 사용자 세션 목록
    ├── OnboardingWizard.tsx        # 새 조례 시작 플로우
    ├── QAPanel.tsx                 # 세션 기반 Q&A 패널
    ├── ArticleItemsModal.tsx       # 조항별 입력 모달
    ├── DraftModal.tsx              # 초안 편집 및 법적 검토 모달
    ├── CompletedDraftModal.tsx     # 최종안 보기 모달
    ├── StageIndicator.tsx          # 현재 진행 단계 표시
    ├── LoadingModal.tsx            # 처리 중 상태 표시
    ├── LegalIssuesPanel.tsx        # 법적 쟁점 표시
    └── TutorialOverlay.tsx         # 튜토리얼 오버레이
```

### 프론트엔드 설계 특징

- 세션 목록 화면과 작성 화면을 분리했습니다.
- 작성 중인 조항, 초안, 법적 검토 결과는 모달 기반으로 다룹니다.
- Q&A 패널은 항상 접근 가능하도록 작성 화면의 주요 영역에 배치했습니다.
- 첫 로그인 사용자를 위한 튜토리얼 오버레이를 제공합니다.
- 글자 크기 조절 기능을 제공해 긴 법령 문서 검토 환경을 고려했습니다.
- 인앱 브라우저에서 Google OAuth가 차단되는 문제를 감지하고 안내합니다.

## 로컬 실행 방법

### 1. 환경 변수 준비

`.env.example`을 복사해 `.env`를 생성합니다.

```bash
cp .env.example .env
```

주요 환경 변수:

| 변수 | 설명 |
| --- | --- |
| `GOOGLE_API_KEY` | Gemini 및 embedding 호출용 API key |
| `OPENAI_API_KEY` | OpenAI 모델 호출용 API key |
| `ANTHROPIC_API_KEY` | Claude 모델 호출용 API key |
| `LLM_INTENT` | 의도 분석에 사용할 provider |
| `LLM_DRAFTING` | 초안 작성에 사용할 provider |
| `LLM_REVIEWER` | 초안 리뷰에 사용할 provider |
| `LLM_LEGAL` | 법적 검토에 사용할 provider |
| `NEO4J_URI` | Neo4j 또는 AuraDB 접속 URI |
| `NEO4J_USER` | Neo4j 사용자명 |
| `NEO4J_PASSWORD` | Neo4j 비밀번호 |
| `POSTGRES_URL` | LangGraph checkpoint와 세션 저장용 PostgreSQL URL |
| `POSTGRES_PASSWORD` | Docker Compose PostgreSQL 비밀번호 |
| `FIREBASE_CREDENTIALS_PATH` | Firebase service account JSON 경로 |
| `CORS_ORIGINS` | 허용할 프론트엔드 origin 목록 |
| `VITE_FIREBASE_API_KEY` | Firebase Web App API key |
| `VITE_FIREBASE_AUTH_DOMAIN` | Firebase auth domain |
| `VITE_FIREBASE_PROJECT_ID` | Firebase project id |

### 2. Docker Compose로 전체 실행

```bash
docker compose up --build
```

기본 접속 주소:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Neo4j Browser: `http://localhost:7474`
- PostgreSQL: 내부 Docker 네트워크에서 `postgres:5432`

### 3. 백엔드 단독 실행

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

백엔드 단독 실행 시 Neo4j와 PostgreSQL이 먼저 준비되어 있어야 합니다.

### 4. 프론트엔드 단독 실행

```bash
cd frontend
npm install
npm run dev
```

Vite 개발 서버는 기본적으로 `http://localhost:5173`에서 실행됩니다.

### 5. 데이터 적재

Neo4j가 비어 있다면 파이프라인을 통해 법령/조례 데이터를 먼저 적재해야 합니다.

```bash
python -m pipeline.scripts.initial_load
```

데이터 적재에는 국가법령정보센터 API key와 Gemini embedding key가 필요합니다.

## API 요약

| Method | Endpoint | 설명 |
| --- | --- | --- |
| `GET` | `/api/v1/sessions` | 현재 사용자 세션 목록 조회 |
| `POST` | `/api/v1/session` | 새 조례 작성 세션 생성 |
| `GET` | `/api/v1/session/{session_id}` | 세션 상태, 초안, Q&A 기록 복원 |
| `DELETE` | `/api/v1/session/{session_id}` | 사용자 본인의 세션 삭제 |
| `POST` | `/api/v1/session/{session_id}/chat` | 기존 세션에서 워크플로우 진행 |
| `POST` | `/api/v1/session/{session_id}/articles_batch` | 조항 내용을 일괄 제출 |
| `POST` | `/api/v1/session/{session_id}/qa` | 세션 맥락 기반 Q&A |
| `POST` | `/api/v1/session/{session_id}/finalize` | 최종 조례 초안 확정 |
| `POST` | `/api/v1/qa` | 세션 없이 직접 법령 Q&A |

### 대표 응답 데이터

`ChatResponse`는 프론트엔드가 화면 상태를 결정하는 핵심 응답입니다.

```json
{
  "session_id": "uuid",
  "message": "AI response",
  "stage": "draft_review",
  "is_complete": false,
  "draft": "...",
  "legal_issues": [],
  "is_legally_valid": null,
  "similar_ordinances": [],
  "article_queue": [],
  "current_article_key": null,
  "suggested_options": [],
  "ordinance_type": "지원"
}
```

## 디렉터리 구조

```text
.
├── app/                         # FastAPI 백엔드와 LangGraph 워크플로우
├── frontend/                    # React + Vite 프론트엔드
├── pipeline/                    # 법령/조례 수집, 변환, Neo4j 적재 파이프라인
├── pipeline_test/               # 법령 API와 파싱 검증용 단계별 테스트
├── docs/                        # 기능별 기획, 설계, 분석, 리포트 문서
├── public/                      # 정적 파일
├── Dockerfile                   # 백엔드 배포 이미지
├── docker-compose.yml           # 로컬 통합 실행 환경
├── firebase.json                # Firebase 배포 설정
├── apphosting.emulator.yaml     # Firebase App Hosting emulator 설정
├── requirements.txt             # 백엔드 Python 의존성
└── ordinance.rdf                # 조례 도메인 RDF/OWL 리소스
```

## 포트폴리오 포인트

### 1. 법률 도메인에 맞춘 GraphRAG 구현

이 프로젝트는 단순히 문서를 벡터 DB에 넣고 검색하는 방식이 아닙니다. 법령, 조례, 조문, 법률 용어를 각각 그래프 노드로 모델링하고, 법적 위임 관계와 유사 조례 관계를 함께 활용합니다. 이를 통해 초안 생성과 Q&A에서 더 설명 가능한 근거를 제공합니다.

### 2. LangGraph 기반 복합 워크플로우

조례 작성은 한 번의 프롬프트로 끝나는 작업이 아니기 때문에 상태 머신으로 설계했습니다. 각 노드는 독립적인 책임을 가지며, 사용자의 입력과 현재 작성 단계에 따라 다른 경로로 이동합니다. 이 구조는 긴 작성 세션을 안정적으로 관리하는 데 유리합니다.

### 3. 멀티 LLM 역할 분담

`LLM_INTENT`, `LLM_DRAFTING`, `LLM_REVIEWER`, `LLM_LEGAL`을 분리해 작업 특성에 맞는 provider를 선택할 수 있도록 구성했습니다. 예를 들어 의도 분석은 구조화 추출에 강한 모델, 초안 작성은 장문 생성에 강한 모델, 법적 검토는 비판적 분석에 적합한 모델로 나누어 운영할 수 있습니다.

### 4. 실무 문서 작성 UX

챗봇 형태만 제공하지 않고, 조항 입력 모달과 초안 편집 모달을 별도로 설계했습니다. 사용자는 AI가 생성한 내용을 그대로 받는 것이 아니라, 조항별로 필요한 내용을 채우고, 초안을 직접 수정하고, 법적 검토 결과를 반영할 수 있습니다.

### 5. 운영 환경을 고려한 백엔드

Firebase 인증, 사용자별 세션 소유권 검증, rate limiting, CORS 제한, 보안 헤더, PostgreSQL 기반 checkpoint, Docker 배포 구성이 포함되어 있습니다. 프로토타입 수준을 넘어 실제 서비스 운영을 고려한 구조입니다.

### 6. 데이터 최신화와 재실행 가능성

Neo4j 적재 로직은 `MERGE` 기반으로 재실행 가능하게 설계되어 있습니다. 초기 적재, 증분 업데이트, 임베딩 생성, 관계 마이그레이션 스크립트를 분리해 데이터 갱신과 스키마 확장을 관리할 수 있습니다.

## 향후 개선 방향

- 법적 검토 결과에서 근거 조문 하이라이트와 원문 링크 제공
- 조례 유형별 템플릿과 조항 추천 로직 고도화
- 법령 변경 감지 후 영향받는 조례 초안 자동 재검토
- 관리자용 그래프 데이터 품질 모니터링 대시보드 추가
- 초안 버전 관리와 변경 이력 비교 기능 추가
- 조례 초안 다운로드 형식 확대
- 검색 근거의 신뢰도 점수와 설명 가능성 강화
- 테스트셋 기반 조례 초안 품질 평가 자동화

## 프로젝트 한 줄 요약

Ordinance Builder AI는 법령 지식 그래프와 상태 기반 AI 워크플로우를 결합해, 사용자의 정책 아이디어를 근거 있는 조례 초안으로 발전시키는 조례 작성 보조 시스템입니다.
