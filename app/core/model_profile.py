"""Model configuration shared by cloud and local chat-model providers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Any


_DEFAULT_MODELS = {
    "gemini": "gemini-2.5-pro",
    "openai": "gpt-4o",
    "anthropic": "claude-opus-4-7",
}


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Complete, immutable description of a chat-model connection."""

    provider: str = "gemini"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    timeout: float | None = None
    temperature: float = 0.2
    max_tokens: int = 8192

    def normalized(self) -> "ModelSpec":
        provider = self.provider.strip().lower().replace("-", "_")
        base_url = self.base_url.rstrip("/") if self.base_url else None
        if provider == "ollama" and not base_url:
            base_url = "http://localhost:11434/v1"
        elif provider == "ollama" and not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        model = self.model or _DEFAULT_MODELS.get(provider)
        if not model:
            raise ValueError(f"LLM model must be configured for provider {provider!r}")
        if provider in {"ollama", "openai_compatible"} and not base_url:
            raise ValueError(f"LLM base_url must be configured for provider {provider!r}")
        return replace(self, provider=provider, model=model, base_url=base_url)

    def fingerprint(self) -> str:
        """Return a secret-safe cache key covering every effective option."""
        spec = self.normalized()
        secret_hash = sha256((spec.api_key or "").encode()).hexdigest()
        values = (
            spec.provider, spec.model, spec.base_url, secret_hash, spec.timeout,
            spec.temperature, spec.max_tokens,
        )
        return sha256(repr(values).encode()).hexdigest()


def model_spec_from_settings(provider: str | None, settings: Any) -> ModelSpec:
    """Resolve a provider profile while tolerating older Settings objects."""
    name = (provider or "gemini").strip().lower().replace("-", "_")
    prefix = name.upper()

    def setting(*names: str, default: Any = None) -> Any:
        for key in names:
            value = getattr(settings, key, None)
            if value is not None and value != "":
                return value
        return default

    api_key_names = {
        "gemini": ("GOOGLE_API_KEY",),
        "openai": ("OPENAI_API_KEY",),
        "anthropic": ("ANTHROPIC_API_KEY",),
        "ollama": ("OLLAMA_API_KEY",),
        "openai_compatible": ("OPENAI_COMPATIBLE_API_KEY",),
    }
    return ModelSpec(
        provider=name,
        model=setting(f"{prefix}_MODEL", "LLM_MODEL"),
        base_url=setting(f"LLM_{prefix}_BASE_URL", f"{prefix}_BASE_URL", "LLM_BASE_URL"),
        api_key=setting(
            *(tuple(f"LLM_{key}" for key in api_key_names.get(name, (f"{prefix}_API_KEY",)))
              + api_key_names.get(name, (f"{prefix}_API_KEY",)))
        ),
        timeout=setting(f"{prefix}_TIMEOUT", "LLM_TIMEOUT_SECONDS", "LLM_REQUEST_TIMEOUT"),
        temperature=float(setting(f"{prefix}_TEMPERATURE", "LLM_TEMPERATURE", default=0.2)),
        max_tokens=int(setting(f"{prefix}_MAX_TOKENS", "LLM_MAX_TOKENS", default=8192)),
    ).normalized()
