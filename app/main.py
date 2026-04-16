from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.chat import router as chat_router
from app.api.routers.debug import router as debug_router
from app.core.config import settings
from app.db.session_store import init_db
from app.graph.workflow import create_workflow, set_graph


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(debug_router)
