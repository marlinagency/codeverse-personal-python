"""Bridges the taxonomy prompt templates (Adım 6) to a real LLM call
(Adım 8) — the "connect the templates to the real API" half of the plan's
Adım 8. The other half (pinning ``FireworksProvider`` to a working model)
lives in ``providers/fireworks.py``.

This module owns only the retry-on-validation-failure loop for a SINGLE
theme profile call or a SINGLE concept batch call. Running every batch for
a full taxonomy dictionary, accumulating the forbidden-token list across
batches, and fanning results out across aliased ``concept_ids`` is the
orchestrator's job (Adım 9) — it composes these two functions in a loop.

Any provider with a public ``chat(messages, *, temperature, max_tokens)``
method works here (``OpenAICompatibleProvider``, ``FireworksProvider``,
``AnthropicProvider``). ``FakeProvider`` has no such method by design (it
never makes network calls) — taxonomy-scale generation always needs a real
model, so it is intentionally not usable here.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Protocol

from codeverse_core.theme_mapping.taxonomy_prompts import (
    BatchMappingResult,
    MappableConcept,
    ThemeProfile,
    build_category_mapping_messages,
    build_compact_theme_profile_messages,
    build_theme_profile_messages,
    parse_category_mapping_output,
    parse_theme_profile_output,
)
from codeverse_core.theme_mapping.theme_families import (
    detect_domain,
    domain_family_motifs,
    domain_label,
)

logger = logging.getLogger(__name__)


class ChatCapableProvider(Protocol):
    def chat(
        self, messages: list[dict[str, str]], *, temperature: float, max_tokens: int
    ) -> str: ...

    @property
    def provider_name(self) -> str: ...


class TaxonomyGenerationError(Exception):
    """A theme-profile or batch-mapping call kept failing validation."""


def generate_theme_profile(
    provider: ChatCapableProvider,
    theme: str,
    output_language: str | None = None,
    max_attempts: int = 3,
    fallback_on_failure: bool = False,
    clarifying_answers: dict[str, str] | None = None,
    compact_prompt: bool = False,
) -> ThemeProfile:
    """Phase A: distill a free-text theme into a reusable ThemeProfile.

    Retries on parse/validation failure (malformed JSON, missing 'motifs')
    since these are model slip-ups, not caller errors — no corrective
    feedback loop is needed here (unlike batch mapping) because there is
    nothing to correct against; a plain retry is enough in practice.

    ``clarifying_answers`` (question -> chosen option label) comes from the
    optional onboarding wizard (``clarifying_questions.py``) and is folded
    into the same trusted LLM call as extra grounding context — it does not
    introduce a second mechanism, it just strengthens this one prompt.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        message_builder = (
            build_compact_theme_profile_messages
            if compact_prompt
            else build_theme_profile_messages
        )
        messages = message_builder(theme, output_language, clarifying_answers)
        try:
            # 2048, not 800: reasoning models (e.g. gpt-oss-120b) spend part
            # of the budget on hidden reasoning_content before the visible
            # answer; 800 was getting cut off mid-reasoning (finish_reason=
            # length, empty content) AND sat below the >1000 threshold that
            # turns on forced JSON mode — both made every real call fail and
            # silently fall back to the curated tables instead of actually
            # analyzing the user's text.
            raw = provider.chat(messages, temperature=0.7, max_tokens=2048)
            return parse_theme_profile_output(raw, theme)
        except Exception as exc:  # noqa: BLE001 - provider failures can use fallback
            last_error = exc
            logger.warning(
                "tema profili denemesi %d/%d başarısız (%s): %s",
                attempt,
                max_attempts,
                provider.provider_name,
                exc,
            )

    if fallback_on_failure:
        logger.warning(
            "tema profili LLM ile uretilemedi; deterministic fallback kullaniliyor (%s)",
            provider.provider_name,
        )
        return _fallback_theme_profile(theme, output_language, str(last_error))

    raise TaxonomyGenerationError(
        f"'{theme}' için tema profili {max_attempts} denemede üretilemedi: {last_error}"
    )


def _fallback_theme_profile(
    theme: str,
    output_language: str | None,
    reason: str,
) -> ThemeProfile:
    label, family_motifs = _fallback_theme_assets(theme)
    motifs = tuple(
        motif
        for family in (
            "condition", "iteration", "function", "output",
            "data", "oop", "error", "general",
        )
        for motif in family_motifs.get(family, ())
    )
    return ThemeProfile(
        theme=theme,
        clean_theme=label,
        learner_summary=(
            f"The learner connects Python ideas to {label} and wants short, "
            "memorable syntax."
        ),
        primary_world=label,
        motifs=motifs or ("personal cue", "learning path", "memory signal"),
        tone="clear and personal",
        output_language=output_language or "en",
        learning_pain_points=_fallback_pain_points(theme),
        concept_preferences={
            "condition": family_motifs.get("condition", ("decision check",))[0],
            "loop": family_motifs.get("iteration", ("learning route",))[0],
            "function": family_motifs.get("function", ("reusable action",))[0],
            "output": family_motifs.get("output", ("clear signal",))[0],
            "data": family_motifs.get("data", ("memory card",))[0],
        },
        family_motifs=family_motifs,
        domain_lexicon=_fallback_domain_lexicon(family_motifs),
        domain_lexicon_source="fallback",
        raw_model_output=f'{{"fallback": true, "reason": {reason!r}}}',
        source="fallback",
    )


def _fallback_domain_lexicon(
    family_motifs: dict[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    sources = {
        "entities": ("general", "oop"),
        "actions": ("iteration", "function"),
        "states": ("condition",),
        "containers": ("data",),
        "signals": ("output",),
        "failures": ("error",),
        "results": ("function", "general"),
    }
    return {
        category: tuple(
            dict.fromkeys(
                motif
                for family in families
                for motif in family_motifs.get(family, ())
            )
        )[:8]
        for category, families in sources.items()
    }


def _fallback_theme_assets(theme: str) -> tuple[str, dict[str, tuple[str, ...]]]:
    folded = _ascii_fold(theme)
    domains: tuple[tuple[tuple[str, ...], str, dict[str, tuple[str, ...]]], ...] = (
        (
            ("counter strike", "counter-strike", "cs2", "clutch", "dust 2"),
            "Counter-Strike 2",
            {
                "condition": ("clutch check", "round state"),
                "iteration": ("site rotation", "map route"),
                "function": ("utility lineup", "round result"),
                "output": ("team callout", "mic check"),
                "data": ("buy menu", "loadout card"),
                "oop": ("agent blueprint", "squad role"),
                "error": ("failed clutch", "missed smoke"),
                "general": ("crosshair", "defuse kit"),
            },
        ),
        (
            ("gta", "san andreas", "grand theft", "grove street"),
            "GTA San Andreas",
            {
                "condition": ("wanted check", "heat shift"),
                "iteration": ("street route", "grove route"),
                "function": ("mission plan", "mission payout"),
                "output": ("radio callout", "phone contact"),
                "data": ("garage stash", "crew profile"),
                "oop": ("crew blueprint", "gang lineage"),
                "error": ("busted escape", "wanted escape"),
                "general": ("safehouse", "crew ride"),
            },
        ),
        (
            ("minecraft", "redstone", "crafting", "minecart"),
            "Minecraft",
            {
                "condition": ("redstone check", "biome shift"),
                "iteration": ("minecart route", "chunk path"),
                "function": ("craft recipe", "crafted item"),
                "output": ("beacon signal", "chat command"),
                "data": ("inventory slots", "chest record"),
                "oop": ("mob blueprint", "entity lineage"),
                "error": ("creeper blast", "tool break"),
                "general": ("spawn point", "diamond pickaxe"),
            },
        ),
        (
            ("formula 1", "formula one", "f1", "racing", "pit stop"),
            "Formula 1",
            {
                "condition": ("strategy check", "weather shift"),
                "iteration": ("race route", "lap cycle"),
                "function": ("pit plan", "podium result"),
                "output": ("radio message", "pit wall"),
                "data": ("telemetry map", "tyre set"),
                "oop": ("car blueprint", "team lineage"),
                "error": ("track limits", "engine fault"),
                "general": ("sector time", "garage setup"),
            },
        ),
        (
            ("harry potter", "hogwarts", "wizard", "spell", "quidditch"),
            "Harry Potter",
            {
                "condition": ("spell check", "house rule"),
                "iteration": ("hall patrol", "marauder map"),
                "function": ("spell cast", "potion recipe"),
                "output": ("owl message", "howler note"),
                "data": ("spellbook", "house points"),
                "oop": ("wizard lineage", "wand blueprint"),
                "error": ("backfired spell", "broken wand"),
                "general": ("hogwarts hall", "charm lesson"),
            },
        ),
        (
            ("philosophy", "philosopher", "philosophers", "socrates", "plato"),
            "Philosophers",
            {
                "condition": ("logic test", "premise check"),
                "iteration": ("academy walk", "dialogue path"),
                "function": ("argument method", "thesis result"),
                "output": ("dialogue voice", "public lecture"),
                "data": ("scroll archive", "idea catalog"),
                "oop": ("school lineage", "thinker type"),
                "error": ("flawed proof", "false premise"),
                "general": ("socratic question", "library shelf"),
            },
        ),
        (
            ("cooking", "cook", "baking", "chef", "kitchen", "recipe"),
            "Cooking",
            {
                "condition": ("taste check", "heat level"),
                "iteration": ("prep line", "stir cycle"),
                "function": ("recipe method", "prep plan"),
                "output": ("order call", "kitchen bell"),
                "data": ("recipe card", "ingredient list"),
                "oop": ("dish blueprint", "menu type"),
                "error": ("burnt pan", "missing spice"),
                "general": ("kitchen station", "serving plate"),
            },
        ),
        (
            ("aviation", "airplane", "aircraft", "pilot", "flight", "ucak"),
            "Aviation",
            {
                "condition": ("flight check", "weather window"),
                "iteration": ("flight path", "runway taxi"),
                "function": ("control plan", "landing result"),
                "output": ("tower call", "radio check"),
                "data": ("flight log", "instrument panel"),
                "oop": ("airframe blueprint", "crew role"),
                "error": ("stall warning", "engine fault"),
                "general": ("hangar station", "flight deck"),
            },
        ),
        (
            ("space", "astronomy", "planet", "galaxy", "nasa", "black hole"),
            "Space Exploration",
            {
                "condition": ("orbit check", "gravity shift"),
                "iteration": ("orbit path", "star route"),
                "function": ("launch plan", "mission result"),
                "output": ("radio ping", "signal beam"),
                "data": ("star chart", "planet record"),
                "oop": ("ship blueprint", "planet type"),
                "error": ("signal loss", "hull breach"),
                "general": ("mission control", "deep space"),
            },
        ),
        (
            ("witcher", "geralt", "rivia", "yennefer", "kaer morhen"),
            "The Witcher 3",
            {
                "condition": ("monster check", "contract clause"),
                "iteration": ("monster trail", "quest path"),
                "function": ("sign cast", "witcher contract"),
                "output": ("quest notice", "tavern rumor"),
                "data": ("bestiary", "alchemy kit"),
                "oop": ("school lineage", "gear blueprint"),
                "error": ("failed sign", "toxic potion"),
                "general": ("silver sword", "witcher sense"),
            },
        ),
        (
            ("game", "gaming", "counter strike", "cs2", "gta", "minecraft"),
            "Games",
            {
                "condition": ("match check", "mission state"),
                "iteration": ("map route", "next checkpoint"),
                "function": ("ability plan", "quest result"),
                "output": ("team callout", "radio message"),
                "data": ("inventory slot", "loadout card"),
                "oop": ("player blueprint", "role class"),
                "error": ("failed round", "lost save"),
                "general": ("spawn point", "game plan"),
            },
        ),
    )
    for needles, label, motifs in domains:
        if any(needle in folded for needle in needles):
            return label, motifs

    # broad category layer (theme_families.py): "one piece izliyorum" hits
    # the anime table, "basketbol antrenmani" hits sports, ... — so even the
    # LLM-failure path produces theme-bound motifs instead of generic cues.
    domain_key = detect_domain(theme)
    if domain_key is not None:
        return domain_label(domain_key), dict(domain_family_motifs(domain_key))

    base = _fallback_base_word(theme)
    title = base.replace("_", " ").title() or "Personal Theme"
    return title, {
        "condition": (f"{base} check", "decision gate"),
        "iteration": (f"{base} route", "next step"),
        "function": (f"{base} method", "result plan"),
        "output": (f"{base} signal", "clear message"),
        "data": (f"{base} record", "memory list"),
        "oop": (f"{base} blueprint", "role type"),
        "error": (f"{base} fault", "recovery step"),
        "general": (f"{base} cue", "learning map"),
    }


def _fallback_pain_points(theme: str) -> tuple[str, ...]:
    folded = _ascii_fold(theme)
    concepts = (
        "if", "elif", "else", "for", "while", "function", "def",
        "return", "class", "dict", "list", "error", "try", "except",
    )
    return tuple(concept for concept in concepts if concept in folded)


def _fallback_base_word(theme: str) -> str:
    words = [
        word
        for word in re.findall(r"[a-z][a-z0-9]*", _ascii_fold(theme))
        if word not in _FALLBACK_STOP_WORDS
    ]
    return "_".join(words[:2]) if words else "personal"


def _ascii_fold(text: str) -> str:
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
    )


_FALLBACK_STOP_WORDS = frozenset(
    {
        "i", "me", "my", "and", "or", "but", "the", "a", "an", "to", "of",
        "with", "for", "in", "on", "love", "like", "seviyorum", "python",
        "learn", "learning", "confuse", "confusing", "karisik", "geliyor",
        "evren", "evreni", "evreniyle", "olustur", "olusturmak", "olusturuyor",
        "ben", "bana", "bir", "cok", "ile", "ilgili", "tema", "dunya",
        "dunyasi", "evreninde", "seviyorum", "yap", "yapmak", "kur",
    }
)


def generate_batch_mapping(
    provider: ChatCapableProvider,
    profile: ThemeProfile,
    batch: list[MappableConcept],
    forbidden_tokens: list[str],
    max_attempts: int = 3,
) -> BatchMappingResult:
    """Phase B: map one concept batch to themed tokens.

    On validation failure (missing canonical name in the response), the
    parser's error message is fed back to the model as corrective feedback
    on the next attempt — the same retry-with-feedback pattern used by the
    live 31-concept ``ThemeDictionaryGenerator``.
    """
    feedback: str | None = None
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        messages = build_category_mapping_messages(
            profile, batch, forbidden_tokens, correction_feedback=feedback
        )
        raw = provider.chat(messages, temperature=0.8, max_tokens=2048)
        try:
            return parse_category_mapping_output(raw, batch)
        except ValueError as exc:
            last_error = exc
            feedback = str(exc)
            logger.warning(
                "batch eşleme denemesi %d/%d başarısız (%s, kind=%s): %s",
                attempt,
                max_attempts,
                provider.provider_name,
                batch[0].kind if batch else "?",
                exc,
            )

    raise TaxonomyGenerationError(
        f"batch eşleme {max_attempts} denemede başarısız oldu: {last_error}"
    )
