# 조례 빌더 AI — 배포 진행 현황

> 최종 갱신: 2026-04-15  
> 참고 문서: [deploy_plan.md](deploy_plan.md)

---

## 전체 진행률

| 단계 | 항목 | 상태 |
|------|------|------|
| **코드 수정** | 11개 항목 | ✅ 완료 |
| **GCP 인프라** | 9개 항목 | ⬜ 미착수 |
| **배포 후 검증** | 6개 항목 | ⬜ 미착수 |

---

## ✅ 완료: 코드 수정

### 백엔드

#### `requirements.txt`
- `langgraph-checkpoint-sqlite` 제거
- `langgraph-checkpoint-postgres>=2.0.0` 추가
- `psycopg[binary]>=3.1.0` 추가
- `gunicorn>=22.0.0` 추가
- `firebase-admin>=6.5.0` 추가

#### `app/core/config.py`
- `CHECKPOINT_DB_PATH` (SQLite 경로) 제거
- `POSTGRES_URL` 추가 — LangGraph 체크포인터 + 세션 레지스트리 공용
- `FIREBASE_CREDENTIALS_PATH` 추가 — 로컬 개발용 서비스 계정 JSON 경로 (Cloud Run에서는 ADC 자동 사용)

#### `app/graph/workflow.py`
- `sqlite3` / `SqliteSaver` import 제거
- `AsyncPostgresSaver` (`langgraph.checkpoint.postgres.aio`) 로 교체
- `create_workflow(checkpointer)` — checkpointer를 외부에서 주입받는 구조로 변경
- `set_graph()` / `get_graph()` 싱글톤 분리 — lifespan 훅에서 초기화 후 등록
- `_memory` 튜플 반환 제거

#### `app/db/session_store.py` (신규)
- `sessions_registry.json` 및 인메모리 dict(`_sessions_registry`) 완전 대체
- PostgreSQL `sessions` 테이블 DDL (`CREATE TABLE IF NOT EXISTS`)
- `user_id` 컬럼 추가 — 사용자별 세션 격리의 핵심
- `user_id` 인덱스 (`idx_sessions_user_id`) 추가
- `chat_history` JSONB 컬럼 — 채팅 기록 저장
- 제공 함수: `init_db()`, `create_session()`, `get_session()`, `list_sessions_by_user()`, `update_session()`
- `psycopg.AsyncConnection` 기반 완전 비동기 구현

#### `app/core/auth.py` (신규)
- Firebase ID Token 검증 미들웨어
- `get_current_user(authorization: str)` — FastAPI `Depends()` 형태로 사용
- 로컬: `FIREBASE_CREDENTIALS_PATH` 환경변수로 서비스 계정 JSON 지정
- Cloud Run: Application Default Credentials 자동 사용
- 오류 분기: 만료(401) / 무효(401) / 형식 불일치(401)

#### `app/main.py`
- `lifespan` 훅 전면 재작성:
  ```
  AsyncPostgresSaver.from_conn_string() (컨텍스트 매니저)
    → checkpointer.setup()        # langgraph_checkpoints 테이블 생성
    → init_db()                   # sessions 테이블 생성
    → set_graph(create_workflow(checkpointer))
  ```
- 앱 종료 시 checkpointer 연결 풀 자동 정리

#### `app/api/routers/chat.py`
- 제거: `REGISTRY_FILE`, `_registry_lock`, `_sessions_registry`, `load_registry()`, `save_registry()`
- 추가: `session_store` import, `get_current_user` import
- 모든 엔드포인트에 `user_id: str = Depends(get_current_user)` 추가
- `_require_ownership()` 헬퍼 — 세션 존재 여부(404) + 소유권(403) 단일 검증
- 동기 → 비동기 전환:
  - `graph.invoke()` → `await graph.ainvoke()`
  - `graph.get_state()` → `await graph.aget_state()`
  - `graph.update_state()` → `await graph.aupdate_state()`
- 세션 CRUD 모두 `db_create_session` / `db_get_session` / `db_update_session` / `list_sessions_by_user` 로 교체

#### `Dockerfile`
```dockerfile
# 변경 전
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# 변경 후
CMD ["sh", "-c", "gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker \
     --bind 0.0.0.0:${PORT:-8000} --timeout 300 --log-level info"]
```
- Cloud Run `PORT` 환경변수 대응
- gunicorn 2 workers + UvicornWorker (async 이벤트 루프 유지)
- `--timeout 300`: Gemini 호출 최대 응답 시간 대비

---

### 프론트엔드

#### `frontend/package.json`
- `"firebase": "^10.14.0"` 의존성 추가

#### `frontend/src/firebase.ts` (신규)
- Firebase 앱 초기화 (`VITE_FIREBASE_*` 환경변수 기반)
- `loginWithGoogle()` — Google 팝업 로그인
- `logout()` — 로그아웃
- `getIdToken()` — 현재 사용자의 ID Token 반환 (만료 시 자동 갱신)
- `onAuthStateChanged` 재내보내기

#### `frontend/src/api.ts`
- 모든 API 함수에 `authHeaders()` 적용
  - `Authorization: Bearer <Firebase ID Token>` 헤더 자동 포함
  - `getIdToken()`이 미로그인 시 예외 throw → 호출부에서 처리

#### `frontend/src/App.tsx`
- **인증 상태 관리**:
  - `user: User | null` — 현재 로그인된 Firebase 사용자
  - `authLoading: boolean` — Firebase auth 초기화 대기 상태
  - `onAuthStateChanged` 구독 (`useEffect`, cleanup 포함)
- **인증 게이트 (3단계 렌더링)**:
  1. `authLoading === true` → 로딩 화면
  2. `user === null` → 로그인 화면 (Google 로그인 버튼)
  3. `user !== null` → 기존 앱 화면
- **로그인 화면**: 중앙 카드, 앱 제목, Google 로그인 버튼 (SVG 아이콘 포함)
- **헤더**: 프로필 이미지 + 이름/이메일 + 로그아웃 버튼 추가
- `handleLogout()` — 로그아웃 후 상태 초기화 + 목록 화면으로 이동

#### `frontend/.env.example` (신규)
- Firebase 설정값 템플릿 (`VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`)

---

## ⬜ 미착수: GCP 인프라

아래 항목들은 [deploy_plan.md §4](deploy_plan.md#4-배포-절차)의 명령어를 따라 진행합니다.

- [ ] GCP 프로젝트 생성 및 필요 API 활성화
- [ ] Cloud SQL PostgreSQL 인스턴스 및 DB 생성
- [ ] Neo4j AuraDB 인스턴스 생성
- [ ] Firebase 프로젝트 생성 및 Google 로그인 활성화
- [ ] Secret Manager에 모든 민감 환경 변수 등록
- [ ] Artifact Registry 저장소 생성
- [ ] Cloud Run 서비스 배포
- [ ] Firebase Hosting 배포
- [ ] ETL 파이프라인 실행 (AuraDB에 법령 데이터 적재)

---

## ⬜ 미착수: 배포 후 검증

- [ ] Google 로그인 후 세션 생성 정상 작동
- [ ] 서로 다른 계정으로 로그인 시 세션 격리 확인 (타인 세션 403 응답)
- [ ] Cloud Run 로그에서 LangGraph 노드 실행 흐름 확인
- [ ] Cloud SQL `sessions` 테이블 데이터 적재 확인
- [ ] Neo4j AuraDB 연결 및 법령 검색 정상 작동 확인
- [ ] CORS 오류 없음 확인 (Firebase Hosting 도메인 → Cloud Run)

---

## 배포 전 로컬 테스트 절차

코드 수정이 완료됐으므로 GCP 인프라 구성 전 로컬에서 검증합니다.

### 1. PostgreSQL 로컬 실행

```bash
# docker-compose에 postgres 서비스 추가 또는 별도 실행
docker run -d \
  --name ordinance-postgres \
  -e POSTGRES_USER=app_user \
  -e POSTGRES_PASSWORD=localpass \
  -e POSTGRES_DB=ordinance_builder \
  -p 5432:5432 \
  postgres:17
```

### 2. 환경변수 설정

```bash
# .env
POSTGRES_URL=postgresql://app_user:localpass@localhost:5432/ordinance_builder
FIREBASE_CREDENTIALS_PATH=./firebase-service-account.json
GOOGLE_API_KEY=...
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
```

### 3. Firebase 서비스 계정 발급

Firebase 콘솔 → 프로젝트 설정 → 서비스 계정 → 새 비공개 키 생성 → `firebase-service-account.json`으로 저장

### 4. 백엔드 실행

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 5. 프론트엔드 설정 및 실행

```bash
cd frontend
cp .env.example .env.local
# .env.local에 Firebase 설정값 입력

npm install
npm run dev
```
