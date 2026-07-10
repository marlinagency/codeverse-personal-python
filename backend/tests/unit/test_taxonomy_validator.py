from __future__ import annotations

from codeverse_core.data.taxonomy_loader import load_taxonomy
from codeverse_core.theme_mapping.validator import (
    validate_personal_python_dictionary_quality,
    validate_taxonomy_batch,
    validate_taxonomy_dictionary_complete,
)


def test_valid_batch_passes():
    problems = validate_taxonomy_batch({"upper": "sesi_yukselt", "lower": "sessize_al"})
    assert problems == []


def test_empty_token_reported():
    problems = validate_taxonomy_batch({"upper": "", "lower": "sessize_al"})
    assert any("empty token" in p for p in problems)


def test_non_identifier_token_reported():
    problems = validate_taxonomy_batch({"upper": "iki kelime", "lower": "3baslar"})
    assert len([p for p in problems if "identifier" in p]) == 2


def test_reserved_keyword_collision_reported():
    problems = validate_taxonomy_batch({"upper": "select", "lower": "def"})
    assert len([p for p in problems if "reserved keyword" in p]) == 2


def test_dsl_type_name_collision_reported():
    problems = validate_taxonomy_batch({"upper": "int", "lower": "dict"})
    assert len([p for p in problems if "DSL type name" in p]) == 2


def test_token_copying_real_syntax_name_rejected():
    problems = validate_taxonomy_batch(
        {"upper": "upper", "left_join": "sol_birlestir"},
        reserved_names={"upper", "left_join", "lower"},
    )
    assert any("copies a real syntax name" in p for p in problems)
    # left_join's token differs from every real name -> no complaint for it
    assert not any("left_join" in p and "copies" in p for p in problems)


def test_duplicate_within_same_batch_reported():
    problems = validate_taxonomy_batch({"upper": "ayni_tok", "lower": "AYNI_TOK"})
    assert any("duplicate token" in p and "same batch" in p for p in problems)


def test_duplicate_across_batches_reported():
    problems = validate_taxonomy_batch(
        {"split": "yeni_token"},
        used_tokens={"yeni_token": "upper"},
    )
    assert any("duplicates a token already used" in p and "upper" in p for p in problems)


def test_same_name_reusing_its_own_prior_token_is_not_a_duplicate():
    # regenerating/re-validating the same canonical_name against itself must
    # not be flagged — only DIFFERENT names colliding on one token is a problem
    problems = validate_taxonomy_batch(
        {"upper": "tok"},
        used_tokens={"tok": "upper"},
    )
    assert problems == []


def test_unicode_tokens_accepted():
    problems = validate_taxonomy_batch({"upper": "büyükharf", "lower": "küçükharf"})
    assert problems == []


def test_multiple_problems_all_reported():
    problems = validate_taxonomy_batch({"upper": "", "lower": "select", "split": "int"})
    assert len(problems) == 3


# ------------------------------------------------- whole-dictionary completeness


def test_complete_dictionary_no_missing():
    mappings = {"py_str_upper": "tok1", "py_str_lower": "tok2"}
    problems = validate_taxonomy_dictionary_complete(
        mappings, required_concept_ids=["py_str_upper", "py_str_lower"]
    )
    assert problems == []


def test_missing_concept_ids_reported():
    mappings = {"py_str_upper": "tok1"}
    problems = validate_taxonomy_dictionary_complete(
        mappings, required_concept_ids=["py_str_upper", "py_str_lower", "py_str_split"]
    )
    assert len(problems) == 1
    assert "py_str_lower" in problems[0]
    assert "py_str_split" in problems[0]


def test_missing_list_truncated_after_ten():
    required = [f"concept_{i}" for i in range(15)]
    problems = validate_taxonomy_dictionary_complete({}, required_concept_ids=required)
    assert "15 concept_id" in problems[0]
    assert "+5 more" in problems[0]


def test_complete_submarine_taxonomy_dictionary_validates_all_concept_ids():
    concept_ids = [
        concept.concept_id
        for language in ("python", "sql")
        for concept in load_taxonomy(language)
    ]
    mappings = {
        concept_id: f"denizalti_token_{index}"
        for index, concept_id in enumerate(concept_ids, start=1)
    }

    assert validate_taxonomy_dictionary_complete(mappings, concept_ids) == []
    assert validate_taxonomy_batch(mappings) == []


def test_blank_token_counts_as_missing():
    mappings = {"py_str_upper": "   "}
    problems = validate_taxonomy_dictionary_complete(
        mappings, required_concept_ids=["py_str_upper"]
    )
    assert len(problems) == 1


# ------------------------------------------------- Personal Python quality gate


def _personal_core_mappings() -> dict[str, str]:
    return {
        "py_kw_if": "monster_check",
        "py_kw_elif": "curse_shift",
        "py_kw_else": "safe_path",
        "py_kw_for": "monster_trail",
        "py_kw_in": "inside_bestiary",
        "py_kw_def": "sign_cast",
        "py_kw_return": "quest_reward",
        "py_fn_print": "quest_notice",
        "py_fn_range": "trail_range",
        "py_fn_list": "alchemy_kit",
        "py_fn_dict": "bestiary_record",
        "py_kw_class": "school_blueprint",
        "py_kw_try": "risky_contract",
        "py_kw_except": "failed_sign",
    }


def test_personal_python_quality_gate_accepts_good_dictionary():
    assert validate_personal_python_dictionary_quality(_personal_core_mappings()) == []


def test_personal_python_quality_gate_rejects_sql_leak_and_missing_core():
    mappings = _personal_core_mappings()
    mappings.pop("py_kw_if")
    mappings["sql_kw_select"] = "quest_select"

    problems = validate_personal_python_dictionary_quality(mappings)

    assert any("SQL concept_ids leaked" in problem for problem in problems)
    assert any("py_kw_if" in problem for problem in problems)


def test_personal_python_quality_gate_rejects_raw_or_generic_token_parts():
    mappings = _personal_core_mappings()
    mappings["py_kw_if"] = "witcher_evreniyle_flow"
    mappings["py_kw_for"] = "generic_route"
    mappings["py_fn_print"] = "print_statement"
    mappings["py_fn_list"] = "code_file"
    mappings["py_fn_dict"] = "sipandcode_notes"

    problems = validate_personal_python_dictionary_quality(mappings)

    assert any("evreniyle" in problem for problem in problems)
    assert any("generic" in problem for problem in problems)
    assert any("statement" in problem for problem in problems)
    assert any("code" in problem for problem in problems)
    assert any("generic technical wording" in problem for problem in problems)


def test_personal_python_quality_gate_rejects_bad_rationale_phrases():
    problems = validate_personal_python_dictionary_quality(
        _personal_core_mappings(),
        {"py_fn_iter": "Gives iter a theme-specific name as a Python function."},
    )

    assert any("generic phrase" in problem for problem in problems)
