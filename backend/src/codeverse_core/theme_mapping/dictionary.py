"""ThemeDictionary: a user's persistent, personal syntax vocabulary."""

from __future__ import annotations

from dataclasses import dataclass, field

from codeverse_core.concepts import ConceptKind, UniversalConcept


@dataclass(frozen=True)
class ThemeDictionary:
    """Maps every UniversalConcept to one themed token.

    ``theme`` is free text — a single word ("Valorant") or a whole sentence
    describing the user's interest ("someone who loves black holes"). The
    LLM distills it; this object only stores the final, validated mapping.
    """

    theme: str
    mappings: dict[UniversalConcept, str]
    rationale: dict[UniversalConcept, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # reverse index: themed token -> concept (built once, used by lexer)
        object.__setattr__(
            self,
            "_reverse",
            {token: concept for concept, token in self.mappings.items()},
        )

    def resolve(self, token: str) -> UniversalConcept | None:
        """Themed token -> concept, or None if it is a plain identifier."""
        return self._reverse.get(token)  # type: ignore[attr-defined]

    def token_for(self, concept: UniversalConcept) -> str:
        return self.mappings[concept]

    def themed_keywords(self) -> dict[str, UniversalConcept]:
        """Only KEYWORD-kind entries (what syntax highlighting needs)."""
        return {
            token: concept
            for token, concept in self._reverse.items()  # type: ignore[attr-defined]
            if concept.kind is ConceptKind.KEYWORD
        }

    def to_json_mappings(self) -> dict[str, str]:
        """Serializable form keyed by stable concept keys (for DB storage)."""
        return {concept.key: token for concept, token in self.mappings.items()}

    @classmethod
    def from_json_mappings(
        cls,
        theme: str,
        mappings: dict[str, str],
        rationale: dict[str, str] | None = None,
    ) -> "ThemeDictionary":
        return cls(
            theme=theme,
            mappings={UniversalConcept.from_key(k): v for k, v in mappings.items()},
            rationale=(
                {UniversalConcept.from_key(k): v for k, v in (rationale or {}).items()}
            ),
        )


#: The identity dictionary: every concept maps to its canonical token.
#: Used by tests, by "professional mode", and as the resolver fallback.
CANONICAL_DICTIONARY = ThemeDictionary(
    theme="canonical",
    mappings={c: c.canonical for c in UniversalConcept},
)
