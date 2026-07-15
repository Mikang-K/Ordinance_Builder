"""Chat model factory supporting cloud and local OpenAI-compatible models."""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.model_profile import ModelSpec, model_spec_from_settings

_llm_cache: dict[str, BaseChatModel] = {}


def get_llm(
    provider: str | ModelSpec | None = None,
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """Return a cached model; provider-only calls remain backward compatible."""
    if isinstance(provider, ModelSpec):
        spec = provider
    else:
        configured = model_spec_from_settings(provider, settings)
        spec = ModelSpec(
            provider=configured.provider,
            model=model if model is not None else configured.model,
            base_url=base_url if base_url is not None else configured.base_url,
            api_key=api_key if api_key is not None else configured.api_key,
            timeout=timeout if timeout is not None else configured.timeout,
            temperature=temperature if temperature is not None else configured.temperature,
            max_tokens=max_tokens if max_tokens is not None else configured.max_tokens,
        )
    spec = spec.normalized()
    key = spec.fingerprint()

    if key not in _llm_cache:
        common = {"temperature": spec.temperature}
        if spec.timeout is not None:
            common["timeout"] = spec.timeout

        if spec.provider == "gemini":
            _llm_cache[key] = ChatGoogleGenerativeAI(
                model=spec.model,
                google_api_key=spec.api_key,
                max_output_tokens=spec.max_tokens,
                **common,
            )
        elif spec.provider in {"openai", "ollama", "openai_compatible"}:
            _llm_cache[key] = ChatOpenAI(
                model=spec.model,
                api_key=spec.api_key or "local-not-required",
                base_url=spec.base_url,
                max_tokens=spec.max_tokens,
                **common,
            )
        elif spec.provider == "anthropic":
            _llm_cache[key] = ChatAnthropic(
                model=spec.model,
                api_key=spec.api_key,
                max_tokens=spec.max_tokens,
                **common,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {spec.provider!r}")

    return _llm_cache[key]
