from __future__ import annotations

import contextlib
import io
import json

import pytest

from codeverse_core.cvl.pipeline import CompilationPipeline
from codeverse_core.theme_mapping.taxonomy_generator import (
    TaxonomyGenerationError,
    generate_batch_mapping,
    generate_theme_profile,
)
from codeverse_core.theme_mapping.generator import TaxonomyThemeDictionaryGenerator
from codeverse_core.theme_mapping.taxonomy_prompts import MappableConcept, ThemeProfile


class _StubProvider:
    """Chat-capable stub: returns queued raw responses in order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    @property
    def provider_name(self) -> str:
        return "stub"

    def chat(self, messages, *, temperature, max_tokens) -> str:
        self.calls.append(messages)
        return self._responses.pop(0)


def _mc(name, kind="method"):
    return MappableConcept(
        canonical_name=name, kind=kind, language="python",
        concept_ids=(f"py_str_{name}",), hint="does a thing", category="strings",
    )


def _concept(
    name,
    *,
    kind="method",
    language="python",
    category="strings",
    ids=None,
):
    return MappableConcept(
        canonical_name=name,
        kind=kind,
        language=language,
        concept_ids=tuple(ids or (f"{language}_{category}_{name}",)),
        hint="does a thing",
        category=category,
    )


# ------------------------------------------------------------ theme profile


def test_generate_theme_profile_success_first_try():
    raw = json.dumps({"motifs": ["a", "b"], "tone": "t", "output_language": "tr"})
    provider = _StubProvider([raw])
    profile = generate_theme_profile(provider, "Valorant", "tr")
    assert profile.motifs == ("a", "b")
    assert len(provider.calls) == 1


def test_generate_theme_profile_retries_on_bad_json_then_succeeds():
    good = json.dumps({"motifs": ["a"], "tone": "t", "output_language": "en"})
    provider = _StubProvider(["not json at all", good])
    profile = generate_theme_profile(provider, "x", max_attempts=3)
    assert profile.motifs == ("a",)
    assert len(provider.calls) == 2


def test_generate_theme_profile_raises_after_max_attempts():
    provider = _StubProvider(["junk", "junk", "junk"])
    with pytest.raises(TaxonomyGenerationError, match="tema profili"):
        generate_theme_profile(provider, "x", max_attempts=3)
    assert len(provider.calls) == 3


def test_generate_theme_profile_fallback_recognizes_witcher_turkish_prompt():
    provider = _StubProvider(["junk", "junk"])

    profile = generate_theme_profile(
        provider,
        "witcher evreniyle olustur",
        max_attempts=2,
        fallback_on_failure=True,
    )

    assert profile.clean_theme == "The Witcher 3"
    assert profile.family_motifs["condition"][0] == "monster check"
    assert profile.family_motifs["iteration"][0] == "monster trail"
    assert "witcher evreniyle" not in " ".join(profile.motifs).casefold()


def test_profile_seeded_fast_path_can_skip_second_llm_batch():
    profile = json.dumps(
        {
            "clean_theme": "Chess",
            "primary_world": "Chess",
            "motifs": ["board", "move", "signal", "rank"],
            "tone": "strategic",
            "output_language": "en",
        }
    )
    provider = _StubProvider([profile])
    concepts = [
        _concept("if", kind="keyword", category="keywords", ids=("py_kw_if",)),
        _concept("print", kind="builtin", category="builtins", ids=("py_fn_print",)),
    ]

    dictionary = TaxonomyThemeDictionaryGenerator(provider, max_attempts=1).generate_profile_seeded(
        "chess",
        languages=("python",),
        concepts=concepts,
        critical_overrides_enabled=False,
        profile_fallback_on_failure=False,
    )

    assert len(provider.calls) == 1
    assert dictionary.mappings["py_kw_if"]
    assert dictionary.mappings["py_fn_print"]


def test_profile_seeded_can_require_a_real_model_profile():
    provider = _StubProvider(["not valid json"])

    with pytest.raises(TaxonomyGenerationError, match="tema profili"):
        TaxonomyThemeDictionaryGenerator(provider, max_attempts=1).generate_profile_seeded(
            "chess",
            languages=("python",),
            concepts=[_concept("if", kind="keyword", category="keywords", ids=("py_kw_if",))],
            critical_overrides_enabled=False,
            profile_fallback_on_failure=False,
        )


# ------------------------------------------------------------- batch mapping


_PROFILE = ThemeProfile(theme="x", motifs=("a",), tone="t", output_language="en")


def test_generate_batch_mapping_success_first_try():
    batch = [_mc("upper"), _mc("lower")]
    raw = json.dumps({"mappings": {"upper": "tok1", "lower": "tok2"}})
    provider = _StubProvider([raw])
    result = generate_batch_mapping(provider, _PROFILE, batch, forbidden_tokens=[])
    assert result.mappings == {"upper": "tok1", "lower": "tok2"}


def test_generate_batch_mapping_retries_with_corrective_feedback():
    batch = [_mc("upper"), _mc("lower")]
    bad = json.dumps({"mappings": {"upper": "tok1"}})  # missing 'lower'
    good = json.dumps({"mappings": {"upper": "tok1", "lower": "tok2"}})
    provider = _StubProvider([bad, good])

    result = generate_batch_mapping(provider, _PROFILE, batch, forbidden_tokens=[])

    assert result.mappings["lower"] == "tok2"
    # second call must carry corrective feedback mentioning the missing name
    second_call_body = provider.calls[1][-1]["content"]
    assert "eksik" in second_call_body or "lower" in second_call_body


def test_generate_batch_mapping_raises_after_max_attempts():
    batch = [_mc("upper")]
    provider = _StubProvider([json.dumps({"mappings": {}})] * 3)
    with pytest.raises(TaxonomyGenerationError, match="batch eşleme"):
        generate_batch_mapping(provider, _PROFILE, batch, forbidden_tokens=[], max_attempts=3)
    assert len(provider.calls) == 3


def test_generate_batch_mapping_passes_forbidden_tokens_through():
    batch = [_mc("upper")]
    raw = json.dumps({"mappings": {"upper": "tok1"}})
    provider = _StubProvider([raw])
    generate_batch_mapping(provider, _PROFILE, batch, forbidden_tokens=["already_used"])
    assert "already_used" in provider.calls[0][-1]["content"]


# -------------------------------------------------------- taxonomy orchestrator


def _profile_json():
    return json.dumps({"motifs": ["site", "spike"], "tone": "tactical", "output_language": "tr"})


def _personal_gta_profile_json():
    return json.dumps(
        {
            "clean_theme": "GTA San Andreas",
            "learner_summary": "The learner loves GTA San Andreas and wants loops and functions to feel familiar.",
            "primary_world": "GTA San Andreas",
            "motifs": ["Grove Street", "mission payout", "radio callout", "street route", "safehouse"],
            "learning_pain_points": ["loops", "functions"],
            "concept_preferences": {
                "loop": "street route",
                "output": "radio callout",
                "function": "mission",
            },
            "tone": "street-level and clear",
            "output_language": "en",
        }
    )


def test_taxonomy_generator_runs_category_batches_and_fans_out_aliases():
    concepts = [
        _concept(
            "upper",
            category="strings",
            ids=("py_str_upper", "py_bytes_upper"),
        ),
        _concept("lower", category="strings", ids=("py_str_lower",)),
        _concept(
            "left_join",
            kind="keyword",
            language="sql",
            category="joins",
            ids=("sql_kw_left_join",),
        ),
    ]
    provider = _StubProvider(
        [
            _profile_json(),
            json.dumps({"mappings": {"lower": "sessize_al", "upper": "sesi_yukselt"}}),
            json.dumps({"mappings": {"left_join": "sol_kanat_bagla"}}),
        ]
    )
    generator = TaxonomyThemeDictionaryGenerator(provider, chunk_size=40)

    dictionary = generator.generate("Valorant", "tr", concepts=concepts)

    assert dictionary.theme_dictionary == {
        "py_str_lower": "sessize_al",
        "py_str_upper": "sesi_yukselt",
        "py_bytes_upper": "sesi_yukselt",
        "sql_kw_left_join": "sol_kanat_bagla",
    }
    assert [b.category for b in dictionary.batches] == ["strings", "joins"]
    assert dictionary.batches[0].attempts == 1
    assert len(provider.calls) == 3
    first_batch_prompt = provider.calls[1][-1]["content"]
    second_batch_prompt = provider.calls[2][-1]["content"]
    assert "- upper:" in first_batch_prompt
    assert "left_join" not in first_batch_prompt
    assert "sesi_yukselt" in second_batch_prompt


def test_taxonomy_generator_retries_with_feedback_for_duplicate_tokens():
    concepts = [
        _concept("upper", category="strings"),
        _concept("lower", category="strings"),
    ]
    provider = _StubProvider(
        [
            _profile_json(),
            json.dumps({"mappings": {"lower": "aynisi", "upper": "aynisi"}}),
            json.dumps({"mappings": {"lower": "sessiz", "upper": "yuksek"}}),
        ]
    )
    generator = TaxonomyThemeDictionaryGenerator(provider, max_attempts=3)

    dictionary = generator.generate("Valorant", "tr", concepts=concepts)

    assert dictionary.mappings["python_strings_lower"] == "sessiz"
    assert dictionary.batches[0].attempts == 2
    retry_prompt = provider.calls[2][-1]["content"]
    assert "previous attempt was rejected" in retry_prompt
    assert "duplicate token" in retry_prompt


def test_taxonomy_generator_rejects_real_syntax_name_and_raises_after_attempts():
    concepts = [_concept("upper", category="strings")]
    provider = _StubProvider(
        [
            _profile_json(),
            json.dumps({"mappings": {"upper": "upper"}}),
            json.dumps({"mappings": {"upper": "upper"}}),
        ]
    )
    generator = TaxonomyThemeDictionaryGenerator(provider, max_attempts=2)

    with pytest.raises(TaxonomyGenerationError, match="copies a real syntax name"):
        generator.generate("Valorant", "tr", concepts=concepts)
    assert len(provider.calls) == 3


def test_taxonomy_generator_chunks_large_categories():
    concepts = [
        _concept("upper", category="strings"),
        _concept("lower", category="strings"),
    ]
    provider = _StubProvider(
        [
            _profile_json(),
            json.dumps({"mappings": {"lower": "tok_lower"}}),
            json.dumps({"mappings": {"upper": "tok_upper"}}),
        ]
    )
    generator = TaxonomyThemeDictionaryGenerator(provider, chunk_size=1)

    dictionary = generator.generate("Valorant", "tr", concepts=concepts)

    assert [b.canonical_names for b in dictionary.batches] == [("lower",), ("upper",)]
    assert dictionary.mappings["python_strings_upper"] == "tok_upper"


def test_profile_seeded_generator_builds_complete_valid_dictionary_fast():
    concepts = [
        _concept("upper", category="strings", ids=("py_str_upper", "py_bytes_upper")),
        _concept("lower", category="strings", ids=("py_str_lower",)),
        _concept("left_join", language="sql", category="joins", kind="keyword", ids=("sql_kw_left_join",)),
    ]
    provider = _StubProvider([_profile_json()])
    generator = TaxonomyThemeDictionaryGenerator(provider)

    dictionary = generator.generate_profile_seeded("deniz alti", "tr", concepts=concepts)

    assert set(dictionary.mappings) == {
        "py_str_upper",
        "py_bytes_upper",
        "py_str_lower",
        "sql_kw_left_join",
    }
    assert dictionary.mappings["py_str_upper"] == dictionary.mappings["py_bytes_upper"]
    assert len(set(dictionary.mappings.values())) == 3
    theme_terms = ("site", "spike", "tactical", "deniz", "alti")
    python_tokens = {
        token
        for concept_id, token in dictionary.mappings.items()
        if concept_id.startswith("py_")
    }
    assert all(any(term in token for term in theme_terms) for token in python_tokens)
    unique_tokens = set(dictionary.mappings.values())
    assert len({token.split("_")[0] for token in unique_tokens}) >= 2
    assert len(provider.calls) == 1


def test_profile_seeded_python_only_excludes_sql_when_requested():
    provider = _StubProvider([_personal_gta_profile_json(), "not used by critical override"])
    generator = TaxonomyThemeDictionaryGenerator(provider)

    dictionary = generator.generate_profile_seeded(
        "gta san andreas oyununu oynamayi seviyorum",
        languages=("python",),
    )

    assert dictionary.theme == "GTA San Andreas"
    assert dictionary.mappings
    assert all(key.startswith("py_") for key in dictionary.mappings)
    assert not any(key.startswith("sql_") for key in dictionary.mappings)
    assert len(dictionary.mappings) > 150


def test_profile_seeded_repairs_iter_token_and_rationale_for_long_turkish_prompt():
    concepts = [
        _concept("iter", kind="builtin", category="builtin_functions", ids=("py_fn_iter",)),
        _concept("print", kind="builtin", category="builtin_functions", ids=("py_fn_print",)),
    ]
    raw_prompt = (
        "gta san andreas oyununu oynamayi seviyorum ve python ogrenmek istiyorum "
        "ama iter ve print kavramlari bana karisik geliyor"
    )
    provider = _StubProvider([_personal_gta_profile_json()])
    generator = TaxonomyThemeDictionaryGenerator(provider)

    dictionary = generator.generate_profile_seeded(
        raw_prompt,
        output_language=None,
        languages=("python",),
        concepts=concepts,
    )

    iter_token = dictionary.mappings["py_fn_iter"]
    iter_rationale = dictionary.rationale["py_fn_iter"].casefold()
    print_token = dictionary.mappings["py_fn_print"]

    assert "iter" not in iter_token
    assert len(iter_token.split("_")) <= 3
    assert "theme-specific" not in iter_rationale
    assert "gives iter" not in iter_rationale
    assert "feel connected" not in iter_rationale
    assert "concept idea" not in iter_rationale
    assert raw_prompt.casefold() not in iter_rationale
    assert "python function" not in iter_rationale
    assert dictionary.profile.output_language == "en"
    assert any(part in iter_token for part in ("street", "route", "grove", "mission"))
    assert any(part in print_token for part in ("radio", "callout", "mission"))


def test_profile_seeded_uses_concept_family_preferences_for_generic_theme():
    concepts = [
        _concept("if", kind="keyword", category="keywords", ids=("py_kw_if",)),
        _concept("for", kind="keyword", category="keywords", ids=("py_kw_for",)),
        _concept("print", kind="builtin", category="builtin_functions", ids=("py_fn_print",)),
        _concept("dict", kind="builtin", category="builtin_functions", ids=("py_fn_dict",)),
        _concept("def", kind="keyword", category="keywords", ids=("py_kw_def",)),
    ]
    profile = json.dumps(
        {
            "clean_theme": "Philosophers",
            "learner_summary": "The learner likes philosophers and wants Python ideas to feel logical.",
            "primary_world": "Philosophers",
            "motifs": [
                "Socratic question", "academy walk", "dialogue voice",
                "scroll archive", "argument method",
            ],
            "learning_pain_points": ["if", "for", "function"],
            "concept_preferences": {
                "condition": "logic test",
                "loop": "academy walk",
                "output": "dialogue voice",
                "data": "scroll archive",
                "function": "argument method",
            },
            "tone": "clear and thoughtful",
            "output_language": "en",
        }
    )
    provider = _StubProvider([profile])
    generator = TaxonomyThemeDictionaryGenerator(provider)

    dictionary = generator.generate_profile_seeded(
        "I love philosophers and if/for/function confuse me",
        languages=("python",),
        concepts=concepts,
    )

    assert dictionary.mappings["py_kw_if"].startswith("logic_test")
    assert dictionary.mappings["py_kw_for"].startswith("academy_walk")
    assert dictionary.mappings["py_fn_print"].startswith("dialogue_voice")
    assert dictionary.mappings["py_fn_dict"].startswith("scroll_archive")
    assert dictionary.mappings["py_kw_def"].startswith("argument_method")
    for text in dictionary.rationale.values():
        folded = text.casefold()
        assert "feel connected" not in folded
        assert "concept idea" not in folded
        assert "theme-specific" not in folded


def test_profile_seeded_uses_standard_family_motifs_for_any_theme():
    concepts = [
        _concept("if", kind="keyword", category="keywords", ids=("py_kw_if",)),
        _concept("for", kind="keyword", category="keywords", ids=("py_kw_for",)),
        _concept("def", kind="keyword", category="keywords", ids=("py_kw_def",)),
        _concept("print", kind="builtin", category="builtin_functions", ids=("py_fn_print",)),
        _concept("dict", kind="builtin", category="builtin_functions", ids=("py_fn_dict",)),
        _concept("class", kind="keyword", category="keywords", ids=("py_kw_class",)),
        _concept("try", kind="keyword", category="keywords", ids=("py_kw_try",)),
    ]
    profile = json.dumps(
        {
            "clean_theme": "Deep Sea Exploration",
            "learner_summary": "The learner imagines submarines and wants Python to feel navigable.",
            "primary_world": "Deep Sea Exploration",
            "motifs": [
                "sonar check", "dive route", "mission protocol",
                "radio ping", "logbook", "vessel blueprint", "pressure leak",
            ],
            "learning_pain_points": ["if", "for", "function", "class"],
            "family_motifs": {
                "condition": ["sonar check"],
                "iteration": ["dive route"],
                "function": ["mission protocol"],
                "output": ["radio ping"],
                "data": ["logbook"],
                "oop": ["vessel blueprint"],
                "error": ["pressure leak"],
            },
            "tone": "calm and exploratory",
            "output_language": "en",
        }
    )
    provider = _StubProvider([profile])
    generator = TaxonomyThemeDictionaryGenerator(provider)

    dictionary = generator.generate_profile_seeded(
        "I like submarines and deep sea exploration",
        languages=("python",),
        concepts=concepts,
    )

    assert dictionary.mappings["py_kw_if"].startswith("sonar_check")
    assert dictionary.mappings["py_kw_for"].startswith("dive_route")
    assert dictionary.mappings["py_kw_def"].startswith("mission_protocol")
    assert dictionary.mappings["py_fn_print"].startswith("radio_ping")
    assert dictionary.mappings["py_fn_dict"].startswith("logbook")
    assert dictionary.mappings["py_kw_class"].startswith("vessel_blueprint")
    assert dictionary.mappings["py_kw_try"].startswith("pressure_leak")
    for token in dictionary.mappings.values():
        assert len(token.split("_")) <= 3
    for text in dictionary.rationale.values():
        folded = text.casefold()
        assert "feel connected" not in folded
        assert "theme-specific" not in folded
        assert "python function" not in folded


def test_profile_seeded_fallback_keeps_witcher_tokens_concept_aware():
    concepts = [
        _concept("if", kind="keyword", category="keywords", ids=("py_kw_if",)),
        _concept("for", kind="keyword", category="keywords", ids=("py_kw_for",)),
        _concept("def", kind="keyword", category="keywords", ids=("py_kw_def",)),
        _concept("print", kind="builtin", category="builtin_functions", ids=("py_fn_print",)),
    ]
    provider = _StubProvider(["junk", "junk", "junk", "junk"])
    generator = TaxonomyThemeDictionaryGenerator(provider)

    dictionary = generator.generate_profile_seeded(
        "witcher evreniyle olustur",
        languages=("python",),
        concepts=concepts,
    )

    assert dictionary.theme == "The Witcher 3"
    assert dictionary.mappings["py_kw_if"].startswith("monster_check")
    assert dictionary.mappings["py_kw_for"].startswith("monster_trail")
    assert dictionary.mappings["py_kw_def"].startswith("sign_cast")
    assert dictionary.mappings["py_fn_print"].startswith("quest_notice")
    for token in dictionary.mappings.values():
        assert "evreniyle" not in token
        assert not token.endswith("_flow")


def test_profile_seeded_reserves_witcher_core_tokens_in_full_python_dictionary():
    provider = _StubProvider(["junk", "junk", "junk", "junk"])
    generator = TaxonomyThemeDictionaryGenerator(provider)

    dictionary = generator.generate_profile_seeded(
        "witcher evreniyle olustur",
        languages=("python",),
    )

    assert len(dictionary.mappings) > 150
    assert dictionary.mappings["py_kw_if"] == "monster_check"
    assert dictionary.mappings["py_kw_for"] == "monster_trail"
    assert dictionary.mappings["py_kw_def"] == "sign_cast"
    assert dictionary.mappings["py_fn_print"] == "quest_notice"
    assert not any(token == "witcher_evreniyle_flow" for token in dictionary.mappings.values())


def test_profile_seeded_hardens_parseable_but_weak_llm_profile_for_known_theme():
    weak_profile = json.dumps(
        {
            "clean_theme": "witcher evreniyle olustur",
            "learner_summary": "The learner typed a Witcher prompt.",
            "primary_world": "witcher evreniyle",
            "motifs": ["witcher evreniyle flow", "generic route", "python token"],
            "family_motifs": {
                "condition": ["witcher evreniyle flow"],
                "iteration": ["generic route"],
                "function": ["python function"],
                "output": ["theme signal"],
            },
            "concept_preferences": {
                "condition": "witcher evreniyle flow",
                "loop": "generic route",
                "function": "python function",
                "output": "theme signal",
            },
            "tone": "generic",
            "output_language": "en",
        }
    )
    provider = _StubProvider([weak_profile])
    generator = TaxonomyThemeDictionaryGenerator(provider)

    dictionary = generator.generate_profile_seeded(
        "witcher evreniyle olustur",
        languages=("python",),
    )

    assert dictionary.theme == "The Witcher 3"
    assert dictionary.mappings["py_kw_if"] == "monster_check"
    assert dictionary.mappings["py_kw_for"] == "monster_trail"
    assert dictionary.mappings["py_kw_def"] == "sign_cast"
    assert dictionary.mappings["py_fn_print"] == "quest_notice"
    for token in dictionary.mappings.values():
        assert "evreniyle" not in token
        assert "generic" not in token
        assert "python" not in token


def test_profile_seeded_hardens_sparse_llm_profile_for_arbitrary_prompt():
    sparse_profile = json.dumps(
        {
            "clean_theme": "late night coffee study",
            "learner_summary": "The learner studies at night with coffee.",
            "primary_world": "late night coffee study",
            "motifs": ["theme", "python token", "coffee mug"],
            "family_motifs": {
                "condition": ["generic flow"],
                "iteration": [],
                "function": ["python function"],
            },
            "concept_preferences": {"condition": "theme specific"},
            "tone": "calm",
            "output_language": "en",
        }
    )
    provider = _StubProvider([sparse_profile])
    generator = TaxonomyThemeDictionaryGenerator(provider)

    dictionary = generator.generate_profile_seeded(
        "I study Python late at night with coffee and functions/loops confuse me",
        languages=("python",),
    )

    assert dictionary.theme == "Late Night Coffee Study"
    assert len(dictionary.mappings) > 150
    assert dictionary.profile is not None
    for family in ("condition", "iteration", "function", "output", "data", "oop", "error"):
        assert dictionary.profile.family_motifs[family]
    assert dictionary.mappings["py_kw_if"].startswith("late_") or "coffee" in dictionary.mappings["py_kw_if"]
    assert dictionary.mappings["py_kw_for"].startswith("late_") or "coffee" in dictionary.mappings["py_kw_for"]
    assert dictionary.mappings["py_kw_def"].startswith("late_") or "coffee" in dictionary.mappings["py_kw_def"]
    for token in dictionary.mappings.values():
        parts = set(token.split("_"))
        assert not (parts & {"theme", "generic", "python", "token", "specific"})
        assert len(token.split("_")) <= 3


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        (
            "counter strike 2 seviyorum if for def print karisik geliyor",
            {
                "theme": "Counter-Strike 2",
                "if": "clutch_check",
                "for": "site_rotation",
                "def": "utility_lineup",
                "print": "team_callout",
            },
        ),
        (
            "gta san andreas evreniyle olustur",
            {
                "theme": "GTA San Andreas",
                "if": "wanted_check",
                "for": "street_route",
                "def": "mission_plan",
                "print": "radio_callout",
            },
        ),
        (
            "minecraft redstone ve crafting ile python ogrenmek istiyorum",
            {
                "theme": "Minecraft",
                "if": "redstone_check",
                "for": "minecart_route",
                "def": "craft_recipe",
                "print": "beacon_signal",
            },
        ),
        (
            "formula 1 pit stop ve yaris stratejisiyle olustur",
            {
                "theme": "Formula 1",
                "if": "strategy_check",
                "for": "lap_cycle",
                "def": "pit_plan",
                "print": "radio_message",
            },
        ),
        (
            "harry potter hogwarts spell temasi",
            {
                "theme": "Harry Potter",
                "if": "spell_check",
                "for": "hall_patrol",
                "def": "spell_cast",
                "print": "owl_message",
            },
        ),
        (
            "witcher evreniyle olustur",
            {
                "theme": "The Witcher 3",
                "if": "monster_check",
                "for": "monster_trail",
                "def": "sign_cast",
                "print": "quest_notice",
            },
        ),
        (
            "felsefe ve socrates ile dusunen bir python dili",
            {
                "theme": "Philosophers",
                "if": "logic_test",
                "for": "academy_walk",
                "def": "argument_method",
                "print": "dialogue_voice",
            },
        ),
        (
            "ucak muhendisi gibi dusunuyorum aviation ve flight temali olsun",
            {
                "theme": "Aviation",
                "if": "preflight_check",
                "for": "flight_path",
                "def": "flight_plan",
                "print": "tower_call",
            },
        ),
        (
            "uzay galaksi nasa black hole temasi",
            {
                "theme": "Space Exploration",
                "if": "orbit_check",
                "for": "orbit_path",
                "def": "launch_plan",
                "print": "radio_ping",
            },
        ),
        (
            "cooking baking chef kitchen recipes ile python",
            {
                "theme": "Cooking",
                "if": "taste_check",
                "for": "prep_line",
                "def": "recipe_method",
                "print": "order_call",
            },
        ),
    ],
)
def test_profile_seeded_fallback_quality_for_common_personal_worlds(prompt, expected):
    provider = _StubProvider(["junk"] * 4)
    generator = TaxonomyThemeDictionaryGenerator(provider)

    dictionary = generator.generate_profile_seeded(prompt, languages=("python",))

    assert dictionary.theme == expected["theme"]
    assert len(dictionary.mappings) > 150
    assert all(key.startswith("py_") for key in dictionary.mappings)
    assert dictionary.mappings["py_kw_if"] == expected["if"]
    assert dictionary.mappings["py_kw_for"] == expected["for"]
    assert dictionary.mappings["py_kw_def"] == expected["def"]
    assert dictionary.mappings["py_fn_print"] == expected["print"]
    for token in dictionary.mappings.values():
        token_parts = set(token.casefold().split("_"))
        assert not (token_parts & {"evreniyle", "olustur", "seviyorum", "karisik"})
    for rationale in dictionary.rationale.values():
        folded = rationale.casefold()
        assert "theme-specific" not in folded
        assert "feel connected" not in folded
        assert "gives iter" not in folded
        assert "specific name" not in folded
        assert "python function" not in folded
        assert "concept idea" not in folded


def test_profile_seeded_dictionary_compiles_and_runs_personal_python_sample():
    provider = _StubProvider(["junk"] * 4)
    generator = TaxonomyThemeDictionaryGenerator(provider)
    dictionary = generator.generate_profile_seeded(
        "witcher evreniyle olustur",
        languages=("python",),
    )
    maps = dictionary.mappings
    source = f"""@theme: {dictionary.theme}
@language: python
@version: 1
---
{maps["py_kw_def"]} reward_path(levels):
    cv_record = {maps["py_fn_dict"]}({{"base": 100}})
    cv_rewards = {maps["py_fn_list"]}([])
    {maps["py_kw_for"]} cv_level {maps["py_kw_in"]} levels:
        {maps["py_kw_if"]} cv_level <= 1:
            cv_rewards.append(cv_record["base"])
        {maps["py_kw_else"]}:
            cv_rewards.append(cv_level * 50)
    {maps["py_kw_return"]} cv_rewards

{maps["py_kw_for"]} cv_value {maps["py_kw_in"]} reward_path({maps["py_fn_range"]}(1, 4)):
    {maps["py_fn_print"]}(cv_value)
"""

    compiled = CompilationPipeline().compile(source, dictionary)
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exec(compiled.codegen.source_code, {})  # noqa: S102 - executes generated test code

    assert compiled.codegen.target_language == "python"
    assert stdout.getvalue() == "100\n100\n150\n"


@pytest.mark.parametrize(
    "prompt",
    (
        "SWAT Police Operations",
        "I repair elevators and think in floors, cables, and safety checks",
        "the quiet feeling of rain moving across a train window at night",
        "I study marine biology, love coral reefs, and struggle with functions and loops",
    ),
)
def test_profile_seeded_keeps_arbitrary_learning_tokens_compact(prompt):
    provider = _StubProvider(["junk"] * 4)
    dictionary = TaxonomyThemeDictionaryGenerator(provider).generate_profile_seeded(
        prompt,
        languages=("python",),
    )

    compact_ids = {
        "py_kw_def", "py_kw_return", "py_fn_print", "py_fn_str",
        "py_kw_if", "py_kw_elif", "py_kw_else", "py_kw_for",
        "py_kw_while", "py_kw_break", "py_kw_continue",
        "py_fn_list", "py_fn_dict", "py_fn_set", "py_fn_tuple",
        "py_fn_open", "py_file_read", "py_file_write",
    }
    for concept_id in compact_ids:
        token = dictionary.mappings[concept_id]
        assert len(token) <= 16, (concept_id, token)
        assert len(token.split("_")) <= 2, (concept_id, token)
    for concept_id, token in dictionary.mappings.items():
        assert len(token) <= 20, (concept_id, token)
        assert len(token.split("_")) <= 2, (concept_id, token)


def test_long_tail_builtins_stay_short_and_keep_python_behavior_cues():
    names = ("bytearray", "bytes", "callable", "chr", "compile", "complex")
    concepts = [
        _concept(name, kind="builtin", category="builtin_functions", ids=(f"py_fn_{name}",))
        for name in names
    ]
    profile = json.dumps(
        {
            "clean_theme": "Emergency Dispatch",
            "learner_summary": "The learner thinks through dispatch operations.",
            "primary_world": "Emergency Dispatch",
            "motifs": ["patrol", "radio", "unit", "signal", "roster", "alert"],
            "family_motifs": {
                "condition": ["safety check"], "iteration": ["patrol route"],
                "function": ["dispatch action"], "output": ["radio call"],
                "data": ["unit roster"], "oop": ["unit role"],
                "error": ["breach alert"], "general": ["command post"],
            },
            "domain_lexicon": {
                "entities": ["unit", "officer"], "actions": ["dispatch", "patrol"],
                "states": ["ready", "secure"], "containers": ["roster", "locker"],
                "signals": ["radio", "alert"], "failures": ["breach", "jam"],
                "results": ["clearance", "rescue"],
            },
            "tone": "direct", "output_language": "en",
        }
    )
    dictionary = TaxonomyThemeDictionaryGenerator(_StubProvider([profile])).generate_profile_seeded(
        "I work with emergency dispatch and want short meaningful Python words",
        languages=("python",),
        concepts=concepts,
    )
    cues = {
        "bytearray": "mutable", "bytes": "packet", "callable": "ready",
        "chr": "glyph", "compile": "build", "complex": "imaginary",
    }
    rationale_cues = {
        "bytearray": "mutable sequence", "bytes": "immutable packet",
        "callable": "can be called", "chr": "unicode number",
        "compile": "source text", "complex": "imaginary parts",
    }
    for name, cue in cues.items():
        token = dictionary.mappings[f"py_fn_{name}"]
        assert len(token) <= 20, token
        assert len(token.split("_")) <= 2, token
        assert cue in token.split("_"), token
        assert rationale_cues[name] in dictionary.rationale[f"py_fn_{name}"].casefold()
    stems = {dictionary.mappings[f"py_fn_{name}"].split("_")[0] for name in names}
    assert len(stems) >= 4


def test_profile_seeded_routes_compact_lexicon_by_python_concept_family():
    concepts = [
        _concept("if", kind="keyword", category="keywords", ids=("py_kw_if",)),
        _concept("for", kind="keyword", category="keywords", ids=("py_kw_for",)),
        _concept("def", kind="keyword", category="keywords", ids=("py_kw_def",)),
        _concept("print", kind="builtin", category="builtins", ids=("py_fn_print",)),
        _concept("list", kind="builtin", category="builtins", ids=("py_fn_list",)),
        _concept("try", kind="keyword", category="keywords", ids=("py_kw_try",)),
    ]
    profile = json.dumps(
        {
            "clean_theme": "Urban Emergency Response",
            "learner_summary": "The learner thinks through coordinated emergency work.",
            "primary_world": "Urban Emergency Response",
            "motifs": ["unit", "dispatch", "ready", "roster", "alert", "breach"],
            "family_motifs": {
                "condition": ["safety check"],
                "iteration": ["patrol route"],
                "function": ["response plan"],
                "output": ["radio call"],
                "data": ["unit roster"],
                "oop": ["team blueprint"],
                "error": ["failed entry"],
                "general": ["command post"],
            },
            "domain_lexicon": {
                "entities": ["unit", "officer"],
                "actions": ["dispatch", "patrol"],
                "states": ["ready", "contained"],
                "containers": ["roster", "locker"],
                "signals": ["alert", "radio"],
                "failures": ["breach", "timeout"],
                "results": ["clearance", "rescue"],
            },
            "tone": "calm and precise",
            "output_language": "en",
        }
    )
    provider = _StubProvider([profile])

    dictionary = TaxonomyThemeDictionaryGenerator(provider).generate_profile_seeded(
        "I coordinate emergency teams and long Python names distract me",
        languages=("python",),
        concepts=concepts,
    )

    assert dictionary.mappings["py_kw_if"] in {"ready", "contained", "unit", "officer"}
    assert dictionary.mappings["py_kw_for"] in {"dispatch", "patrol", "unit", "officer"}
    assert dictionary.mappings["py_kw_def"] in {"dispatch", "patrol", "clearance", "rescue"}
    assert dictionary.mappings["py_fn_print"] in {"alert", "radio", "clearance", "rescue"}
    assert dictionary.mappings["py_fn_list"] in {"roster", "locker", "unit", "officer"}
    assert dictionary.mappings["py_kw_try"] in {"breach", "timeout", "ready", "contained"}
    assert all(len(token.split("_")) <= 2 for token in dictionary.mappings.values())


def test_profile_seeded_repairs_generic_long_elif_for_cs2():
    concepts = [
        _concept("if", kind="keyword", category="keywords", ids=("py_kw_if",)),
        _concept("elif", kind="keyword", category="keywords", ids=("py_kw_elif",)),
        _concept("else", kind="keyword", category="keywords", ids=("py_kw_else",)),
    ]
    profile = json.dumps(
        {
            "clean_theme": "Counter-Strike 2",
            "learner_summary": "The learner likes CS2 and struggles with branches.",
            "primary_world": "Counter-Strike 2",
            "motifs": ["clutch check", "site rotation", "team callout"],
            "learning_pain_points": ["if", "elif", "else"],
            "concept_preferences": {"condition": "clutch check"},
            "tone": "tactical",
            "output_language": "en",
        }
    )
    provider = _StubProvider(
        [
            profile,
            json.dumps(
                {
                    "mappings": {
                        "if": "clutch_check",
                        "elif": "clutch_or_second_trigger",
                        "else": "save_round",
                    },
                    "rationale": {
                        "elif": "bad generic trigger phrase",
                    },
                }
            ),
        ]
    )
    generator = TaxonomyThemeDictionaryGenerator(provider)

    dictionary = generator.generate_profile_seeded(
        "I love Counter-Strike 2",
        languages=("python",),
        concepts=concepts,
    )

    # Trusted-LLM contract: tokens derive from the profile, the flagship "if"
    # reserves the family's strongest motif, and the siblings each get their
    # own distinct motif — never a generic "trigger" suffix combo.
    mappings = dictionary.mappings
    assert mappings["py_kw_if"] == "clutch_check"
    assert len({mappings["py_kw_if"], mappings["py_kw_elif"], mappings["py_kw_else"]}) == 3
    for key in ("py_kw_if", "py_kw_elif", "py_kw_else"):
        assert "trigger" not in mappings[key]
        assert len(mappings[key].split("_")) <= 3
