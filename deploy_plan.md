# 조례 빌더 AI — 배포 계획서

> 대상: 다수의 사용자, 사용자별 세션 격리  
> 목표 인프라: GCP (Cloud Run + Cloud SQL + Firebase Hosting + Neo4j AuraDB)

---

## 목차

1. [현황 진단](#1-현황-진단)
2. [코드 수정 계획](#2-코드-수정-계획)
   - 2-1. SQLite → PostgreSQL 체크포인터
   - 2-2. JSON 파일 → PostgreSQL 세션 레지스트리
   - 2-3. Firebase Auth 통합 (백엔드)
   - 2-4. Firebase Auth 통합 (프론트엔드)
   - 2-5. 비동기 LLM 호출
   - 2-6. Dockerfile 운영 설정
3. [GCP 인프라 구성](#3-gcp-인프라-구성)
4. [배포 절차](#4-배포-절차)
5. [완료 체크리스트](#5-완료-체크리스트)

---

## 1. 현황 진단

다수 사용자 배포 전 반드시 해결해야 할 문제들입니다.

| 구분 | 현재 상태 | 문제점 |
|------|-----------|--------|
| **LangGraph 체크포인터** | `SqliteSaver` (파일 기반 SQLite) | 다중 인스턴스 공유 불가, Cloud Run 재시작 시 상태 소실 |
| **세션 레지스트리** | `sessions_registry.json` + 인메모리 dict | 다중 인스턴스 간 불일치, 파일 동시 쓰기 경쟁 |
| **인증/인가** | 없음 | 세션 UUID만 알면 타인 세션에 무제한 접근 가능 |
| **LLM 호출** | `graph.invoke()` (동기) | FastAPI async 환경에서 스레드 블로킹, 동시 접속자 증가 시 병목 |
| **환경 변수** | `.env` 파일 직접 관리 | 비밀 값 Git 노출 위험, 인스턴스별 수동 배포 필요 |

---

## 2. 코드 수정 계획

수정은 **백엔드 → 프론트엔드 순**, 각 단계를 독립적으로 완료하고 테스트합니다.

---

### 2-1. SQLite → PostgreSQL 체크포인터

**영향 파일**: `requirements.txt`, `app/core/config.py`, `app/graph/workflow.py`

#### requirements.txt

```diff
- langgraph-checkpoint-sqlite>=2.0.0
+ langgraph-checkpoint-postgres>=2.0.0
+ psycopg[binary]>=3.1.0
```

#### app/core/config.py

```python
class Settings(BaseSettings):
    GOOGLE_API_KEY: str
    MAX_INTERVIEW_TURNS: int = 5
    LOG_LEVEL: str = "INFO"
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"

    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str

    # SQLite 제거, PostgreSQL URL로 교체
    POSTGRES_URL: str  # e.g. postgresql://user:pass@host:5432/dbname

    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
```

#### app/graph/workflow.py

```python
import sqlite3  # 제거
from langgraph.checkpoint.sqlite import SqliteSaver  # 제거

from langgraph.checkpoint.postgres import PostgresSaver  # 추가

def create_workflow():
    llm = get_llm()
    db = Neo4jGraphDB(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)

    builder: StateGraph = StateGraph(OrdinanceBuilderState)
    # ... 노드/엣지 등록 (변경 없음) ...

    # SQLite 제거
    # conn = sqlite3.connect(settings.CHECKPOINT_DB_PATH, check_same_thread=False)
    # memory = SqliteSaver(conn)

    # PostgreSQL로 교체
    memory = PostgresSaver.from_conn_string(settings.POSTGRES_URL)
    memory.setup()  # 체크포인트 테이블 초기화 (최초 1회)

    compiled = builder.compile(checkpointer=memory)
    return compiled, memory
```

---

### 2-2. JSON 파일 → PostgreSQL 세션 레지스트리

**영향 파일**: `app/db/session_store.py` (신규), `app/api/routers/chat.py`

#### app/db/session_store.py (신규)

파일 기반 레지스트리를 PostgreSQL 테이블로 교체합니다.

```python
"""
세션 메타데이터 저장소.
sessions_registry.json 및 인메모리 dict를 대체합니다.
"""
import psycopg
from app.core.config import settings


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '새 조례',
    stage       TEXT NOT NULL DEFAULT 'intent_analysis',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    chat_history JSONB NOT NULL DEFAULT '[]'::jsonb,
    initial_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
"""


def init_db():
    """앱 시작 시 1회 호출 — 테이블이 없으면 생성."""
    with psycopg.connect(settings.POSTGRES_URL) as conn:
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()


def create_session(session_id: str, user_id: str, title: str,
                   initial_message: str, created_at: str):
    with psycopg.connect(settings.POSTGRES_URL) as conn:
        conn.execute(
            """INSERT INTO sessions (session_id, user_id, title, stage,
                                     created_at, initial_message)
               VALUES (%s, %s, %s, 'intent_analysis', %s, %s)""",
            (session_id, user_id, title, created_at, initial_message),
        )
        conn.commit()


def get_session(session_id: str) -> dict | None:
    with psycopg.connect(settings.POSTGRES_URL) as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = %s", (session_id,)
        ).fetchone()
    if row is None:
        return None
    cols = ["session_id", "user_id", "title", "stage",
            "created_at", "chat_history", "initial_message"]
    return dict(zip(cols, row))


def list_sessions_by_user(user_id: str) -> list[dict]:
    with psycopg.connect(settings.POSTGRES_URL) as conn:
        rows = conn.execute(
            """SELECT session_id, user_id, title, stage, created_at,
                      chat_history, initial_message
               FROM sessions WHERE user_id = %s
               ORDER BY created_at DESC""",
            (user_id,),
        ).fetchall()
    cols = ["session_id", "user_id", "title", "stage",
            "created_at", "chat_history", "initial_message"]
    return [dict(zip(cols, row)) for row in rows]


def update_session(session_id: str, stage: str, title: str,
                   chat_history: list):
    with psycopg.connect(settings.POSTGRES_URL) as conn:
        import json
        conn.execute(
            """UPDATE sessions SET stage = %s, title = %s, chat_history = %s
               WHERE session_id = %s""",
            (stage, title, json.dumps(chat_history, ensure_ascii=False), session_id),
        )
        conn.commit()
```

#### app/api/routers/chat.py — 레지스트리 관련 부분 교체

```python
# 제거할 것들
import threading
REGISTRY_FILE = "sessions_registry.json"
_registry_lock = threading.Lock()
_sessions_registry: dict = load_registry()
def load_registry(): ...
def save_registry(): ...

# 추가
from app.db.session_store import (
    create_session as db_create_session,
    get_session as db_get_session,
    list_sessions_by_user,
    update_session as db_update_session,
)
```

---

### 2-3. Firebase Auth 통합 (백엔드)

**영향 파일**: `requirements.txt`, `app/core/auth.py` (신규), `app/api/routers/chat.py`, `app/main.py`

#### requirements.txt

```diff
+ firebase-admin>=6.5.0
```

#### app/core/auth.py (신규)

```python
"""
Firebase ID Token 검증 미들웨어.
모든 API 엔드포인트에서 Depends(get_current_user)로 사용.
"""
import firebase_admin
from firebase_admin import auth as firebase_auth, credentials
from fastapi import Depends, HTTPException, Header

# GCP 환경에서는 credentials 없이 Application Default Credentials 사용
# 로컬 개발 시에는 서비스 계정 JSON 경로를 FIREBASE_CREDENTIALS_PATH 환경 변수로 지정
_app = None


def _init_firebase():
    global _app
    if _app is None:
        import os
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        if cred_path:
            cred = credentials.Certificate(cred_path)
            _app = firebase_admin.initialize_app(cred)
        else:
            _app = firebase_admin.initialize_app()  # ADC (Cloud Run에서 자동)


async def get_current_user(authorization: str = Header(...)) -> str:
    """
    Authorization: Bearer <Firebase ID Token> 헤더를 검증하고 user_id를 반환.
    검증 실패 시 401 반환.
    """
    _init_firebase()
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer 토큰이 필요합니다.")
    token = authorization[len("Bearer "):]
    try:
        decoded = firebase_auth.verify_id_token(token)
        return decoded["uid"]
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 인증 토큰입니다.")
```

#### app/api/routers/chat.py — 엔드포인트 수정

```python
from app.core.auth import get_current_user

@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(user_id: str = Depends(get_current_user)):
    """본인의 세션만 반환."""
    return [
        SessionSummary(
            session_id=s["session_id"],
            title=s["title"],
            stage=s["stage"],
            created_at=str(s["created_at"]),
        )
        for s in list_sessions_by_user(user_id)
    ]


@router.get("/session/{session_id}", response_model=SessionStateResponse)
async def get_session_state(
    session_id: str,
    user_id: str = Depends(get_current_user),
):
    entry = db_get_session(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    if entry["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    # ... 이하 동일


@router.post("/session", response_model=SessionCreateResponse)
async def create_session(
    request: SessionCreateRequest,
    user_id: str = Depends(get_current_user),  # 추가
):
    session_id = str(uuid.uuid4())
    # user_id를 포함하여 세션 생성
    db_create_session(session_id, user_id, title, initial_message, created_at)
    # ...


@router.post("/session/{session_id}/chat", response_model=ChatResponse)
async def chat(
    session_id: str,
    request: ChatRequest,
    user_id: str = Depends(get_current_user),  # 추가
):
    entry = db_get_session(session_id)
    if not entry or entry["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    # ...
```

> `/articles_batch`, `/finalize` 엔드포인트도 동일한 방식으로 `Depends(get_current_user)` 및 소유권 검증 추가.

---

### 2-4. Firebase Auth 통합 (프론트엔드)

**영향 파일**: `frontend/src/firebase.ts` (신규), `frontend/src/api.ts`, `frontend/src/App.tsx`

#### frontend/src/firebase.ts (신규)

```typescript
import { initializeApp } from 'firebase/app'
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut, onAuthStateChanged } from 'firebase/auth'

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
}

const app = initializeApp(firebaseConfig)
export const auth = getAuth(app)
export const googleProvider = new GoogleAuthProvider()

export const loginWithGoogle = () => signInWithPopup(auth, googleProvider)
export const logout = () => signOut(auth)
export { onAuthStateChanged }
```

#### frontend/src/api.ts — 모든 요청에 토큰 헤더 추가

```typescript
import { auth } from './firebase'

async function getAuthHeaders(): Promise<HeadersInit> {
  const user = auth.currentUser
  if (!user) throw new Error('로그인이 필요합니다.')
  const token = await user.getIdToken()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  }
}

export async function createSession(initialMessage: string): Promise<SessionCreateResponse> {
  const res = await fetch('/api/v1/session', {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: JSON.stringify({ initial_message: initialMessage }),
  })
  if (!res.ok) throw new Error(`세션 생성 실패: ${res.status}`)
  return res.json()
}

// sendMessage, submitArticlesBatch, finalizeSession, listSessions, getSessionState
// 모두 동일하게 headers: await getAuthHeaders() 로 교체
```

#### frontend/.env (신규)

```env
VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-project-id
```

---

### 2-5. 비동기 LLM 호출

**영향 파일**: `app/api/routers/chat.py`

현재 `graph.invoke()`는 동기 호출로 FastAPI 이벤트 루프를 블로킹합니다. LLM 호출이 수초~수십초 걸리는 특성상 동시 접속자가 늘면 병목이 됩니다.

```python
# 현재 (동기 — 이벤트 루프 블로킹)
result = graph.invoke(update, config=config)

# 수정 후 (비동기)
result = await graph.ainvoke(update, config=config)
```

`create_session`, `chat`, `submit_articles_batch`, `finalize_session` 엔드포인트 모두 동일하게 수정.

> **참고**: `PostgresSaver`는 sync/async 버전이 각각 있습니다. `graph.ainvoke()`를 사용하려면 `workflow.py`에서 `AsyncPostgresSaver`(`langgraph.checkpoint.postgres.aio`)를 사용하고, `lifespan` 훅 안에서 초기화해야 합니다.

---

### 2-6. Dockerfile 운영 설정

**영향 파일**: `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# gunicorn 추가 설치
RUN pip install --no-cache-dir gunicorn

COPY app/ ./app/

# Cloud Run은 PORT 환경변수를 주입함
# gunicorn + uvicorn worker로 프로세스 기반 동시성 확보
# --timeout 300: Gemini 호출 최대 응답 시간 대비
CMD ["sh", "-c", \
     "gunicorn app.main:app \
      -w 2 \
      -k uvicorn.workers.UvicornWorker \
      --bind 0.0.0.0:${PORT:-8000} \
      --timeout 300 \
      --log-level info"]
```

> Cloud Run 기본 설정: `--concurrency 80`, `--min-instances 1`, `--max-instances 10`

---

## 3. GCP 인프라 구성

### 전체 아키텍처

```
사용자 브라우저
      │
      ▼
Firebase Hosting (React 정적 빌드 + CDN)
      │ HTTPS API 요청 (Authorization: Bearer <token>)
      │
      ▼
Cloud Load Balancing + Cloud Armor
  └── DDoS 방어, 분당 요청 수 제한 (Rate Limiting)
      │
      ▼
Cloud Run (Backend — 자동 스케일링)
  ├── 인스턴스 1 ─┐
  ├── 인스턴스 2 ─┤── Cloud SQL (PostgreSQL 17)
  └── 인스턴스 N ─┘   ├── sessions 테이블 (세션 메타데이터 + 채팅 기록)
                       └── langgraph_checkpoints 테이블 (LangGraph 상태)
                            │
                       Neo4j AuraDB
                       (법령 그래프 DB, 관리형)
                            │
                       Gemini API
                       (GCP 내부 네트워크, 지연 최소화)
```

### 서비스별 설정

| 서비스 | 설정값 | 비고 |
|--------|--------|------|
| **Cloud Run** | CPU: 2, RAM: 2GB | LLM 호출 중 CPU 유지 (`--cpu-always-allocated`) |
| | `--min-instances=1` | 콜드 스타트 방지 |
| | `--max-instances=10` | 비용 상한 제어 |
| | `--timeout=300` | Gemini 응답 대기 |
| | `--concurrency=40` | 인스턴스당 동시 요청 |
| **Cloud SQL** | db-g1-small (PostgreSQL 17) | 세션 수 적을 때 시작점 |
| | 자동 백업 활성화 | 7일 보존 |
| **Neo4j AuraDB** | Professional 플랜 이상 | Free tier는 5GB 상한 |
| **Firebase Hosting** | 기본 설정 | `/api/**` → Cloud Run 리다이렉트 설정 |
| **Secret Manager** | 모든 민감 환경 변수 | `GOOGLE_API_KEY`, `NEO4J_PASSWORD`, DB 접속 정보 등 |

### Secret Manager 등록 항목

```
GOOGLE_API_KEY
NEO4J_URI
NEO4J_USER
NEO4J_PASSWORD
POSTGRES_URL
FIREBASE_PROJECT_ID
```

---

## 4. 배포 절차

### Phase 1: GCP 프로젝트 준비

```bash
# 프로젝트 생성 및 API 활성화
gcloud projects create ordinance-builder-prod
gcloud config set project ordinance-builder-prod

gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  firebase.googleapis.com \
  artifactregistry.googleapis.com
```

### Phase 2: Cloud SQL (PostgreSQL) 생성

```bash
gcloud sql instances create ordinance-db \
  --database-version=POSTGRES_17 \
  --tier=db-g1-small \
  --region=asia-northeast3 \
  --backup-start-time=03:00

gcloud sql databases create ordinance_builder \
  --instance=ordinance-db

gcloud sql users create app_user \
  --instance=ordinance-db \
  --password=<strong_password>
```

### Phase 3: Neo4j AuraDB 연결

1. [Neo4j AuraDB](https://console.neo4j.io) 콘솔에서 인스턴스 생성
2. Connection URI, 사용자명, 비밀번호 메모
3. Secret Manager에 등록

```bash
echo -n "neo4j+s://xxxx.databases.neo4j.io" | \
  gcloud secrets create NEO4J_URI --data-file=-
```

### Phase 4: Firebase 프로젝트 설정

1. [Firebase 콘솔](https://console.firebase.google.com)에서 프로젝트 생성 (기존 GCP 프로젝트 연결)
2. Authentication → 로그인 방법 → Google 활성화
3. (선택) 허용 도메인 제한: `*.go.kr` (공무원 이메일만 허용)
4. 웹 앱 등록 → `VITE_FIREBASE_*` 설정값 확인

### Phase 5: 백엔드 빌드 및 Cloud Run 배포

```bash
# Artifact Registry 저장소 생성
gcloud artifacts repositories create ordinance-backend \
  --repository-format=docker \
  --location=asia-northeast3

# 이미지 빌드 및 푸시
gcloud builds submit \
  --tag asia-northeast3-docker.pkg.dev/ordinance-builder-prod/ordinance-backend/app:latest

# Cloud Run 배포
gcloud run deploy ordinance-backend \
  --image asia-northeast3-docker.pkg.dev/ordinance-builder-prod/ordinance-backend/app:latest \
  --region asia-northeast3 \
  --platform managed \
  --min-instances 1 \
  --max-instances 10 \
  --timeout 300 \
  --concurrency 40 \
  --memory 2Gi \
  --cpu 2 \
  --cpu-boost \
  --set-secrets "GOOGLE_API_KEY=GOOGLE_API_KEY:latest,\
NEO4J_URI=NEO4J_URI:latest,\
NEO4J_USER=NEO4J_USER:latest,\
NEO4J_PASSWORD=NEO4J_PASSWORD:latest,\
POSTGRES_URL=POSTGRES_URL:latest" \
  --set-env-vars "CORS_ORIGINS=https://your-project.web.app"
```

### Phase 6: 프론트엔드 빌드 및 Firebase Hosting 배포

```bash
cd frontend

# .env.production 작성
cat > .env.production << EOF
VITE_FIREBASE_API_KEY=<value>
VITE_FIREBASE_AUTH_DOMAIN=ordinance-builder-prod.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=ordinance-builder-prod
VITE_API_BASE_URL=https://<cloud-run-url>
EOF

# 프로덕션 빌드
npm run build

# Firebase CLI 배포
npm install -g firebase-tools
firebase login
firebase init hosting
firebase deploy --only hosting
```

#### firebase.json (API 요청 프록시 설정)

```json
{
  "hosting": {
    "public": "dist",
    "ignore": ["firebase.json", "**/.*"],
    "rewrites": [
      {
        "source": "/api/**",
        "run": {
          "serviceId": "ordinance-backend",
          "region": "asia-northeast3"
        }
      },
      {
        "source": "**",
        "destination": "/index.html"
      }
    ]
  }
}
```

### Phase 7: ETL 파이프라인 실행 (최초 1회)

AuraDB 연결 정보를 `.env`에 설정한 뒤 로컬 또는 Cloud Build에서 실행:

```bash
python -m pipeline.scripts.initial_load
```

---

## 5. 완료 체크리스트

### 코드 수정

- [x] `requirements.txt`: `langgraph-checkpoint-sqlite` → `langgraph-checkpoint-postgres`, `psycopg[binary]`, `firebase-admin` 추가
- [x] `app/core/config.py`: `CHECKPOINT_DB_PATH` 제거, `POSTGRES_URL` 추가
- [x] `app/graph/workflow.py`: `SqliteSaver` → `AsyncPostgresSaver` 교체, checkpointer 외부 주입 구조로 변경
- [x] `app/db/session_store.py`: PostgreSQL 기반 세션 CRUD 구현 (신규)
- [x] `app/core/auth.py`: Firebase ID Token 검증 미들웨어 구현 (신규)
- [x] `app/main.py`: lifespan 훅에서 `AsyncPostgresSaver` 초기화 및 `init_db()` 호출
- [x] `app/api/routers/chat.py`:
  - [x] JSON 파일 레지스트리 코드 제거
  - [x] `session_store` 함수 사용으로 교체
  - [x] 모든 엔드포인트에 `Depends(get_current_user)` 추가
  - [x] 세션 소유권 검증 (`user_id != entry["user_id"]` → 403) 추가
  - [x] `graph.invoke()` → `graph.ainvoke()`, `graph.aget_state()`, `graph.aupdate_state()` 교체
- [x] `Dockerfile`: `gunicorn` 추가, `CMD` 교체
- [x] `frontend/package.json`: `firebase ^10.14.0` 추가
- [x] `frontend/src/firebase.ts`: Firebase 초기화 모듈 추가 (신규)
- [x] `frontend/src/api.ts`: 모든 요청에 `Authorization` 헤더 추가
- [x] `frontend/src/App.tsx`: 로그인/로그아웃 UI 및 인증 상태 관리 추가
- [x] `frontend/.env.example`: Firebase 설정값 템플릿 추가

### GCP 인프라

- [ ] GCP 프로젝트 생성 및 필요 API 활성화
- [ ] Cloud SQL PostgreSQL 인스턴스 및 DB 생성
- [ ] Neo4j AuraDB 인스턴스 생성
- [ ] Firebase 프로젝트 생성 및 Google 로그인 활성화
- [ ] Secret Manager에 모든 민감 환경 변수 등록
- [ ] Artifact Registry 저장소 생성
- [ ] Cloud Run 서비스 배포
- [ ] Firebase Hosting 배포 (`firebase.json` API 프록시 포함)
- [ ] ETL 파이프라인 실행 (AuraDB에 법령 데이터 적재)

### 배포 후 검증

- [ ] Google 로그인 후 세션 생성 정상 작동
- [ ] 서로 다른 계정으로 로그인 시 세션 격리 확인 (타인 세션 403 응답)
- [ ] Cloud Run 로그에서 LangGraph 노드 실행 흐름 확인
- [ ] Cloud SQL에서 `sessions` 테이블 데이터 적재 확인
- [ ] Neo4j AuraDB 연결 및 법령 검색 정상 작동 확인
- [ ] CORS 오류 없음 확인 (Firebase Hosting 도메인 → Cloud Run)

---

## 부록: 비용 추정 (일 100세션 기준)

| 항목 | 예상 비용/월 |
|------|-------------|
| Cloud Run (min 1 인스턴스) | ~$15–30 |
| Cloud SQL db-g1-small | ~$10 |
| Neo4j AuraDB Professional | ~$65 (1GB RAM) |
| Firebase Hosting | $0 (무료 tier) |
| Secret Manager | ~$1 미만 |
| **Gemini API** | **~$50–200** (세션당 $0.05–0.20, 가장 큰 비용) |
| **합계** | **~$141–306/월** |

> Gemini API 비용이 지배적입니다. 서비스 정책상 세션 수 제한(예: 1일 5건/사용자) 또는 초안 생성 단계에만 과금하는 구조를 검토하세요.
