from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from app.core.config import settings

# provider별 인스턴스 캐시
_llm_cache: dict[str, BaseChatModel] = {}


def get_llm(provider: str | None = None) -> BaseChatModel:
    """
    provider에 맞는 LLM 인스턴스를 반환한다. 인스턴스는 provider별로 캐싱된다.

    Args:
        provider: "gemini" | "openai" | "anthropic". None이면 "gemini"로 폴백.

    Returns:
        BaseChatModel 구현체 (세 provider 모두 .with_structured_output() 지원)
    """
    key = provider or "gemini"

    if key not in _llm_cache:
        if key == "gemini":
            _llm_cache[key] = ChatGoogleGenerativeAI(
                model="gemini-2.5-pro",
                google_api_key=settings.GOOGLE_API_KEY,
                temperature=0.2,
                max_output_tokens=8192,
            )
        elif key == "openai":
            _llm_cache[key] = ChatOpenAI(
                model="gpt-4o",
                api_key=settings.OPENAI_API_KEY,
                temperature=0.2,
                max_tokens=8192,
            )
        elif key == "anthropic":
            _llm_cache[key] = ChatAnthropic(
                model="claude-opus-4-6",
                api_key=settings.ANTHROPIC_API_KEY,
                temperature=0.2,
                max_tokens=8192,
            )
        else:
            raise ValueError(f"지원하지 않는 LLM provider: {key!r}")

    return _llm_cache[key]
