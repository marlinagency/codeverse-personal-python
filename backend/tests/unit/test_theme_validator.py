from __future__ import annotations

import pytest

from codeverse_core.concepts import UniversalConcept
from codeverse_core.theme_mapping.dictionary import CANONICAL_DICTIONARY
from codeverse_core.theme_mapping.generator import ThemeDictionaryGenerator
from codeverse_core.theme_mapping.providers.fake import FakeProvider
from codeverse_core.theme_mapping.validator import (
    ThemeDictionaryValidationError,
    ensure_valid,
    validate_mappings,
)


def _full_valid_mappings() -> dict[UniversalConcept, str]:
    return {c: f"tok_{c.key}" for c in UniversalConcept}


def test_valid_mappings_pass():
    assert validate_mappings(_full_valid_mappings()) == []


def test_missing_concept_reported():
    mappings = _full_valid_mappings()
    del mappings[UniversalConcept.RETURN]
    problems = validate_mappings(mappings)
    assert any("return" in p for p in problems)


def test_duplicate_tokens_rejected():
    mappings = _full_valid_mappings()
    mappings[UniversalConcept.IF] = "supernova"
    mappings[UniversalConcept.ELSE] = "SUPERNOVA"  # case-insensitive duplicate
    problems = validate_mappings(mappings)
    assert any("duplicate" in p for p in problems)


def test_non_identifier_tokens_rejected():
    mappings = _full_valid_mappings()
    mappings[UniversalConcept.IF] = "iki kelime"
    mappings[UniversalConcept.FOR] = "3baslar"
    mappings[UniversalConcept.WHILE] = "nokta.li"
    problems = validate_mappings(mappings)
    assert len([p for p in problems if "identifier" in p]) == 3


def test_reserved_keyword_collision_rejected():
    mappings = _full_valid_mappings()
    mappings[UniversalConcept.IF] = "select"
    mappings[UniversalConcept.FOR] = "def"
    problems = validate_mappings(mappings)
    assert len([p for p in problems if "reserved" in p]) == 2


def test_unicode_tokens_accepted():
    mappings = _full_valid_mappings()
    mappings[UniversalConcept.IF] = "tetiklendiğinde"
    mappings[UniversalConcept.RETURN] = "geri_gönder"
    assert validate_mappings(mappings) == []


def test_ensure_valid_raises():
    mappings = _full_valid_mappings()
    mappings[UniversalConcept.IF] = "iki kelime"
    with pytest.raises(ThemeDictionaryValidationError):
        ensure_valid(mappings)


def test_canonical_dictionary_resolves():
    assert CANONICAL_DICTIONARY.resolve("func") is UniversalConcept.FUNCTION_DEF
    assert CANONICAL_DICTIONARY.resolve("nonexistent") is None


def test_generator_with_fake_provider_free_text_theme():
    """Free-text sentence themes must work end to end."""
    gen = ThemeDictionaryGenerator(FakeProvider())
    dictionary, raw = gen.generate("uzayda karadelikleri seven ve bilen biri")
    assert dictionary.theme.startswith("uzayda")
    assert len(dictionary.mappings) == len(list(UniversalConcept))
    assert raw  # audit trail present
    # deterministic: same theme -> same tokens
    dictionary2, _ = gen.generate("uzayda karadelikleri seven ve bilen biri")
    assert dictionary.mappings == dictionary2.mappings


def test_dictionary_json_roundtrip():
    gen = ThemeDictionaryGenerator(FakeProvider())
    dictionary, _ = gen.generate("Valorant")
    as_json = dictionary.to_json_mappings()
    restored = type(dictionary).from_json_mappings("Valorant", as_json)
    assert restored.mappings == dictionary.mappings
