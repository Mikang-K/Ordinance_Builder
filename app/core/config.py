from typing import Literal

from pydantic_settings import BaseSettings


LLMProvider = Literal["gemini", "openai", "anthropic", "ollama", "openai_compatible"]


class Settings(BaseSettings):
    # Optional so a fully local LLM configuration does not require cloud credentials.
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    MAX_INTERVIEW_TURNS: int = 5
    LOG_LEVEL: str = "INFO"
    DEBUG_MODE: bool = False
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"

    # 노드별 LLM provider 설정
    LLM_INTENT: LLMProvider = "gemini"
    LLM_DRAFTING: LLMProvider = "gemini"
    LLM_REVIEWER: LLMProvider = "gemini"
    LLM_LEGAL: LLMProvider = "gemini"

    LLM_INTENT_MODEL: str = ""
    LLM_DRAFTING_MODEL: str = ""
    LLM_REVIEWER_MODEL: str = ""
    LLM_LEGAL_MODEL: str = ""
    LLM_OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_OPENAI_COMPATIBLE_BASE_URL: str = "http://localhost:11434/v1"
    LLM_OPENAI_COMPATIBLE_API_KEY: str = ""
    LLM_TIMEOUT_SECONDS: float = 120.0
    LLM_FALLBACK_ENABLED: bool = False

    def llm_config(self, role: str) -> dict[str, str | float | bool | None]:
        """Return the non-secret model configuration for a workflow role."""
        normalized = role.upper()
        provider = getattr(self, f"LLM_{normalized}")
        model = getattr(self, f"LLM_{normalized}_MODEL") or {
            "gemini": "gemini-2.5-pro",
            "openai": "gpt-4o",
            "anthropic": "claude-opus-4-7",
            "ollama": "qwen2.5:14b",
            "openai_compatible": "local-model",
        }[provider]
        base_url = None
        if provider == "ollama":
            base_url = self.LLM_OLLAMA_BASE_URL
        elif provider == "openai_compatible":
            base_url = self.LLM_OPENAI_COMPATIBLE_BASE_URL
        return {
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "timeout": self.LLM_TIMEOUT_SECONDS,
            "fallback": self.LLM_FALLBACK_ENABLED,
        }

    def llm_available(self, role: str) -> bool:
        config = self.llm_config(role)
        provider = config["provider"]
        if not config["model"]:
            return False
        if provider == "gemini":
            return bool(self.GOOGLE_API_KEY)
        if provider == "openai":
            return bool(self.OPENAI_API_KEY)
        if provider == "anthropic":
            return bool(self.ANTHROPIC_API_KEY)
        return bool(config["base_url"])

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
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,https://ordinance-builder-b9f6c.web.app"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
