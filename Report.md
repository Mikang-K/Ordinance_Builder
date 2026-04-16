# 보안 점검 보고서 — 조례 빌더 AI

> 점검 일자: 2026-04-16  
> 점검 범위: `d:/Project/Ordinance_Builder` 전체 (백엔드, 프론트엔드, 파이프라인, 인프라 설정)

---

## 요약

| 심각도 | 건수 |
|--------|------|
| **CRITICAL** | 2 |
| **HIGH**     | 3 |
| **MEDIUM**   | 5 |
| **LOW**      | 3 |
| **합계**     | **13** |

---

## CRITICAL

### C-1. docker-compose.yml에 자격증명 하드코딩

**파일**: [docker-compose.yml](docker-compose.yml)  
**해당 라인**: 6, 22, 44  

`docker-compose.yml`은 Git에 커밋되는 파일임에도 불구하고 실제 자격증명이 평문으로 포함되어 있습니다.

```yaml
# Line 6
POSTGRES_PASSWORD: localpass

# Line 22
NEO4J_AUTH: neo4j/<실제 비밀번호>

# Line 44
POSTGRES_URL: postgresql://app_user:localpass@postgres:5432/ordinance_builder
```

**위험**: 저장소를 조회할 수 있는 누구나 DB에 직접 접근 가능한 자격증명을 획득할 수 있습니다.

**권장 조치**:
1. `.env` 파일로 이동하고 환경 변수 참조 방식으로 변경
2. 현재 커밋된 비밀번호 즉시 교체

```yaml
# 수정 예시
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
POSTGRES_URL: postgresql://app_user:${POSTGRES_PASSWORD}@postgres:5432/ordinance_builder
```

---

### C-2. 인증 없는 디버그 엔드포인트 프로덕션 노출

**파일**: [app/api/routers/debug.py](app/api/routers/debug.py), [app/main.py](app/main.py:53)  
**해당 라인**: debug.py 전체, main.py:53  

디버그 라우터가 인증 없이 프로덕션 앱에 포함되어 있어 4개의 엔드포인트가 외부에 노출됩니다.

| 엔드포인트 | 노출 내용 |
|-----------|----------|
| `GET /api/v1/debug/db` | 법령 DB 전체 쿼리 결과 반환 |
| `GET /api/v1/debug/vector` | 벡터 인덱스 검색 + DB 임베딩 커버리지 통계 |
| `GET /api/v1/debug/legal-terms` | LegalTerm 노드 전체 조회 |
| `GET /api/v1/debug/db/stats` | Neo4j 노드·관계 전체 카운트 + `neo4j_uri` 반환 |

```python
# app/main.py:53 — 인증 없이 등록됨
app.include_router(debug_router)

# app/api/routers/debug.py:167 — 인증 미들웨어 없음
@router.get("/db/stats")
def debug_db_stats():
    # Depends(get_current_user) 없음
    return {"neo4j_uri": settings.NEO4J_URI, ...}
```

특히 `/debug/db/stats`는 응답에 `neo4j_uri` 값을 그대로 반환하여 내부 인프라 정보가 노출됩니다.

**권장 조치**:
- 프로덕션 배포 시 `debug_router` 등록 제거 (환경 변수 분기)
- 개발 환경에서도 최소한 `Depends(get_current_user)` 적용

```python
# app/main.py
if settings.DEBUG_MODE:
    app.include_router(debug_router)
```

---

## HIGH

### H-1. CORS allow_methods/allow_headers 와일드카드

**파일**: [app/main.py](app/main.py:45-50)  

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],   # DELETE, PUT, PATCH 등 모든 메서드 허용
    allow_headers=["*"],   # 임의 헤더 허용
)
```

실제로 사용되는 메서드는 `GET`, `POST`뿐입니다. 와일드카드는 공격 표면을 불필요하게 넓힙니다.

**권장 조치**:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,
)
```

---

### H-2. 예외 상세 정보 클라이언트 노출

**파일**: [app/api/routers/chat.py](app/api/routers/chat.py:166,236,296)  

워크플로우 오류 발생 시 내부 예외 메시지가 HTTP 500 응답 body에 그대로 포함됩니다.

```python
# chat.py:166, 236, 296 — 동일 패턴 반복
except Exception as exc:
    raise HTTPException(status_code=500, detail=f"워크플로우 오류: {exc}") from exc
```

`exc` 문자열에는 DB 연결 정보, 내부 경로, LLM API 응답 원문 등이 포함될 수 있습니다.

**권장 조치**:

```python
import logging
logger = logging.getLogger(__name__)

except Exception as exc:
    logger.exception("워크플로우 오류 (session=%s)", session_id)
    raise HTTPException(status_code=500, detail="내부 서버 오류가 발생했습니다.") from exc
```

---

### H-3. 의존성 버전 범위 지정 (공급망 위험)

**파일**: [requirements.txt](requirements.txt)  

모든 패키지가 `>=` 범위로만 지정되어 있습니다. 향후 빌드 시 예기치 않은 버전이 설치될 수 있으며, 악성 패키지 삽입 등 공급망 공격에 취약합니다.

```
langgraph>=0.2.0
langchain>=0.3.0
fastapi>=0.115.0
firebase-admin>=6.5.0
```

**권장 조치**: `pip freeze > requirements.lock` 또는 `pip-compile`로 정확한 버전을 고정하고, `requirements.txt`에서 참조합니다.

---

## MEDIUM

### M-1. 요청 속도 제한(Rate Limiting) 미적용

**파일**: [app/main.py](app/main.py), [app/api/routers/chat.py](app/api/routers/chat.py)  

모든 엔드포인트에 속도 제한이 없습니다. Gemini API는 호출당 비용이 발생하므로, 악의적인 사용자가 세션을 반복 생성하여 API 비용을 과다 소모시킬 수 있습니다.

**권장 조치**: `slowapi` 라이브러리 또는 리버스 프록시(nginx, Cloud Armor) 수준에서 제한 적용

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/session")
@limiter.limit("10/minute")
async def create_session(...):
    ...
```

---

### M-2. 보안 응답 헤더 미설정

**파일**: [app/main.py](app/main.py)  

다음 보안 헤더가 설정되지 않았습니다.

| 헤더 | 목적 |
|------|------|
| `X-Content-Type-Options: nosniff` | MIME 스니핑 방지 |
| `X-Frame-Options: DENY` | 클릭재킹 방지 |
| `Strict-Transport-Security` | HTTPS 강제 (프로덕션) |
| `Content-Security-Policy` | XSS 방어 |

**권장 조치**:

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

---

### M-3. session_id 형식 검증 미적용

**파일**: [app/api/routers/chat.py](app/api/routers/chat.py:107,207)  

`session_id`를 경로 파라미터로 받을 때 UUID 형식 검증이 없습니다. 소유권 체크(`_require_ownership`)가 있어 직접적인 IDOR는 방어되지만, 비정상 입력이 DB까지 그대로 전달됩니다.

```python
# 현재
@router.get("/session/{session_id}", ...)
async def get_session_state(session_id: str, ...):
    entry = await db_get_session(session_id)  # 형식 검증 없음
```

**권장 조치**: `uuid.UUID` 타입 힌트로 FastAPI의 자동 검증 활용

```python
import uuid
from fastapi import Path

async def get_session_state(
    session_id: uuid.UUID = Path(...),
    ...
):
    entry = await db_get_session(str(session_id))
```

---

### M-4. 채팅 기록 및 초안 평문 저장

**파일**: [app/db/session_store.py](app/db/session_store.py)  

조례 초안 전문과 채팅 기록이 PostgreSQL에 평문(JSONB)으로 저장됩니다. 조례 초안에는 지역, 사업 계획, 예산 등 민감한 행정 정보가 포함될 수 있습니다.

**권장 조치**: 최소한 DB 수준 암호화(PostgreSQL `pgcrypto`) 또는 애플리케이션 수준 암호화 적용 검토

---

### M-5. 인증 실패 로그 불충분

**파일**: [app/core/auth.py](app/core/auth.py)  

Firebase 토큰 검증 실패 시 예외 객체 문자열만 기록되어, 보안 감사나 침해 탐지에 활용하기 어렵습니다.

```python
except Exception as exc:
    logger.warning("Firebase 토큰 검증 실패: %s", exc)
```

**권장 조치**: 실패 IP, User-Agent, 토큰 앞 8자(식별용), 타임스탬프를 구조화된 로그로 기록

---

## LOW

### L-1. 요청 크기 제한 미설정

**파일**: [app/main.py](app/main.py)  

FastAPI/Uvicorn의 기본 요청 크기 제한이 명시적으로 설정되지 않았습니다. `/session/{id}/chat` 엔드포인트의 `draft_text` 필드에 수 MB의 데이터를 전송하는 공격이 가능합니다.

**권장 조치**: Uvicorn 실행 옵션 또는 미들웨어로 제한 설정

```python
# uvicorn 옵션
uvicorn app.main:app --limit-max-requests 1000

# 또는 Pydantic 스키마에서 max_length 지정
draft_text: str | None = Field(None, max_length=100_000)
```

---

### L-2. 기본 로그 레벨 INFO (프로덕션 정보 노출)

**파일**: [app/core/config.py](app/core/config.py:7)  

`LOG_LEVEL` 기본값이 `INFO`로 설정되어 있습니다. LangChain/LangGraph는 INFO 레벨에서 LLM 입출력 일부를 로그에 남길 수 있으며, 이는 사용자 입력이나 초안 내용 노출로 이어질 수 있습니다.

**권장 조치**: 프로덕션 환경에서는 `LOG_LEVEL=WARNING`으로 설정하고, 감사 목적 로그는 별도 structured logger로 분리

---

### L-3. POSTGRES_URL에 평문 비밀번호 포함

**파일**: [app/core/config.py](app/core/config.py:16-17), [docker-compose.yml](docker-compose.yml:44)  

연결 문자열(DSN) 형식으로 비밀번호가 포함되어, 환경 변수 덤프·로그 출력 시 노출될 위험이 있습니다.

**권장 조치**: `DATABASE_URL` 대신 호스트·포트·사용자·비밀번호를 분리된 환경 변수로 관리하거나, 연결 시 `asyncpg`의 `password` 파라미터로 분리 전달

---

## 잘 구현된 항목 (긍정 사항)

| 항목 | 파일 | 설명 |
|------|------|------|
| `.env` gitignore 처리 | [.gitignore](.gitignore:2) | `.env` 파일이 버전 관리에서 제외됨 |
| `firebase-service-account.json` gitignore 처리 | [.gitignore](.gitignore:53) | 서비스 계정 키 파일 추적 제외 |
| 채팅 API 인증 적용 | [app/api/routers/chat.py](app/api/routers/chat.py:93,110,140) | 모든 비즈니스 엔드포인트에 `Depends(get_current_user)` 적용 |
| 세션 소유권 검증 | [app/api/routers/chat.py](app/api/routers/chat.py:46-52) | `_require_ownership`으로 타 사용자 세션 접근 차단 |
| Neo4j 파라미터화 쿼리 | [app/db/neo4j_db.py](app/db/neo4j_db.py) | Cypher Injection 방어 |
| 환경 변수 기반 설정 | [app/core/config.py](app/core/config.py) | `pydantic-settings`로 타입 안전한 설정 관리 |
| UUID 세션 ID | [app/api/routers/chat.py](app/api/routers/chat.py:149) | 예측 불가능한 세션 식별자 사용 |

---

## 우선 조치 권고

| 순위 | 항목 | 작업 |
|------|------|------|
| 1 | **C-1** | `docker-compose.yml`의 하드코딩 자격증명 → 환경 변수 참조로 교체 + 기존 비밀번호 교체 |
| 2 | **C-2** | `debug_router` 프로덕션 등록 제거 또는 환경 변수 조건부 적용 |
| 3 | **H-1** | CORS `allow_methods`, `allow_headers` 최소 권한으로 변경 |
| 4 | **H-2** | 예외 메시지 클라이언트 응답에서 제거, 서버 측 로그로만 기록 |
| 5 | **M-1** | 핵심 엔드포인트에 Rate Limiting 적용 |
| 6 | **M-2** | 보안 응답 헤더 미들웨어 추가 |
| 7 | **H-3** | `pip freeze`로 의존성 버전 고정 |
