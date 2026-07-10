from __future__ import annotations

from dataclasses import dataclass, field

from codeverse_core.concepts import UniversalConcept
from codeverse_core.error_translation.catalog import infer_error_concepts, render_catalog_message
from codeverse_core.theme_mapping.dictionary import ThemeDictionary
from codeverse_core.theme_mapping.llm_provider import LLMProvider


@dataclass(frozen=True)
class ErrorContext:
    message: str
    line: int
    col: int
    stage: str
    severity: str = "error"


@dataclass(frozen=True)
class ErrorTranslation:
    canonical_message: str
    themed_message: str
    line: int
    col: int
    stage: str
    severity: str
    concepts: tuple[UniversalConcept, ...] = field(default_factory=tuple)
    provider_name: str = "catalog"


class ErrorTranslator:
    """Translate technical diagnostics into the active theme vocabulary.

    The catalog fallback is deterministic and always available. If an LLM
    provider is supplied, its translation is used only when it returns a short,
    non-empty message; provider failures fall back to the catalog.
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        *,
        max_provider_message_chars: int = 500,
    ) -> None:
        self._provider = provider
        self._max_provider_message_chars = max_provider_message_chars

    def translate(
        self,
        context: ErrorContext,
        dictionary: ThemeDictionary,
    ) -> ErrorTranslation:
        concepts = infer_error_concepts(context.message, context.stage)
        fallback = render_catalog_message(
            message=context.message,
            stage=context.stage,
            dictionary=dictionary,
            concepts=concepts,
        )

        provider_name = "catalog"
        themed_message = fallback
        if self._provider is not None:
            try:
                candidate = self._provider.translate_error_message(
                    context.message,
                    dictionary.theme,
                    dictionary.mappings,
                ).strip()
            except Exception:  # noqa: BLE001 - error translation is a best-effort
                # enhancement over the deterministic catalog; ANY provider
                # failure (transport, bad shape, unexpected key type) must
                # degrade to the catalog, never break compilation.
                candidate = ""

            if candidate and len(candidate) <= self._max_provider_message_chars:
                themed_message = candidate
                provider_name = self._provider.provider_name

        return ErrorTranslation(
            canonical_message=context.message,
            themed_message=themed_message,
            line=context.line,
            col=context.col,
            stage=context.stage,
            severity=context.severity,
            concepts=concepts,
            provider_name=provider_name,
        )
