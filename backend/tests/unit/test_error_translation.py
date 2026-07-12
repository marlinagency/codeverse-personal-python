from __future__ import annotations

import pytest

from codeverse_core.concepts import UniversalConcept
from codeverse_core.cvl.pipeline import CompilationError, CompilationPipeline
from codeverse_core.error_translation import ErrorContext, ErrorTranslator
from codeverse_core.theme_mapping.llm_provider import (
    LLMProvider,
    ThemeMappingRequest,
    ThemeMappingResponse,
    error_mapping_json,
)


def test_catalog_translates_return_outside_function(space_dictionary):
    translation = ErrorTranslator().translate(
        ErrorContext(
            message="cannot return a value outside a function",
            line=5,
            col=1,
            stage="semantic",
        ),
        space_dictionary,
    )

    assert translation.provider_name == "catalog"
    assert "`emit`" in translation.themed_message
    assert "`singularity`" in translation.themed_message
    assert translation.concepts == (
        UniversalConcept.FUNCTION_DEF,
        UniversalConcept.RETURN,
    )


def test_provider_translation_is_used_when_available(space_dictionary):
    provider = _StaticProvider("themed and short error message")

    translation = ErrorTranslator(provider).translate(
        ErrorContext(
            message="'break' cannot be used outside a loop",
            line=3,
            col=1,
            stage="semantic",
        ),
        space_dictionary,
    )

    assert translation.provider_name == "static"
    assert translation.themed_message == "themed and short error message"


def test_overlong_provider_translation_falls_back_to_catalog(space_dictionary):
    provider = _StaticProvider("x" * 1000)

    translation = ErrorTranslator(provider, max_provider_message_chars=50).translate(
        ErrorContext(
            message="'continue' cannot be used outside a loop",
            line=3,
            col=1,
            stage="semantic",
        ),
        space_dictionary,
    )

    assert translation.provider_name == "catalog"
    assert "`slingshot`" in translation.themed_message


def test_pipeline_attaches_themed_diagnostic(space_dictionary):
    source = """@theme: uzay
@language: python
@version: 1
---
emit 1
"""

    with pytest.raises(CompilationError) as raised:
        CompilationPipeline(error_translator=ErrorTranslator()).compile(
            source,
            space_dictionary,
        )

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.stage == "semantic"
    assert diagnostic.message == "cannot return a value outside a function"
    assert diagnostic.themed_message is not None
    assert "`emit`" in diagnostic.themed_message
    assert diagnostic.translation_provider == "catalog"


def test_error_mapping_json_accepts_both_key_types():
    # legacy UniversalConcept keys (31-concept ThemeDictionary)
    enum_keyed = error_mapping_json({UniversalConcept.IF: "clutch_check"})
    assert '"if": "clutch_check"' in enum_keyed
    # taxonomy string keys (concept_id) — the flavor the API actually uses
    str_keyed = error_mapping_json({"py_kw_if": "clutch_check"})
    assert '"py_kw_if": "clutch_check"' in str_keyed


def test_provider_exception_degrades_to_catalog(space_dictionary):
    """A provider that raises anything (not just LLMProviderError) must fall
    back to the deterministic catalog instead of breaking compilation."""

    class _BoomProvider(_StaticProvider):
        def translate_error_message(self, canonical_message, theme, mappings):
            raise AttributeError("simulated provider bug")

    translation = ErrorTranslator(_BoomProvider("unused")).translate(
        ErrorContext(
            message="'break' cannot be used outside a loop",
            line=3,
            col=1,
            stage="semantic",
        ),
        space_dictionary,
    )

    assert translation.provider_name == "catalog"
    assert translation.themed_message  # catalog produced something usable


class _StaticProvider(LLMProvider):
    def __init__(self, message: str) -> None:
        self._message = message

    @property
    def provider_name(self) -> str:
        return "static"

    def generate_theme_mapping(self, request: ThemeMappingRequest) -> ThemeMappingResponse:
        raise AssertionError("not used by error translation tests")

    def translate_error_message(
        self,
        canonical_message: str,
        theme: str,
        mappings: dict[UniversalConcept, str],
    ) -> str:
        return self._message
