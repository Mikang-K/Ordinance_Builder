from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GOOGLE_API_KEY: str
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    MAX_INTERVIEW_TURNS: int = 5
    LOG_LEVEL: str = "INFO"
    DEBUG_MODE: bool = False
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"

    # 노드별 LLM provider 설정
    LLM_INTENT: Literal["gemini", "openai", "anthropic"] = "gemini"
    LLM_DRAFTING: Literal["gemini", "openai", "anthropic"] = "anthropic"
    LLM_REVIEWER: Literal["gemini", "openai", "anthropic"] = "anthropic"
    LLM_LEGAL: Literal["gemini", "openai", "anthropic"] = "openai"

    # Neo4j
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str

    # PostgreSQL — LangGraph 체크포인터 + 세션 레지스트리 공용
    # e.g. postgresql://user:pass@host:5432/dbname
    POSTGRES_URL: str

    # Firebase — 로컬 개발 시 서비스 계정 JSON 경로 지정 (Cloud Run은 ADC 자동 사용)
    FIREBASE_CREDENTIALS_PATH: str = ""

    # CORS — str 타입으로 유지해 pydantic-settings의 JSON 디코딩 우회
    # 쉼표 구분 문자열로 주입: "https://example.com,https://other.com"
    # 파싱은 main.py의 cors_origins() 헬퍼에서 처리
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
