from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings

_llm_instance: ChatGoogleGenerativeAI | None = None


def get_llm() -> ChatGoogleGenerativeAI:
    """Return a singleton Gemini 2.5 Pro LLM instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.2,
            max_output_tokens=8192,
        )
    return _llm_instance
