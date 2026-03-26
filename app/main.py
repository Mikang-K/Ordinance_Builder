from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.chat import router as chat_router
from app.api.routers.debug import router as debug_router
from app.core.config import settings
from app.graph.workflow import create_workflow


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the LangGraph workflow (LLM connection included) at startup."""
    create_workflow()
    yield
    # Shutdown cleanup goes here if needed


app = FastAPI(
    title="조례 빌더 AI",
    description="LangGraph 기반 지방 조례 초안 생성 서비스 (PoC)",
    version="0.1.0",
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
