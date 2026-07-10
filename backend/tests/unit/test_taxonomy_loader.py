from __future__ import annotations

import pytest

from codeverse_core.data.taxonomy_loader import (
    TaxonomyConcept,
    categories,
    concepts_by_category,
    concepts_by_tier,
    get_concept,
    load_all_taxonomies,
    load_taxonomy,
)

_VALID_TIERS = {"core", "builtin", "method", "type", "exception", "library"}


@pytest.mark.parametrize("language", ["python", "sql"])
def test_load_taxonomy_nonempty(language):
    concepts = load_taxonomy(language)
    assert len(concepts) > 100
    assert all(isinstance(c, TaxonomyConcept) for c in concepts)


@pytest.mark.parametrize("language", ["python", "sql"])
def test_all_concept_ids_unique(language):
    concepts = load_taxonomy(language)
    ids = [c.concept_id for c in concepts]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("language", ["python", "sql"])
def test_schema_fields_populated(language):
    for c in load_taxonomy(language):
        assert c.concept_id
        assert c.category
        assert c.tier in _VALID_TIERS
        assert c.title
        assert c.real_syntax
        assert c.description
        assert c.language == language


def test_load_taxonomy_rejects_unknown_language():
    with pytest.raises(ValueError, match="desteklenmeyen dil"):
        load_taxonomy("cobol")  # type: ignore[arg-type]


def test_get_concept_known_and_unknown():
    concept = get_concept("python", "py_str_upper")
    assert concept is not None
    assert concept.real_syntax == "string.upper()"
    assert concept.tier == "method"
    assert concept.is_sandbox_safe is True

    assert get_concept("python", "does_not_exist") is None


def test_library_tier_is_not_sandbox_safe():
    library_concepts = concepts_by_tier("python", "library")
    assert library_concepts
    assert all(not c.is_sandbox_safe for c in library_concepts)

    core_concepts = concepts_by_tier("python", "core")
    assert core_concepts
    assert all(c.is_sandbox_safe for c in core_concepts)


def test_categories_and_concepts_by_category_consistent():
    cats = categories("python")
    assert "string_methods" in cats
    string_methods = concepts_by_category("python", "string_methods")
    assert len(string_methods) > 10
    assert all(c.category == "string_methods" for c in string_methods)
    assert concepts_by_category("python", "not_a_real_category") == ()


def test_load_all_taxonomies_returns_both_languages():
    all_tax = load_all_taxonomies()
    assert set(all_tax.keys()) == {"python", "sql"}
    assert len(all_tax["python"]) == len(load_taxonomy("python"))
    assert len(all_tax["sql"]) == len(load_taxonomy("sql"))


def test_sql_join_concept_present():
    concept = get_concept("sql", "sql_kw_left_join")
    assert concept is not None
    assert "JOIN" in concept.real_syntax.upper()
