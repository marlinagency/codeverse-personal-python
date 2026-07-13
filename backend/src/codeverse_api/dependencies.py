"""Dependency-injection providers wiring codeverse_core/_sandbox into FastAPI."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from codeverse_api.config import Settings, get_settings
from codeverse_api.db.base import get_db
from codeverse_core.cvl.pipeline import CompilationPipeline
from codeverse_core.error_translation import ErrorTranslator
from codeverse_core.theme_mapping.generator import TaxonomyThemeDictionaryGenerator
from codeverse_core.theme_mapping.llm_provider import LLMProvider
from codeverse_core.theme_mapping.providers.anthropic import AnthropicProvider
from codeverse_core.theme_mapping.providers.fake import FakeProvider
from codeverse_core.theme_mapping.providers.fireworks import FireworksProvider
from codeverse_core.theme_mapping.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from codeverse_sandbox.docker_runner import DockerSandboxRunner


def build_llm_provider(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "fireworks":
        return FireworksProvider(api_key=settings.fireworks_api_key, model=settings.fireworks_model)
    if provider == "openai_compatible":
        return OpenAICompatibleProvider(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
    if provider == "anthropic":
        return AnthropicProvider(
            api_key=settings.anthropic_api_key, model=settings.anthropic_model
        )
    if provider == "fake":
        return FakeProvider()
    raise ValueError(
        f"unknown LLM_PROVIDER: {settings.llm_provider!r} "
        "(fireworks | openai_compatible | anthropic | fake)"
    )


def build_amd_provider(settings: Settings) -> OpenAICompatibleProvider:
    """Our own model, fine-tuned on an AMD Instinct GPU and served over a
    reverse tunnel. Reached only for curated theme chips; see themes router."""
    return OpenAICompatibleProvider(
        base_url=settings.amd_base_url,
        api_key="not-needed",
        model=settings.amd_model,
        timeout_seconds=settings.amd_timeout_seconds,
    )


def get_llm_provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return build_llm_provider(settings)


def get_theme_generator(
    provider: LLMProvider = Depends(get_llm_provider),
) -> TaxonomyThemeDictionaryGenerator:
    return TaxonomyThemeDictionaryGenerator(provider)  # type: ignore


def get_error_translator(
    provider: LLMProvider = Depends(get_llm_provider),
) -> ErrorTranslator:
    return ErrorTranslator(provider)


def get_compilation_pipeline(
    translator: ErrorTranslator = Depends(get_error_translator),
) -> CompilationPipeline:
    return CompilationPipeline(error_translator=translator)


@lru_cache
def _sandbox_singleton() -> DockerSandboxRunner | None:
    """Constructed lazily and cached; None if the Docker daemon is unreachable
    (e.g. Docker Desktop not installed) so routes can degrade with a clear
    503 instead of crashing app startup."""
    try:
        return DockerSandboxRunner()
    except Exception:  # noqa: BLE001 - docker.from_env raises broad errors
        return None


def get_sandbox_runner() -> DockerSandboxRunner | None:
    return _sandbox_singleton()


__all__ = [
    "get_db",
    "get_llm_provider",
    "get_theme_generator",
    "get_error_translator",
    "get_compilation_pipeline",
    "get_sandbox_runner",
    "build_llm_provider",
    "build_amd_provider",
]
