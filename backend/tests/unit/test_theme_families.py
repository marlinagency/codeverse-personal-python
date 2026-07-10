from __future__ import annotations

import pytest

from codeverse_core.theme_mapping.generator import _concept_family
from codeverse_core.theme_mapping.taxonomy_generator import _fallback_theme_assets
from codeverse_core.theme_mapping.taxonomy_prompts import MappableConcept, extract_mappable
from codeverse_core.theme_mapping.theme_families import (
    CONCEPT_FAMILIES,
    DOMAIN_FAMILY_MOTIFS,
    DOMAIN_KEYWORDS,
    DOMAIN_LABELS,
    detect_domain,
    domain_family_motifs,
    domain_label,
)

# ------------------------------------------------------------ table structure


def test_every_domain_has_all_concept_families():
    for domain, families in DOMAIN_FAMILY_MOTIFS.items():
        missing = set(CONCEPT_FAMILIES) - set(families)
        assert not missing, f"{domain} eksik aile(ler): {missing}"
        for family, motifs in families.items():
            assert motifs, f"{domain}/{family} boş"
            for motif in motifs:
                assert len(motif.split()) <= 2 or "_" in motif, (
                    f"{domain}/{family}: {motif!r} çok uzun"
                )


def test_every_keyword_domain_has_label_and_motifs():
    for key, needles in DOMAIN_KEYWORDS:
        assert key in DOMAIN_LABELS, key
        assert key in DOMAIN_FAMILY_MOTIFS, key
        assert needles


def test_no_duplicate_domain_keys_in_keyword_order():
    keys = [key for key, _ in DOMAIN_KEYWORDS]
    assert len(keys) == len(set(keys))


def test_new_category_motifs_avoid_the_weak_word_blocklist():
    """Regression: 'opening_theme' (anime/output) collided with the quality
    gate's own reserved word 'theme', causing live token validation
    failures (py_fn_ascii -> 'opening_theme_ascii' etc). Any NEW category
    added here must not repeat that mistake — motifs must not contain
    meta/generic words the validator itself reserves."""
    weak_words = {
        "theme", "tone", "epic", "gritty", "dark", "light", "story", "world",
        "game", "final", "quality", "code", "concept", "system", "style",
        "generic", "python", "syntax", "token", "specific",
    }
    new_categories = (
        "games", "movies_series", "anime", "sports", "professions",
        "engineering", "science", "fantasy", "daily_life",
    )
    offenders = []
    for domain in new_categories:
        for family, motifs in DOMAIN_FAMILY_MOTIFS[domain].items():
            for motif in motifs:
                parts = set(motif.replace("_", " ").split())
                if parts & weak_words:
                    offenders.append(f"{domain}/{family}: {motif!r}")
    assert not offenders, offenders


# ------------------------------------------------------------- detection


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("one piece izliyorum surekli", "anime"),
        ("attack on titan hayraniyim", "anime"),
        ("her aksam netflix dizi izlerim", "movies_series"),
        ("I love playing video games on steam", "games"),
        ("esports takibi yapiyorum, fps oynarim", "games"),
        ("basketbol antrenmani yapiyorum", "sports"),
        ("I go to the gym and do fitness workouts", "sports"),
        ("makine muhendisiyim", "engineering"),
        ("fizik deneyleri yapmayi seviyorum", "science"),
        ("dragons and medieval kingdoms fascinate me", "fantasy"),
        ("avukat olarak calisiyorum", "professions"),
        ("sabah kahve rutinim olmadan olmaz", "daily_life"),
    ],
)
def test_new_categories_detected(text, expected):
    assert detect_domain(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # specific domains must win over broad ones
        ("futbol oynuyorum her hafta", "football"),
        ("uzay ve kara delikler", "space"),
        ("pilot olmak istiyorum, flight simulator", "aviation"),
        ("yunan mitolojisi zeus olympus", "mythology"),
        ("gitar caliyorum bir bandim var", "music"),
    ],
)
def test_specific_domains_beat_broad_categories(text, expected):
    assert detect_domain(text) == expected


def test_unknown_text_returns_none():
    assert detect_domain("xylophone-free abstract nothingness qqq") is None


def test_turkish_characters_fold():
    assert detect_domain("uçak kullanmayı öğreniyorum") == "aviation"


def test_domain_label_fallback_titles_unknown_key():
    assert domain_label("some_new_key") == "Some New Key"
    assert domain_family_motifs("nonexistent") == {}


# ----------------------------------------- LLM-failure fallback integration


def test_fallback_assets_use_category_layer_for_anime():
    label, motifs = _fallback_theme_assets("one piece izlemeyi cok seviyorum")
    assert label == "Anime"
    assert motifs["iteration"][0] == "training_arc"


def test_fallback_assets_still_prefer_curated_over_category():
    # "minecraft" is both a curated known theme AND would match "games"
    label, _ = _fallback_theme_assets("minecraft oynuyorum")
    assert label == "Minecraft"


def test_fallback_assets_generic_when_nothing_matches():
    label, motifs = _fallback_theme_assets("qqq zzz abstract")
    assert "general" in motifs  # generic path keeps its extra family


# ------------------------------------------------- concept family deepening


def _mc(name, kind="builtin", category="builtin_functions"):
    return MappableConcept(
        canonical_name=name,
        kind=kind,
        language="python",
        concept_ids=(f"py_x_{name}",),
        hint="",
        category=category,
    )


@pytest.mark.parametrize(
    ("concept", "family"),
    [
        (_mc("upper", kind="method", category="string_methods"), "data"),
        (_mc("strip", kind="method", category="string_methods"), "data"),
        (_mc("add", kind="method", category="set_methods"), "data"),
        (_mc("ValueError", kind="exception", category="exceptions"), "error"),
        (_mc("ZeroDivisionError", kind="exception", category="exceptions"), "error"),
        (_mc("seek", kind="method", category="file_methods"), "error"),
        (_mc("abs"), "data"),
        (_mc("sorted"), "data"),
        (_mc("and", kind="keyword", category="keywords"), "condition"),
        (_mc("is", kind="keyword", category="keywords"), "condition"),
        # explicit sets still take precedence over fallbacks
        (_mc("print"), "output"),
        (_mc("range"), "iteration"),
        (_mc("def", kind="keyword", category="keywords"), "function"),
    ],
)
def test_concept_family_routing(concept, family):
    assert _concept_family(concept) == family


def test_general_family_is_now_rare():
    """The deepening's measurable goal: almost every mappable Python concept
    lands in a real family; 'general' is the exception, not the default."""
    mappable, _ = extract_mappable("python")
    general = [m.canonical_name for m in mappable if _concept_family(m) == "general"]
    ratio = len(general) / len(mappable)
    assert ratio < 0.15, f"general oranı %{ratio * 100:.0f}: {sorted(general)[:20]}"
