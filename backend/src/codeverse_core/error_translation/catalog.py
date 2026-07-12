from __future__ import annotations

import re

from codeverse_core.concepts import UniversalConcept
from codeverse_core.theme_mapping.dictionary import ThemeDictionary


def infer_error_concepts(message: str, stage: str) -> tuple[UniversalConcept, ...]:
    """Best-effort concept tags for deterministic fallback translation."""

    folded = message.casefold()
    concepts: list[UniversalConcept] = []

    if "function" in folded:
        concepts.append(UniversalConcept.FUNCTION_DEF)
    if "return" in folded:
        concepts.append(UniversalConcept.RETURN)
    if "break" in folded:
        concepts.append(UniversalConcept.BREAK)
    if "continue" in folded:
        concepts.append(UniversalConcept.CONTINUE)
    if "loop" in folded:
        concepts.extend([UniversalConcept.FOR, UniversalConcept.WHILE])
    if "condition" in folded or re.search(r"\bif\b", folded):
        concepts.append(UniversalConcept.IF)
    if "except" in folded or re.search(r"\btry\b", folded):
        concepts.extend([UniversalConcept.TRY, UniversalConcept.EXCEPT])
    if "undefined" in folded or "not defined" in folded:
        concepts.append(UniversalConcept.IMPORT)
    if stage == "lex":
        concepts.extend([UniversalConcept.FUNCTION_DEF, UniversalConcept.IF])

    return tuple(dict.fromkeys(concepts))


def render_catalog_message(
    *,
    message: str,
    stage: str,
    dictionary: ThemeDictionary,
    concepts: tuple[UniversalConcept, ...] | None = None,
) -> str:
    """Deterministic theme-aware fallback when no LLM is available."""

    tags = concepts if concepts is not None else infer_error_concepts(message, stage)
    folded = message.casefold()

    if "cannot return a value outside a function" in folded:
        return (
            f"`{dictionary.token_for(UniversalConcept.RETURN)}` can only be used "
            f"inside a `{dictionary.token_for(UniversalConcept.FUNCTION_DEF)}` block."
        )

    if "'break' cannot be used outside a loop" in folded:
        return (
            f"`{dictionary.token_for(UniversalConcept.BREAK)}` can only be used "
            f"inside a `{dictionary.token_for(UniversalConcept.FOR)}` or "
            f"`{dictionary.token_for(UniversalConcept.WHILE)}` loop."
        )

    if "'continue' cannot be used outside a loop" in folded:
        return (
            f"`{dictionary.token_for(UniversalConcept.CONTINUE)}` can only be used "
            f"inside a `{dictionary.token_for(UniversalConcept.FOR)}` or "
            f"`{dictionary.token_for(UniversalConcept.WHILE)}` loop."
        )

    undefined = re.search(r"undefined name: '([^']+)'", message)
    if undefined:
        return (
            f"`{undefined.group(1)}` is not defined yet in this flow. Assign it a "
            "value first, import it, or check your themed vocabulary."
        )

    if tags:
        themed = ", ".join(f"`{dictionary.token_for(c)}`" for c in tags)
        return (
            f"Error around {themed} in the {dictionary.theme} vocabulary: {message}"
        )

    return f"Error in the {dictionary.theme} vocabulary: {message}"
