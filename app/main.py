import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routers.chat import router as chat_router
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging_config import setup_logging
from app.db.session_store import init_db
from app.graph.workflow import create_workflow, set_graph

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """모든 요청/응답에 대해 메서드, 경로, 상태코드, 소요 시간을 기록합니다."""

    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        logger.info("→ %s %s", request.method, request.url.path)
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "← %s %s [%d] %.0fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """X-Content-Type-Options, X-Frame-Options, X-XSS-Protection 헤더를 모든 응답에 추가합니다."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    앱 시작 시:
      1. AsyncPostgresSaver 초기화 및 LangGraph 체크포인트 테이블 생성
      2. sessions 테이블 초기화
      3. LangGraph 워크플로우 컴파일 및 싱글톤 등록

    앱 종료 시:
      - AsyncPostgresSaver 연결 풀 정리 (context manager 자동 처리)
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncPostgresSaver.from_conn_string(settings.POSTGRES_URL) as checkpointer:
        try:
            await checkpointer.setup()      # langgraph_checkpoints 테이블 생성
        except Exception:
            # 다른 워커가 이미 setup을 완료한 경우 UniqueViolation 등이 발생할 수 있음 — 무시
            pass
        await init_db()                     # sessions 테이블 생성
        set_graph(create_workflow(checkpointer))
        yield
    # context manager 종료 시 checkpointer 연결 풀 자동 정리


app = FastAPI(
    title="조례 빌더 AI",
    description="LangGraph 기반 지방 조례 초안 생성 서비스",
    version="0.2.0",
    lifespan=lifespan,
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Request/response logging
app.add_middleware(RequestLoggingMiddleware)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# CORS — 실제 사용하는 메서드/헤더만 허용
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(chat_router)

# 디버그 라우터: DEBUG_MODE=true 일 때만 등록 (프로덕션 비노출)
if settings.DEBUG_MODE:
    from app.api.routers.debug import router as debug_router
    app.include_router(debug_router)
