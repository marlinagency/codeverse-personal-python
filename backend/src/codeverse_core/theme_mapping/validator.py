"""Validation rules for LLM-generated theme mappings.

The theme *input* is unconstrained free text; only the generated *output*
tokens are constrained, because they must be lexable, unambiguous DSL
keywords.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from codeverse_core.concepts import DSL_TYPE_NAMES, RESERVED_TOKENS, UniversalConcept

#: Tokens must be single identifiers. Unicode letters are allowed (themed
#: tokens may be Turkish, Japanese, ...) — the lexer treats any \w run as an
#: identifier character.
_IDENTIFIER_RE = re.compile(r"^[^\W\d]\w*$", re.UNICODE)


class ThemeDictionaryValidationError(Exception):
    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


def validate_mappings(
    mappings: dict[UniversalConcept, str],
    required: tuple[UniversalConcept, ...] = tuple(UniversalConcept),
) -> list[str]:
    """Return a list of problems (empty list == valid)."""
    problems: list[str] = []

    missing = [c.key for c in required if c not in mappings or not mappings.get(c, "").strip()]
    if missing:
        problems.append(f"missing mappings for concepts: {', '.join(missing)}")

    seen: dict[str, UniversalConcept] = {}
    for concept, token in mappings.items():
        token = token.strip()
        folded = _casefold(token)

        if not _IDENTIFIER_RE.match(token):
            problems.append(
                f"{concept.key}: token {token!r} is not a valid identifier "
                "(letters/digits/underscore, must not start with a digit, no spaces)"
            )
            continue

        if folded in _RESERVED_FOLDED:
            problems.append(
                f"{concept.key}: token {token!r} collides with a reserved keyword "
                "of a supported target language"
            )

        if folded in _TYPE_NAMES_FOLDED:
            problems.append(
                f"{concept.key}: token {token!r} collides with a DSL type name"
            )

        if folded in seen:
            problems.append(
                f"duplicate token {token!r} used for both "
                f"{seen[folded].key} and {concept.key}"
            )
        else:
            seen[folded] = concept

    return problems


def ensure_valid(
    mappings: dict[UniversalConcept, str],
    required: tuple[UniversalConcept, ...] = tuple(UniversalConcept),
) -> None:
    problems = validate_mappings(mappings, required)
    if problems:
        raise ThemeDictionaryValidationError(problems)


def _casefold(token: str) -> str:
    return unicodedata.normalize("NFKC", token).casefold()


_RESERVED_FOLDED = frozenset(_casefold(t) for t in RESERVED_TOKENS)
_TYPE_NAMES_FOLDED = frozenset(_casefold(t) for t in DSL_TYPE_NAMES)


# --------------------------------------------------------------------------
# Taksonomi Planı Adım 10: same rules, at ~1000-concept scale.
#
# The 31-concept validator above keys mappings by ``UniversalConcept`` and
# requires every concept present in one shot — that model doesn't fit the
# taxonomy: ~980 concepts are mapped in ~40-item batches (Adım 9), so
# completeness can only be checked incrementally (this batch) or at the end
# (the full dictionary), never "in one dict like the 31-concept case."
# ``validate_taxonomy_batch`` is the shared, string-keyed rule set both the
# batch orchestrator (``generator.py``) and standalone tests call — no
# duplicated validation logic between the two scales.
# --------------------------------------------------------------------------


def validate_taxonomy_batch(
    batch_mappings: dict[str, str],
    *,
    used_tokens: dict[str, str] | None = None,
    reserved_names: set[str] | None = None,
) -> list[str]:
    """Validate one canonical_name -> token batch at taxonomy scale.

    - ``used_tokens``: folded-token -> canonical_name already claimed by
      EARLIER batches in this same dictionary (cross-batch dedup — the
      orchestrator accumulates this across calls).
    - ``reserved_names``: every canonical construct name across the whole
      taxonomy (e.g. the ~468 names ``upper``, ``left_join``, ...) — a
      themed token must never literally equal a real construct's own name,
      themed or not (a token IS the theming, so it can't just repeat the
      thing it's supposed to replace).

    Returns a list of problems (empty == valid). Does not check for missing
    entries — batches are partial by design; use
    ``validate_taxonomy_dictionary_complete`` for whole-dictionary
    completeness once every batch has run.
    """
    problems: list[str] = []
    used_tokens = used_tokens or {}
    reserved_names_folded = {_casefold(n) for n in (reserved_names or set())}
    local_seen: dict[str, str] = {}

    for name, raw_token in batch_mappings.items():
        token = raw_token.strip()
        folded = _casefold(token)

        if not token:
            problems.append(f"{name}: empty token")
            continue

        if not _IDENTIFIER_RE.match(token):
            problems.append(
                f"{name}: token {token!r} is not a valid identifier "
                "(letters/digits/underscore, must not start with a digit, no spaces)"
            )
            continue

        if folded in _RESERVED_FOLDED:
            problems.append(
                f"{name}: token {token!r} collides with a reserved keyword "
                "of a supported target language"
            )

        if folded in _TYPE_NAMES_FOLDED:
            problems.append(f"{name}: token {token!r} collides with a DSL type name")

        if folded in reserved_names_folded:
            problems.append(
                f"{name}: token {token!r} copies a real syntax name — themed "
                "tokens must differ from the construct's own name"
            )

        if folded in used_tokens and used_tokens[folded] != name:
            problems.append(
                f"{name}: token {token!r} duplicates a token already used for "
                f"{used_tokens[folded]!r} in an earlier batch"
            )

        if folded in local_seen:
            problems.append(
                f"duplicate token {token!r} used for both {local_seen[folded]!r} "
                f"and {name!r} in the same batch"
            )
        else:
            local_seen[folded] = name

    return problems


def validate_taxonomy_dictionary_complete(
    mappings: dict[str, str],
    required_concept_ids: Iterable[str],
) -> list[str]:
    """Whole-dictionary completeness check, run once after every batch of a
    taxonomy generation has completed (per-batch validation cannot check
    this, since each batch only ever sees its own slice)."""
    missing = [cid for cid in required_concept_ids if not mappings.get(cid, "").strip()]
    if not missing:
        return []
    shown = ", ".join(missing[:10])
    suffix = f" (+{len(missing) - 10} more)" if len(missing) > 10 else ""
    return [f"missing tokens for {len(missing)} concept_id(s): {shown}{suffix}"]


def validate_personal_python_dictionary_quality(
    mappings: dict[str, str],
    rationale: dict[str, str] | None = None,
    *,
    require_python_only: bool = True,
) -> list[str]:
    """Product-level quality gate for the Personal Python path.

    This is deliberately stricter than the syntax validator but still broad
    enough for long-tail Python methods. Core learning concepts must exist and
    the full dictionary must not leak raw prompt filler or generic LLM phrases.
    """
    problems: list[str] = []
    rationale = rationale or {}

    if require_python_only:
        sql_keys = sorted(key for key in mappings if key.startswith("sql_"))
        if sql_keys:
            shown = ", ".join(sql_keys[:5])
            problems.append(f"SQL concept_ids leaked into Personal Python output: {shown}")

    missing_core = [
        concept_id
        for concept_id in _PERSONAL_PYTHON_CORE_IDS
        if not mappings.get(concept_id, "").strip()
    ]
    if missing_core:
        problems.append(f"missing Personal Python core mappings: {', '.join(missing_core)}")

    for concept_id, raw_token in mappings.items():
        token = raw_token.strip()
        folded = _casefold(token)
        parts = [part for part in folded.split("_") if part]
        part_set = set(parts)

        if not token:
            problems.append(f"{concept_id}: empty token")
            continue
        compact_learning_token = concept_id in _PERSONAL_PYTHON_COMPACT_IDS
        python_token = concept_id.startswith("py_")
        max_length = 16 if compact_learning_token else (20 if python_token else 48)
        max_parts = 2 if python_token else 6
        if len(token) > max_length:
            problems.append(f"{concept_id}: token {token!r} is too long for learning UI")
        if len(parts) > max_parts:
            problems.append(f"{concept_id}: token {token!r} has too many snake_case parts")
        if part_set & _PERSONAL_BAD_TOKEN_PARTS:
            bad = ", ".join(sorted(part_set & _PERSONAL_BAD_TOKEN_PARTS))
            problems.append(f"{concept_id}: token {token!r} contains generic/raw part(s): {bad}")
        if folded in _PERSONAL_BAD_EXACT_TOKENS:
            problems.append(f"{concept_id}: token {token!r} is too close to a programming exercise phrase")
        if any(bad in folded for bad in _PERSONAL_BAD_TOKEN_SUBSTRINGS):
            problems.append(f"{concept_id}: token {token!r} contains generic technical wording")

    for concept_id, text in rationale.items():
        folded = _casefold(text)
        for phrase in _PERSONAL_BAD_RATIONALE_PHRASES:
            if phrase in folded:
                problems.append(
                    f"{concept_id}: rationale contains generic phrase {phrase!r}"
                )
                break

    return problems


_PERSONAL_PYTHON_CORE_IDS = (
    "py_kw_if",
    "py_kw_elif",
    "py_kw_else",
    "py_kw_for",
    "py_kw_in",
    "py_kw_def",
    "py_kw_return",
    "py_fn_print",
    "py_fn_range",
    "py_fn_list",
    "py_fn_dict",
    "py_kw_class",
    "py_kw_try",
    "py_kw_except",
)

_PERSONAL_PYTHON_COMPACT_IDS = frozenset(_PERSONAL_PYTHON_CORE_IDS) | frozenset(
    {
        "py_fn_str", "py_fn_int", "py_fn_float", "py_fn_round", "py_fn_abs", "py_fn_pow",
        "py_kw_while", "py_kw_break", "py_kw_continue",
        "py_kw_and", "py_kw_or", "py_kw_not", "py_kw_true", "py_kw_false", "py_kw_none",
        "py_fn_set", "py_fn_tuple", "py_set_add", "py_set_discard", "py_set_union",
        "py_kw_with", "py_kw_as", "py_kw_from", "py_fn_open", "py_file_read", "py_file_write",
        "py_kw_finally", "py_fn_len", "py_list_append", "py_dict_get",
    }
)

#: public alias: the generator aligns its in-flight token-length rule with
#: this gate so a token can never pass generation yet fail the final gate.
PERSONAL_PYTHON_COMPACT_IDS = _PERSONAL_PYTHON_COMPACT_IDS

_PERSONAL_BAD_TOKEN_PARTS = frozenset(
    {
        "theme",
        "generic",
        "specific",
        "code",
        "coding",
        "program",
        "variable",
        "helper",
        "config",
        "console",
        "debug",
        "terminal",
        "loop",
        "iteration",
        "print",
        "logs",
        "statement",
        "script",
        "syntax",
        "token",
        "python",
        "thing",
        "stuff",
        "evren",
        "evreni",
        "evreniyle",
        "olustur",
        "olusturmak",
        "seviyorum",
        "karisik",
    }
)

_PERSONAL_BAD_TOKEN_SUBSTRINGS = frozenset(
    {
        "python",
        "code",
        "coding",
        "token",
        "syntax",
        "generic",
        "statement",
        "variable",
        "helper",
        "config",
        "console",
        "debug",
        "terminal",
        "loop",
        "iteration",
    }
)

_PERSONAL_BAD_EXACT_TOKENS = frozenset({"run_test", "test_run"})

_PERSONAL_BAD_RATIONALE_PHRASES = frozenset(
    {
        "theme-specific",
        "feel connected",
        "concept idea",
        "specific name",
        "python function",
        "gives iter",
        "raw user",
    }
)
