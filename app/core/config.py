from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GOOGLE_API_KEY: str
    MAX_INTERVIEW_TURNS: int = 5
    LOG_LEVEL: str = "INFO"
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"

    # Neo4j — set these to switch from MockGraphDB to Neo4jGraphDB
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str

    # SQLite checkpointer — session state is persisted to this file
    CHECKPOINT_DB_PATH: str = "sessions.db"

    # CORS — comma-separated origins, or JSON array string
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Docker (nginx)
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
