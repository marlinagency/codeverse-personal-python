from __future__ import annotations

import json

import pytest

from codeverse_core.theme_mapping.taxonomy_prompts import (
    MappableConcept,
    ThemeProfile,
    build_category_mapping_messages,
    build_theme_profile_messages,
    build_compact_theme_profile_messages,
    chunk_mappable,
    extract_mappable,
    parse_category_mapping_output,
    parse_theme_profile_output,
)


def _mc(name, kind="method", lang="python", ids=None, hint="does a thing"):
    return MappableConcept(
        canonical_name=name,
        kind=kind,
        language=lang,
        concept_ids=tuple(ids or (f"py_str_{name}",)),
        hint=hint,
    )


_PROFILE = ThemeProfile(
    theme="Valorant",
    motifs=("ajan", "spike", "site", "raund"),
    tone="taktiksel",
    output_language="tr",
)


# ------------------------------------------------------------- extraction


def test_extract_mappable_python_covers_methods_builtins_keywords():
    mappable, skipped = extract_mappable("python")
    names = {m.canonical_name for m in mappable}
    assert {"upper", "split", "append", "print", "len", "for", "while"} <= names
    assert len(mappable) > 150
    assert skipped  # topic pages are intentionally excluded


def test_extract_mappable_sql_groups_dialect_aliases():
    mappable, _ = extract_mappable("sql")
    by_name = {m.canonical_name: m for m in mappable}
    assert "left_join" in by_name
    # UPPER exists on multiple dialect pages -> one name, many concept_ids
    upper = by_name["upper"]
    assert len(upper.concept_ids) >= 2


def test_extracted_names_are_identifier_safe():
    for lang in ("python", "sql"):
        mappable, _ = extract_mappable(lang)
        for m in mappable:
            assert m.canonical_name.replace("_", "a").isalnum(), m.canonical_name
            assert not m.canonical_name[0].isdigit()


# --------------------------------------------------------------- chunking


def test_chunk_mappable_sizes_and_kind_grouping():
    items = [_mc(f"m{i}") for i in range(50)] + [
        _mc(f"k{i}", kind="keyword") for i in range(10)
    ]
    chunks = chunk_mappable(items, chunk_size=40)
    assert [len(c) for c in chunks] == [40, 20]
    # kinds are contiguous: keywords sort before methods alphabetically
    assert all(m.kind == "keyword" for m in chunks[0][:10])


def test_chunk_mappable_deterministic():
    items = [_mc(n) for n in ("zeta", "alpha", "mid")]
    a = chunk_mappable(items, chunk_size=2)
    b = chunk_mappable(list(reversed(items)), chunk_size=2)
    assert [[m.canonical_name for m in c] for c in a] == [
        [m.canonical_name for m in c] for c in b
    ]


# ------------------------------------------------------ profile prompts


def test_theme_profile_messages_shape():
    msgs = build_theme_profile_messages("uzayda karadelikleri seven biri", "tr")
    assert msgs[0]["role"] == "system"
    assert "motifs" in msgs[0]["content"]
    assert msgs[-1]["content"].startswith("Theme: uzayda")
    assert "tr" in msgs[-1]["content"]


def test_theme_profile_messages_appends_clarifying_answers_after_theme_line():
    msgs = build_theme_profile_messages(
        "witcher",
        "en",
        clarifying_answers={"Which role?": "Monster hunter"},
    )
    body = msgs[-1]["content"]
    # "Theme: witcher" must stay first — later generic-theme-label logic and
    # existing tests key off startswith("Theme: ") for the theme itself.
    assert body.startswith("Theme: witcher")
    theme_index = body.index("Theme: witcher")
    qa_index = body.index("Additional details from the user:")
    assert qa_index > theme_index
    assert "Which role?: Monster hunter" in body


def test_compact_theme_profile_messages_are_small_and_skip_few_shots():
    msgs = build_compact_theme_profile_messages(
        "chess",
        "en",
        clarifying_answers={"Style?": "strategic"},
    )

    assert [message["role"] for message in msgs] == ["system", "user"]
    assert "exactly 6" in msgs[0]["content"]
    assert "Theme: chess" in msgs[1]["content"]
    assert "Style?: strategic" in msgs[1]["content"]
    assert sum(len(message["content"]) for message in msgs) < 1000


def test_parse_theme_profile_output_happy_path():
    raw = json.dumps(
        {"motifs": ["karadelik", "olay ufku"], "tone": "kozmik", "output_language": "tr"}
    )
    profile = parse_theme_profile_output(raw, "uzay")
    assert profile.motifs == ("karadelik", "olay ufku")
    assert profile.tone == "kozmik"
    assert profile.output_language == "tr"


def test_parse_theme_profile_output_supports_personal_python_brain_fields():
    raw = json.dumps(
        {
            "clean_theme": "Counter-Strike 2",
            "learner_summary": "The learner loves CS2 and struggles with loops.",
            "primary_world": "Counter-Strike 2",
            "motifs": ["clutch", "site rotation", "team callout"],
            "learning_pain_points": ["for", "function"],
            "concept_preferences": {"loop": "site rotation", "output": "team callout"},
            "family_motifs": {
                "condition": ["clutch check"],
                "iteration": ["site rotation"],
                "function": ["utility lineup"],
                "output": ["team callout"],
                "data": ["loadout card"],
                "oop": ["agent blueprint"],
                "error": ["missed smoke"],
            },
            "tone": "tactical and concise",
        }
    )

    profile = parse_theme_profile_output(
        raw,
        "CS2 seviyorum ve Python'da for/function kafami karistiriyor",
    )

    assert profile.clean_theme == "Counter-Strike 2"
    assert profile.primary_world == "Counter-Strike 2"
    assert profile.output_language == "en"
    assert profile.learning_pain_points == ("for", "function")
    assert profile.concept_preferences["loop"] == "site rotation"
    assert profile.family_motifs["iteration"] == ("site rotation",)
    assert profile.family_motifs["output"] == ("team callout",)


def test_parse_theme_profile_output_normalizes_family_motif_aliases():
    raw = json.dumps(
        {
            "motifs": ["sonar ping", "dive route"],
            "tone": "calm",
            "family_motifs": {
                "loops": ["dive route"],
                "collections": ["logbook"],
                "exceptions": ["pressure leak"],
                "class": ["vessel blueprint"],
            },
        }
    )

    profile = parse_theme_profile_output(raw, "deep sea explorer")

    assert profile.family_motifs["iteration"] == ("dive route",)
    assert profile.family_motifs["data"] == ("logbook",)
    assert profile.family_motifs["error"] == ("pressure leak",)
    assert profile.family_motifs["oop"] == ("vessel blueprint",)


def test_parse_theme_profile_output_normalizes_compact_domain_lexicon():
    raw = json.dumps(
        {
            "motifs": ["dispatch", "patrol"],
            "tone": "direct",
            "domain_lexicon": {
                "entities": ["officer", "Officer", "patrol unit", "a phrase that is much too long to be useful"],
                "actions": ["dispatch", "secure", "clear"],
                "states": ["ready", "contained"],
                "unknown_bucket": ["ignored"],
            },
        }
    )

    profile = parse_theme_profile_output(raw, "American SWAT operations")

    assert profile.domain_lexicon["entities"] == ("officer", "patrol unit")
    assert profile.domain_lexicon["actions"] == ("dispatch", "secure", "clear")
    assert profile.domain_lexicon["states"] == ("ready", "contained")
    assert "unknown_bucket" not in profile.domain_lexicon


def test_parse_theme_profile_output_tolerates_fences_and_prose():
    raw = 'Here you go:\n```json\n{"motifs": ["a"], "tone": "t", "output_language": "en"}\n```'
    profile = parse_theme_profile_output(raw, "x")
    assert profile.motifs == ("a",)


def test_parse_theme_profile_output_rejects_missing_motifs():
    with pytest.raises(ValueError, match="motifs"):
        parse_theme_profile_output('{"tone": "t"}', "x")


# -------------------------------------------------------- batch prompts


def test_batch_messages_include_profile_forbidden_and_constructs():
    batch = [_mc("upper", hint="converts to upper case"), _mc("lower")]
    msgs = build_category_mapping_messages(_PROFILE, batch, ["yetenek", "spike_tasi"])
    body = msgs[-1]["content"]
    assert "Theme: Valorant" in body
    assert "yetenek, spike_tasi" in body
    assert "- upper: converts to upper case" in body
    assert "kind=method" in body


def test_batch_messages_carry_correction_feedback():
    msgs = build_category_mapping_messages(
        _PROFILE, [_mc("upper")], [], correction_feedback="- duplicate token 'x'"
    )
    assert "duplicate token 'x'" in msgs[-1]["content"]


def test_batch_messages_reject_empty_batch():
    with pytest.raises(ValueError, match="kavram grubu"):
        build_category_mapping_messages(_PROFILE, [], [])


def test_parse_batch_output_happy_path():
    batch = [_mc("upper"), _mc("lower")]
    raw = json.dumps(
        {
            "mappings": {"upper": "sesi_yukselt", "lower": "sessize_al"},
            "rationale": {"upper": "bagirir"},
        }
    )
    result = parse_category_mapping_output(raw, batch)
    assert result.mappings == {"upper": "sesi_yukselt", "lower": "sessize_al"}
    assert result.rationale["upper"] == "bagirir"


def test_parse_batch_output_missing_name_raises():
    batch = [_mc("upper"), _mc("lower")]
    raw = json.dumps({"mappings": {"upper": "x"}})
    with pytest.raises(ValueError, match="eksik"):
        parse_category_mapping_output(raw, batch)


def test_parse_batch_output_ignores_extra_names():
    batch = [_mc("upper")]
    raw = json.dumps({"mappings": {"upper": "x", "hallucinated": "y"}})
    result = parse_category_mapping_output(raw, batch)
    assert set(result.mappings) == {"upper"}
