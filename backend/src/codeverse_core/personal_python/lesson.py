"""Build a small, runnable Personal Python lesson from a theme dictionary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from codeverse_core.concepts import UniversalConcept


@dataclass(frozen=True)
class PersonalPythonLesson:
    theme_name: str
    source_content: str
    used_concepts: dict[str, str]
    focus: tuple[str, ...]


_UNIVERSAL_FALLBACKS: dict[str, UniversalConcept] = {
    "py_kw_def": UniversalConcept.FUNCTION_DEF,
    "py_kw_return": UniversalConcept.RETURN,
    "py_kw_if": UniversalConcept.IF,
    "py_kw_elif": UniversalConcept.ELIF,
    "py_kw_else": UniversalConcept.ELSE,
    "py_kw_for": UniversalConcept.FOR,
    "py_kw_in": UniversalConcept.IN,
    "py_fn_print": UniversalConcept.PRINT,
    "py_fn_range": UniversalConcept.RANGE,
    "py_fn_len": UniversalConcept.LEN,
    "py_list_append": UniversalConcept.LIST_APPEND,
    "py_dict_get": UniversalConcept.DICT_GET,
}

_CANONICAL_FALLBACKS: dict[str, str] = {
    "py_kw_def": "func",
    "py_kw_return": "return",
    "py_kw_if": "if",
    "py_kw_elif": "elif",
    "py_kw_else": "else",
    "py_kw_for": "for",
    "py_kw_in": "in",
    "py_fn_print": "print",
    "py_fn_range": "range",
    "py_fn_list": "list",
    "py_fn_dict": "dict",
    "py_fn_len": "len",
    "py_list_append": "append",
    "py_dict_get": "get",
}

_FOCUS = (
    "function",
    "branching",
    "loops",
    "collections",
    "method calls",
    "real Python output",
)


def build_personal_python_lesson(dictionary: Any) -> PersonalPythonLesson:
    """Return a deterministic lesson source that should compile for any theme.

    The lesson intentionally keeps user-defined names under the ``cv_`` prefix.
    That prevents accidental shadowing when a theme maps concepts to attractive
    names such as ``spellbook`` for ``dict`` or ``radio_callout`` for ``print``.
    """

    tokens = {
        concept_id: _token(dictionary, concept_id)
        for concept_id in _CANONICAL_FALLBACKS
    }
    theme_name = _header_value(str(getattr(dictionary, "theme", "Personal Python")))

    source = f"""@theme: {theme_name}
@language: python
@version: 1
---
# Personal Python starter lesson
{tokens["py_kw_def"]} cv_build_scores(cv_levels):
    cv_rules = {tokens["py_fn_dict"]}({{"base": 100, "bonus": 50}})
    cv_scores = {tokens["py_fn_list"]}([])
    {tokens["py_kw_for"]} cv_level {tokens["py_kw_in"]} cv_levels:
        {tokens["py_kw_if"]} cv_level <= 1:
            cv_scores.{tokens["py_list_append"]}(cv_rules.{tokens["py_dict_get"]}("base"))
        {tokens["py_kw_elif"]} cv_level == 2:
            cv_scores.{tokens["py_list_append"]}(cv_rules.{tokens["py_dict_get"]}("base") + cv_rules.{tokens["py_dict_get"]}("bonus"))
        {tokens["py_kw_else"]}:
            cv_scores.{tokens["py_list_append"]}(cv_level * cv_rules.{tokens["py_dict_get"]}("bonus"))
    {tokens["py_kw_return"]} cv_scores

cv_scores = cv_build_scores({tokens["py_fn_range"]}(1, 5))
{tokens["py_kw_for"]} cv_score {tokens["py_kw_in"]} cv_scores:
    {tokens["py_fn_print"]}(cv_score)
{tokens["py_fn_print"]}({tokens["py_fn_len"]}(cv_scores))
"""

    return PersonalPythonLesson(
        theme_name=theme_name,
        source_content=source,
        used_concepts=tokens,
        focus=_FOCUS,
    )


def _token(dictionary: Any, concept_id: str) -> str:
    mappings = getattr(dictionary, "mappings", {})
    if concept_id in mappings and str(mappings[concept_id]).strip():
        return str(mappings[concept_id]).strip()

    universal = _UNIVERSAL_FALLBACKS.get(concept_id)
    if universal is not None:
        try:
            return str(dictionary.token_for(universal)).strip()
        except Exception:  # noqa: BLE001 - accepts both dictionary classes.
            pass

    return _CANONICAL_FALLBACKS[concept_id]


def _header_value(value: str) -> str:
    compact = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    return compact[:120] or "Personal Python"
