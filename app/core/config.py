from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GOOGLE_API_KEY: str
    MAX_INTERVIEW_TURNS: int = 5
    LOG_LEVEL: str = "INFO"
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"

    # Neo4j
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str

    # PostgreSQL — LangGraph 체크포인터 + 세션 레지스트리 공용
    # e.g. postgresql://user:pass@host:5432/dbname
    POSTGRES_URL: str

    # Firebase — 로컬 개발 시 서비스 계정 JSON 경로 지정 (Cloud Run은 ADC 자동 사용)
    FIREBASE_CREDENTIALS_PATH: str = ""

    # CORS — comma-separated origins, or JSON array string
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Docker (nginx)
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
