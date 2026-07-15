# Ordinance Builder AI

지방자치단체 조례 초안 작성을 지원하는 GraphRAG 애플리케이션입니다. 정책 의도를 단계적으로 수집하고 Neo4j에서 관련 법령·조례를 검색한 뒤 LLM으로 초안을 작성·검토합니다. 연구·개발 단계의 도구이며 법률 자문이나 최종 입법 검토를 대체하지 않습니다.

## 핵심 기능

- Firebase Google 로그인과 사용자별 작성 세션
- 자연어 의도 분석, 누락 정보 인터뷰, 조항별 상세 입력
- Neo4j 그래프·벡터 검색 기반 법령 및 유사 조례 조회
- 초안 생성, 사용자 편집, 재검토, 법률 검증
- 세션 문맥 Q&A 및 독립 GraphRAG Q&A
- TXT/DOCX 내보내기
- 역할별 클라우드/로컬 LLM 선택 및 활성 모델 상태 UI

## 아키텍처와 기술 스택

```text
React 18 + TypeScript + Vite
        │ Firebase ID token
        ▼
FastAPI + LangGraph + LangChain
   ├─ 역할별 LLM provider
   ├─ Neo4j: 지식 그래프와 벡터 검색
   ├─ PostgreSQL: LangGraph checkpoint와 세션
   └─ Firebase Admin: API 인증

법령 API/원천 데이터 → pipeline → Gemini embedding → Neo4j
```

| 영역 | 구현 |
| --- | --- |
| API | Python, FastAPI, Pydantic, Gunicorn/Uvicorn |
| 워크플로 | LangGraph, LangChain |
| LLM | Gemini, OpenAI, Anthropic, Ollama, OpenAI 호환 endpoint |
| 저장소 | Neo4j 5.23/APOC, PostgreSQL 17 |
| 인증 | Firebase Authentication/Admin SDK |
| UI | React 18, TypeScript, Vite |
| 실행 | Docker Compose |

## 현재 LangGraph 단계

| 노드 | 역할 | LLM 설정 |
| --- | --- | --- |
| `intent_analyzer` | 입력에서 기본 정보 추출 | `LLM_INTENT` |
| `interviewer` | 누락 정보 질문 | 없음 |
| `graph_retriever` | Neo4j 법령·유사 조례 검색 | 없음 |
| `article_planner` | 조항 목록 결정 | 없음 |
| `article_interviewer` | 조항별 정보 수집 | 없음 |
| `drafting_agent` | 초안 생성 | `LLM_DRAFTING` |
| `draft_reviewer` | 초안 검토·수정 | `LLM_REVIEWER` |
| `legal_checker` | 법률 충돌·위임 범위 검증 | `LLM_LEGAL` |

각 요청은 필요한 지점까지 실행된 뒤 사용자 입력을 기다립니다. 상태는 PostgreSQL checkpointer와 세션 저장소에 유지됩니다.

## LLM provider

지원값은 `gemini`, `openai`, `anthropic`, `ollama`, `openai_compatible`입니다. 네 역할을 독립 설정하므로 클라우드와 로컬 모델을 혼합할 수 있습니다.

```dotenv
LLM_INTENT=gemini
LLM_INTENT_MODEL=gemini-2.5-pro
LLM_DRAFTING=ollama
LLM_DRAFTING_MODEL=qwen2.5:14b
LLM_REVIEWER=openai_compatible
LLM_REVIEWER_MODEL=local-model
LLM_LEGAL=anthropic
LLM_LEGAL_MODEL=claude-opus-4-7
```

로컬 모델도 구조화 출력과 긴 한국어 법률 문서를 안정적으로 처리해야 합니다.

### 모델 상태 UI/API

`GET /api/v1/model-status`는 endpoint와 credential을 제외하고 역할별 `provider`, `model`, `deployment`, `status`를 반환합니다. 프론트엔드는 이를 `available`, `degraded`, `unavailable`로 표시합니다. UI는 서버 설정을 보여 줄 뿐 endpoint나 API key를 변경하지 않습니다.

현재 가용 상태는 설정값 존재 여부를 기준으로 하며 실제 모델 endpoint health check는 하지 않습니다.

## 완전 오프라인이 아닌 이유

생성 LLM 네 역할은 모두 로컬화할 수 있지만 시스템 전체는 아직 완전 오프라인이 아닙니다.

- 임베딩은 `models/gemini-embedding-001`을 사용합니다.
- Neo4j 벡터 인덱스는 3072차원 Gemini 임베딩에 맞춰져 있습니다.
- 질문 임베딩과 데이터 적재·재임베딩에는 Google API가 필요합니다.
- 데이터 갱신은 외부 법령 API, Google 로그인은 Firebase 연결이 필요합니다.

로컬 임베딩 전환에는 전체 벡터 재생성과 Neo4j 인덱스 재구축이 필요합니다.

## 사전 요구사항

Docker 실행에는 Docker Compose v2, Firebase 프로젝트/서비스 계정 JSON, 사용하는 클라우드 API key가 필요합니다. 데이터 파이프라인에는 법령 API key와 Gemini key도 필요합니다.

직접 실행 시 Python 3.11+, Node.js 20+, PostgreSQL, Neo4j 5.x/APOC를 권장합니다. 로컬 LLM은 Ollama 또는 별도 OpenAI 호환 서버가 필요합니다.

## 환경변수

```powershell
Copy-Item .env.example .env
```

| 변수 | 설명 |
| --- | --- |
| `GOOGLE_API_KEY` | Gemini LLM/임베딩 사용 시 필요 |
| `OPENAI_API_KEY` | `openai` 사용 시 필요 |
| `ANTHROPIC_API_KEY` | `anthropic` 사용 시 필요 |
| `LLM_INTENT`, `LLM_DRAFTING`, `LLM_REVIEWER`, `LLM_LEGAL` | 역할별 provider |
| `LLM_INTENT_MODEL`, `LLM_DRAFTING_MODEL`, `LLM_REVIEWER_MODEL`, `LLM_LEGAL_MODEL` | 역할별 모델명 |
| `LLM_OLLAMA_BASE_URL` | 기본 `http://localhost:11434` |
| `LLM_OPENAI_COMPATIBLE_BASE_URL` | 기본 `http://localhost:11434/v1` |
| `LLM_OPENAI_COMPATIBLE_API_KEY` | 호환 서버가 인증을 요구할 때 사용 |
| `LLM_TIMEOUT_SECONDS` | LLM 제한 시간, 기본 120초 |
| `LLM_FALLBACK_ENABLED` | 기본 `false`; 자동 fallback 동작은 아직 미구현 |
| `EMBEDDING_MODEL` | 기본 `models/gemini-embedding-001` |
| `MAX_INTERVIEW_TURNS` | 기본 정보 인터뷰 최대 횟수 |
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | Neo4j 연결 |
| `POSTGRES_URL` | PostgreSQL 연결 문자열 |
| `POSTGRES_PASSWORD` | Compose PostgreSQL 비밀번호 |
| `LAW_API_KEY` | 파이프라인의 법령 API key |
| `FIREBASE_CREDENTIALS_PATH` | Firebase 서비스 계정 JSON 경로 |
| `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID` | Firebase 웹 앱 설정 |
| `VITE_API_BASE_URL` | 빈 값이면 동일 origin 사용 |
| `DEBUG_MODE` | `true`일 때만 debug API 등록 |
| `CORS_ORIGINS` | 쉼표로 구분한 허용 origin |

## Docker 실행

루트에 `firebase-service-account.json`을 준비하고 `.env`를 설정합니다. Compose 내부 주소를 사용하십시오.

```dotenv
NEO4J_URI=bolt://neo4j:7687
POSTGRES_URL=postgresql://app_user:<비밀번호>@postgres:5432/ordinance_builder
```

클라우드 LLM 구성:

```powershell
docker compose up --build
```

Ollama `local-llm` profile:

```powershell
docker compose --profile local-llm up -d ollama
docker compose exec ollama ollama pull qwen2.5:14b
docker compose --profile local-llm up --build
```

```dotenv
LLM_DRAFTING=ollama
LLM_DRAFTING_MODEL=qwen2.5:14b
LLM_OLLAMA_BASE_URL=http://ollama:11434
```

- 앱: <http://localhost:3000>
- OpenAPI: <http://localhost:8000/docs>
- Neo4j Browser: <http://localhost:7474>
- Ollama API: <http://localhost:11434>

## 직접 실행

```powershell
docker compose up -d postgres neo4j
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

다른 터미널에서:

```powershell
Set-Location frontend
npm install
npm run dev
```

호스트 Ollama는 기본 `http://localhost:11434`로 연결합니다.

## Neo4j 로컬/Aura 전환

```dotenv
# 호스트에서 로컬 Neo4j
NEO4J_URI=bolt://localhost:7687
# Docker backend에서 Compose Neo4j
NEO4J_URI=bolt://neo4j:7687
# Aura
NEO4J_URI=neo4j+s://<instance-id>.databases.neo4j.io
```

URI 변경은 데이터를 복제하지 않습니다. Aura와 로컬 사이의 데이터 이전은 별도 작업입니다.

## 데이터 파이프라인

프로젝트 루트에서 실행하며 `LAW_API_KEY`, Neo4j 설정, `GOOGLE_API_KEY`가 필요합니다.

```powershell
python -m pipeline.scripts.initial_load
python -m pipeline.scripts.resume_load
python -m pipeline.scripts.incremental_update
python -m pipeline.scripts.type_load --type "설치·운영"
python -m pipeline.scripts.type_load --type all
python -m pipeline.scripts.embed_ordinances --dry-run
python -m pipeline.scripts.embed_ordinances
python -m pipeline.scripts.migrate_schema
python -m pipeline.scripts.migrate_relations --dry-run
python -m pipeline.scripts.migrate_relations --target local
```

대량 적재와 마이그레이션 전에는 Neo4j를 백업하십시오.

## API 개요

대부분의 API는 Firebase Bearer token을 요구합니다.

| 메서드 | 경로 | 용도 |
| --- | --- | --- |
| GET | `/api/v1/model-status` | 활성 모델 구성 |
| POST | `/api/v1/session` | 세션 생성 |
| GET | `/api/v1/sessions` | 세션 목록 |
| GET/DELETE | `/api/v1/session/{session_id}` | 상태 조회/삭제 |
| POST | `/api/v1/session/{session_id}/chat` | 워크플로 입력 |
| POST | `/api/v1/session/{session_id}/articles_batch` | 조항 일괄 제출 |
| POST | `/api/v1/session/{session_id}/finalize` | 최종안 확정 |
| GET | `/api/v1/session/{session_id}/export` | TXT/DOCX 내보내기 |
| POST | `/api/v1/session/{session_id}/qa` | 세션 Q&A |
| POST | `/api/v1/qa` | 독립 GraphRAG Q&A |

`DEBUG_MODE=true`에서만 `/api/v1/debug/*`가 등록됩니다. 운영에서는 활성화하지 마십시오.

## 테스트와 빌드

일반적인 pytest 스위트는 아직 정립되지 않았고 `pipeline_test`에 단계별 확인 스크립트가 있습니다.

```powershell
python -m compileall app pipeline
python pipeline_test/step5_neo4j_basic.py
python pipeline_test/step6_integration.py
Set-Location frontend
npm run build
```

파이프라인 테스트는 실제 DB나 외부 API를 사용할 수 있으므로 대상과 비용을 먼저 확인하십시오.

## 디렉터리 구조

```text
app/              FastAPI, 설정, DB, LangGraph, prompt, service
frontend/src/     React/TypeScript UI
pipeline/         법령 API, 변환, Neo4j 적재, 실행 script
pipeline_test/    단계별 파이프라인 확인
docs/             계획·설계·보고 문서
ordinance.rdf     온톨로지/SWRL 정의
docker-compose.yml
```

## 보안과 운영

- `.env`, Firebase 서비스 계정, API key, DB 비밀번호를 커밋하지 마십시오.
- 운영에서는 `DEBUG_MODE=false`, 제한된 `CORS_ORIGINS`, 사설 DB 네트워크를 사용하십시오.
- 모델 상태 API에 endpoint나 credential을 추가하지 마십시오.
- 자동 클라우드 fallback은 현재 없습니다. 민감 데이터가 외부로 나가지 않도록 provider를 명시하십시오.
- LLM 결과와 법률 검증은 담당자가 최종 확인해야 합니다.
- 장문 생성은 컨텍스트 길이, GPU 메모리, proxy timeout의 영향을 받습니다.
- 외부 API와 클라우드 모델은 비용 및 rate limit이 발생합니다.

## 제한과 로드맵

현재 제한:

- 로컬 모델 설치·다운로드·적합성 검사는 자동화되지 않았습니다.
- 모델 상태는 설정만 검사하며 실시간 endpoint 진단은 없습니다.
- `LLM_FALLBACK_ENABLED`는 설정 필드만 존재하고 자동 fallback은 미구현입니다.
- Gemini 3072차원 임베딩 의존성 때문에 완전 오프라인이 아닙니다.
- 모델은 서버 환경변수로 선택하며 사용자별 선택 UI는 없습니다.
- 법률 정확성과 최신성은 원천 데이터, 검색 품질, 선택 모델에 좌우됩니다.

로드맵 후보:

1. endpoint 및 구조화 출력 capability health check
2. 로컬 임베딩과 Neo4j 전체 재색인 절차
3. 관리자 전용 모델 구성·진단 화면
4. 모델별 품질·지연·자원 벤치마크
5. 명시적 opt-in fallback과 감사 로그
6. 백엔드·프론트엔드·브라우저 자동 테스트 확대
