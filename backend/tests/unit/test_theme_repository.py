from __future__ import annotations

from types import SimpleNamespace

from codeverse_api.repositories.theme_repository import ThemeRepository
from codeverse_core.theme_mapping.dictionary import ThemeDictionary
from codeverse_core.theme_mapping.generator import TaxonomyThemeDictionary


def test_to_domain_detects_expanded_taxonomy_dictionary_without_private_enum_lookup():
    row = SimpleNamespace(
        theme_name="GTA San Andreas",
        mappings={"py_kw_def": "mission_plan", "py_fn_print": "radio_callout"},
        rationale={},
        llm_provider="fake",
        llm_model="fake",
    )

    dictionary = ThemeRepository.to_domain(row)

    assert isinstance(dictionary, TaxonomyThemeDictionary)
    assert dictionary.resolve("mission_plan") is not None


def test_to_domain_keeps_legacy_universal_dictionary():
    row = SimpleNamespace(
        theme_name="legacy",
        mappings={"function_def": "mission_plan", "print": "radio_callout"},
        rationale={},
        llm_provider="fake",
        llm_model="fake",
    )

    dictionary = ThemeRepository.to_domain(row)

    assert isinstance(dictionary, ThemeDictionary)
    assert dictionary.resolve("mission_plan") is not None
