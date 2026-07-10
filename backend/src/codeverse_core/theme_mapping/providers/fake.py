"""Deterministic, network-free provider for tests and offline development.

The fake provider is intentionally better than a random mock: local demos should
still show the Personal Python idea when no external LLM key is configured.
"""

from __future__ import annotations

import json
import re
import unicodedata

from codeverse_core.concepts import UniversalConcept
from codeverse_core.theme_mapping.llm_provider import (
    LLMProvider,
    ThemeMappingRequest,
    ThemeMappingResponse,
)


def _slug(theme: str) -> str:
    normalized = unicodedata.normalize("NFKD", theme)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    words = re.findall(r"[a-z][a-z0-9]*", ascii_text)
    return words[0] if words else "theme"


def _theme_key(theme: str) -> str:
    folded = theme.casefold()
    ascii_folded = (
        unicodedata.normalize("NFKD", folded)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    if "counter" in ascii_folded or "cs2" in ascii_folded or "strike" in ascii_folded:
        return "cs2"
    if "gta" in ascii_folded or "san andreas" in ascii_folded or "grand theft" in ascii_folded:
        return "gta"
    if "minecraft" in ascii_folded:
        return "minecraft"
    if "formula" in ascii_folded or "f1" in ascii_folded:
        return "formula1"
    if "harry" in ascii_folded or "hogwarts" in ascii_folded:
        return "harry_potter"
    if "witcher" in ascii_folded:
        return "witcher"
    if "philosopher" in ascii_folded or "philosophy" in ascii_folded:
        return "philosophers"
    return "generic"


def _profile_for_theme(theme: str) -> dict[str, object]:
    key = _theme_key(theme)
    profiles: dict[str, dict[str, object]] = {
        "cs2": {
            "clean_theme": "Counter-Strike 2",
            "primary_world": "Counter-Strike 2",
            "motifs": [
                "clutch check", "site rotation", "team callout", "buy round",
                "crosshair", "smoke lineup", "defuse kit", "entry frag",
            ],
            "concept_preferences": {
                "condition": "clutch check",
                "loop": "site rotation",
                "function": "utility lineup",
                "output": "team callout",
            },
            "tone": "tactical and concise",
        },
        "gta": {
            "clean_theme": "GTA San Andreas",
            "primary_world": "GTA San Andreas",
            "motifs": [
                "Grove Street", "street route", "mission payout", "radio callout",
                "safehouse", "wanted level", "garage", "crew ride",
            ],
            "concept_preferences": {
                "condition": "wanted level",
                "loop": "street route",
                "function": "mission plan",
                "output": "radio callout",
            },
            "tone": "street-level and clear",
        },
        "minecraft": {
            "clean_theme": "Minecraft",
            "primary_world": "Minecraft",
            "motifs": [
                "crafting table", "minecart route", "redstone signal", "inventory",
                "biome path", "diamond pickaxe", "spawn point", "chest",
            ],
            "concept_preferences": {
                "condition": "redstone signal",
                "loop": "minecart route",
                "function": "crafting recipe",
                "output": "beacon signal",
            },
            "tone": "blocky and practical",
        },
        "formula1": {
            "clean_theme": "Formula 1",
            "primary_world": "Formula 1",
            "motifs": [
                "race strategy", "pit stop", "lap route", "radio message",
                "sector time", "DRS window", "podium result", "garage setup",
            ],
            "concept_preferences": {
                "condition": "race strategy",
                "loop": "lap route",
                "function": "pit plan",
                "output": "radio message",
            },
            "tone": "fast and analytical",
        },
        "harry_potter": {
            "clean_theme": "Harry Potter",
            "primary_world": "Harry Potter",
            "motifs": [
                "spell cast", "Hogwarts hall", "owl message", "potion recipe",
                "wand spark", "house points", "marauder map", "charm lesson",
            ],
            "concept_preferences": {
                "condition": "spell check",
                "loop": "hall patrol",
                "function": "spell cast",
                "output": "owl message",
            },
            "tone": "magical and clear",
        },
        "witcher": {
            "clean_theme": "The Witcher 3",
            "primary_world": "The Witcher 3",
            "motifs": [
                "witcher contract", "monster trail", "sign cast", "alchemy kit",
                "silver sword", "gwent round", "quest reward", "bestiarum",
            ],
            "concept_preferences": {
                "condition": "monster check",
                "loop": "monster trail",
                "function": "sign cast",
                "output": "quest notice",
            },
            "tone": "dark fantasy and clear",
        },
        "philosophers": {
            "clean_theme": "Philosophers",
            "primary_world": "Philosophers",
            "motifs": [
                "logic test", "academy walk", "dialogue voice", "scroll archive",
                "argument method", "thesis result", "school lineage", "flawed proof",
            ],
            "concept_preferences": {
                "condition": "logic test",
                "loop": "academy walk",
                "function": "argument method",
                "output": "dialogue voice",
                "data": "scroll archive",
            },
            "tone": "clear and thoughtful",
        },
    }
    profile = profiles.get(key)
    if profile is None:
        label = " ".join(part.capitalize() for part in re.findall(r"[a-z0-9]+", _slug(theme)))
        motif = _slug(theme)
        profile = {
            "clean_theme": label or "Personal Theme",
            "primary_world": label or "Personal Theme",
            "motifs": [
                f"{motif} route", f"{motif} signal", f"{motif} toolkit",
                f"{motif} checkpoint", f"{motif} result",
            ],
            "concept_preferences": {
                "condition": f"{motif} checkpoint",
                "loop": f"{motif} route",
                "function": f"{motif} toolkit",
                "output": f"{motif} signal",
            },
            "tone": "personal and concise",
        }
    return {
        "clean_theme": profile["clean_theme"],
        "learner_summary": (
            f"The learner connects Python ideas to {profile['clean_theme']} and wants "
            "short, memorable syntax."
        ),
        "primary_world": profile["primary_world"],
        "motifs": profile["motifs"],
        "learning_pain_points": ["conditionals", "loops", "functions"],
        "concept_preferences": profile["concept_preferences"],
        "family_motifs": _family_motifs_for_profile(profile),
        "tone": profile["tone"],
        "output_language": "en",
    }


def _profile_value(profile: dict[str, object], key: str) -> str:
    value = profile.get("concept_preferences", {})
    if isinstance(value, dict):
        found = value.get(key)
        if found:
            return str(found)
    motifs = profile.get("motifs", [])
    if isinstance(motifs, list) and motifs:
        return str(motifs[0])
    return "personal cue"


def _profile_motif(profile: dict[str, object], index: int, fallback: str) -> str:
    motifs = profile.get("motifs", [])
    if isinstance(motifs, list) and len(motifs) > index:
        return str(motifs[index])
    return fallback


def _family_motifs_for_profile(profile: dict[str, object]) -> dict[str, list[str]]:
    condition = _profile_value(profile, "condition")
    iteration = _profile_value(profile, "loop")
    function = _profile_value(profile, "function")
    output = _profile_value(profile, "output")
    data = _profile_value(profile, "data")
    return {
        "condition": [condition, _profile_motif(profile, 4, condition)],
        "iteration": [iteration, _profile_motif(profile, 1, iteration)],
        "function": [function, _profile_motif(profile, 2, function)],
        "output": [output, _profile_motif(profile, 3, output)],
        "data": [data, _profile_motif(profile, 4, data)],
        "oop": [_profile_motif(profile, 6, function), f"{function} blueprint"],
        "error": [_profile_motif(profile, 7, condition), f"failed {condition}"],
        "general": [_profile_motif(profile, 0, condition), _profile_motif(profile, 1, iteration)],
    }


def _critical_tokens(theme: str) -> dict[str, tuple[str, str]]:
    key = _theme_key(theme)
    maps: dict[str, dict[str, str]] = {
        "cs2": {
            "if": "clutch_check", "elif": "backup_angle", "else": "save_round",
            "for": "rotate_sites", "while": "hold_angle", "break": "call_save",
            "continue": "repeek_next", "def": "utility_lineup", "return": "round_result",
            "yield": "drop_flash", "lambda": "quick_strat", "print": "team_callout",
            "input": "mic_check", "range": "round_window", "iter": "site_route",
            "next": "next_angle", "list": "buy_menu", "dict": "loadout_card",
            "class": "agent_blueprint",
        },
        "gta": {
            "if": "wanted_check", "elif": "heat_shift", "else": "safehouse_plan",
            "for": "cruise_blocks", "while": "keep_driving", "break": "ditch_cops",
            "continue": "next_block", "def": "mission_plan", "return": "mission_payout",
            "yield": "side_hustle", "lambda": "quick_job", "print": "radio_callout",
            "input": "phone_contact", "range": "block_range", "iter": "grove_route",
            "next": "next_checkpoint", "list": "garage_list", "dict": "crew_profile",
            "class": "safehouse_blueprint",
        },
        "minecraft": {
            "if": "redstone_check", "elif": "biome_shift", "else": "spawn_fallback",
            "for": "minecart_loop", "while": "keep_mining", "break": "tool_snap",
            "continue": "next_block", "def": "craft_recipe", "return": "crafted_item",
            "yield": "ore_drop", "lambda": "quick_craft", "print": "beacon_signal",
            "input": "chat_command", "range": "chunk_range", "iter": "minecart_route",
            "next": "next_chunk", "list": "inventory_slots", "dict": "chest_record",
            "class": "mob_blueprint",
        },
        "formula1": {
            "if": "strategy_check", "elif": "weather_shift", "else": "box_plan",
            "for": "lap_cycle", "while": "push_lap", "break": "box_now",
            "continue": "next_sector", "def": "pit_plan", "return": "podium_result",
            "yield": "split_time", "lambda": "quick_setup", "print": "radio_message",
            "input": "pit_wall", "range": "lap_window", "iter": "race_route",
            "next": "next_corner", "list": "tyre_set", "dict": "telemetry_map",
            "class": "car_blueprint",
        },
        "philosophers": {
            "if": "logic_test", "elif": "backup_premise", "else": "other_premise",
            "for": "academy_walk", "while": "keep_debating", "break": "drop_argument",
            "continue": "resume_debate", "def": "argument_method", "return": "thesis_result",
            "yield": "shared_idea", "lambda": "quick_thesis", "print": "dialogue_voice",
            "input": "socratic_question", "range": "argument_range", "iter": "dialogue_path",
            "next": "next_argument", "list": "idea_catalog", "dict": "scroll_archive",
            "class": "school_blueprint",
        },
    }
    base = maps.get(key, {})
    return {
        name: (token, f"Uses {token.replace('_', ' ')} to make {name} feel tied to the theme.")
        for name, token in base.items()
    }


class FakeProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "fake"

    def generate_theme_mapping(self, request: ThemeMappingRequest) -> ThemeMappingResponse:
        prefix = _slug(request.theme)
        mappings = {c.key: f"{prefix}_{c.canonical}" for c in request.concepts}
        rationale = {c.key: f"deterministic fake token for {c.key}" for c in request.concepts}
        return ThemeMappingResponse(
            mappings=mappings,
            rationale=rationale,
            raw_model_output=json.dumps({"mappings": mappings}, ensure_ascii=False),
            model="fake",
        )

    def translate_error_message(
        self,
        canonical_message: str,
        theme: str,
        mappings: dict[UniversalConcept, str],
    ) -> str:
        return f"[{_slug(theme)}] {canonical_message}"

    def chat(self, messages: list[dict[str, str]], *, temperature: float, max_tokens: int) -> str:
        system_msg = messages[0]["content"] if messages else ""
        user_msg = next(m["content"] for m in reversed(messages) if m["role"] == "user")

        # Checked first and keyed on the SYSTEM message: the clarifying-
        # questions user message also starts with "Theme:" (like the theme-
        # profile prompt), so dispatching on user_msg alone would silently
        # misroute it into the theme-profile branch below.
        if "multiple-choice clarifying wizard" in system_msg:
            return json.dumps(_fake_clarifying_questions(), ensure_ascii=False)

        if "Theme:" in user_msg and "CONSTRUCTS" not in user_msg:
            theme_line = next(line for line in user_msg.split("\n") if line.startswith("Theme:"))
            theme = theme_line.split("Theme:", maxsplit=1)[1].strip()
            return json.dumps(_profile_for_theme(theme), ensure_ascii=False)

        theme = "personal theme"
        if "THEME PROFILE" in user_msg:
            for line in user_msg.split("\n"):
                if line.startswith("Clean theme:") or line.startswith("Theme:"):
                    theme = line.split(":", maxsplit=1)[1].strip()
                    break

        critical = _critical_tokens(theme)
        fallback_prefix = _slug(theme)
        mappings: dict[str, str] = {}
        rationale: dict[str, str] = {}
        for line in user_msg.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                name = line[2:].split(":", maxsplit=1)[0].strip()
                token, why = critical.get(
                    name,
                    (
                        f"{fallback_prefix}_{name}",
                        f"Uses {fallback_prefix} as a stable personal cue for {name}.",
                    ),
                )
                mappings[name] = token
                rationale[name] = why

        return json.dumps({"mappings": mappings, "rationale": rationale}, ensure_ascii=False)


def _fake_clarifying_questions() -> dict[str, object]:
    """Deterministic, non-theme-aware stand-in for the real clarifying-
    questions call. Only needs to satisfy the parser's shape contract (5-8
    questions, 2-5 options each, label+icon) — theme-aware wording is a real
    LLM's job, not something offline tests depend on."""
    return {
        "questions": [
            {
                "id": f"q{i}",
                "question": f"Sample clarifying question {i}?",
                "options": [
                    {"label": "First option", "icon": "🎯"},
                    {"label": "Second option", "icon": "✨"},
                    {"label": "Third option", "icon": "🔥"},
                ],
            }
            for i in range(1, 8)
        ]
    }
