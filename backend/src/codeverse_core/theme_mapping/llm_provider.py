"""Provider-agnostic LLM abstraction.

Fireworks AI is the primary documented target (per product spec), but the
interface is deliberately provider-neutral so an OpenAI-compatible endpoint,
Anthropic, or a deterministic fake can back it interchangeably. Selection is
config-driven (``CODEVERSE_LLM_PROVIDER``).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from codeverse_core.concepts import UniversalConcept


def error_mapping_json(mappings: dict) -> str:
    """Serialize a concept->token mapping for the error-translation prompt.

    Accepts either legacy ``UniversalConcept`` keys (the 31-concept
    ``ThemeDictionary``) or plain ``concept_id`` string keys (the taxonomy
    ``TaxonomyThemeDictionary`` the API actually uses). Keeping this tolerant
    prevents a provider call from crashing the whole compile just because the
    dictionary flavor differs.
    """
    return json.dumps(
        {(key.key if hasattr(key, "key") else str(key)): token
         for key, token in mappings.items()},
        ensure_ascii=False,
    )


@dataclass(frozen=True)
class ThemeMappingRequest:
    #: Free text. Can be a name ("Valorant") or a full sentence describing
    #: the user's interest — the provider prompt distills it into motifs.
    theme: str
    concepts: tuple[UniversalConcept, ...] = tuple(UniversalConcept)
    #: Optional language hint for output token language (e.g. "tr", "en").
    output_language: str | None = None
    #: Previous mapping when regenerating, so the model keeps consistency.
    existing_mappings: dict[UniversalConcept, str] | None = None
    #: Validator feedback from a failed previous attempt (retry loop).
    correction_feedback: str | None = None


@dataclass(frozen=True)
class ThemeMappingResponse:
    #: keyed by stable concept key (UniversalConcept.key) — the generator
    #: resolves keys to enum members and rejects unknown ones.
    mappings: dict[str, str]
    rationale: dict[str, str] = field(default_factory=dict)
    raw_model_output: str = ""
    model: str = ""


class LLMProviderError(Exception):
    """Raised when a provider call fails or returns unusable output."""


class LLMProvider(ABC):
    """One theme-mapping generation + one error-translation capability."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    def generate_theme_mapping(self, request: ThemeMappingRequest) -> ThemeMappingResponse:
        """Produce a themed token for every requested concept.

        Raises LLMProviderError on transport failure or unparseable output.
        Output *content* validation (uniqueness, identifier shape, reserved
        collisions) is the validator's job, not the provider's.
        """

    @abstractmethod
    def translate_error_message(
        self,
        canonical_message: str,
        theme: str,
        mappings: dict[UniversalConcept, str],
    ) -> str:
        """Rephrase a canonical error message in the user's theme vocabulary."""
