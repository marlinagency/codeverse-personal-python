"""Taxonomy-scale theme-mapping prompt architecture (Taksonomi PlanÄ± AdÄ±m 6).

Design (the RAG approach)
=========================

Mapping ~1000 taxonomy concepts in one LLM call is impossible (output limits)
and mapping them in isolated calls destroys thematic coherence. The
architecture therefore has two phases:

**Phase A â€” theme distillation (one call per theme).**
The free-text theme ("Valorant", "uzayda karadelikleri seven biri", ...) is
distilled into a structured :class:`ThemeProfile`: 8-15 motifs (objects,
actions, places, jargon of that world), a tone, and an output language. The
profile â€” not the raw theme â€” is what every later call receives, so category
batches drawn hours apart still share one motif vocabulary. This is the
consistency mechanism.

**Phase B â€” category batch mapping (one call per ~40 concepts).**
Mappable concepts are grouped by category, chunked, and each chunk is sent
with (a) the frozen theme profile, (b) that chunk's concept lines
(canonical name + one-line hint), and (c) the *forbidden token list* â€”
every token produced by earlier chunks, so collisions are prevented at
generation time instead of only being caught by the validator afterwards.

Canonical names, not concept_ids, are the prompt currency: several taxonomy
entries can share one canonical name (``UPPER`` exists on three SQL dialect
pages), and asking the model once per *name* keeps prompts small; the
orchestrator (AdÄ±m 9) fans the returned token back out to every aliased
concept_id via :attr:`MappableConcept.concept_ids`.

Concepts that cannot be reduced to a single canonical identifier (tutorial
topic pages like "Assign Multiple Values") are excluded here â€” they are
documentation/translation-panel material, not themeable tokens.

This module is pure prompt construction + parsing; it performs no I/O and
does not touch the live 31-concept pipeline in ``prompt_templates.py``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from codeverse_core.data.taxonomy_loader import Language, TaxonomyConcept, load_taxonomy
from codeverse_core.theme_mapping.json_extraction import extract_json_object

# --------------------------------------------------------------------------
# mappable-concept extraction
# --------------------------------------------------------------------------

#: how the concept participates in the DSL, drives prompt wording per group
MappableKind = str  # "keyword" | "builtin" | "method" | "exception" | "function"


@dataclass(frozen=True)
class MappableConcept:
    canonical_name: str
    kind: MappableKind
    language: Language
    #: every taxonomy concept_id that shares this canonical name (aliases)
    concept_ids: tuple[str, ...]
    #: one-line hint shown to the model (original wording from AdÄ±m 4)
    hint: str
    #: taxonomy category used by the AdÄ±m 9 orchestrator for category calls
    category: str = ""


_PAREN_RE = re.compile(r"\(\)$")
_LANG_PREFIX_RE = re.compile(r"^(SQL|Python)\s+", re.IGNORECASE)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WORDS_RE = re.compile(r"^[A-Za-z]+$")

_SQL_TOPIC_CATEGORIES = frozenset(
    {
        "query_basics", "filtering", "joins", "aggregation",
        "data_modification", "conditional", "subqueries",
    }
)


def canonical_name_for(concept: TaxonomyConcept) -> str | None:
    """Reduce a concept title to one identifier-safe canonical name.

    ``upper()`` -> ``upper``; ``SQL Left Join`` -> ``left_join``;
    ``ValueError`` -> ``ValueError``. Returns None when no single-token
    reduction exists (multi-word non-SQL titles, symbol titles).
    """
    t = _PAREN_RE.sub("", concept.title.strip())
    t = _LANG_PREFIX_RE.sub("", t).strip()
    if _IDENT_RE.match(t):
        return t.lower() if concept.language == "sql" else t
    words = t.split()
    if (
        concept.language == "sql"
        and 1 < len(words) <= 3
        and all(_WORDS_RE.match(w) for w in words)
    ):
        return "_".join(w.lower() for w in words)
    return None


def _kind_for(concept: TaxonomyConcept) -> MappableKind:
    if concept.language == "python":
        if concept.category == "keywords":
            return "keyword"
        if concept.tier == "builtin":
            return "builtin"
        if concept.tier == "exception":
            return "exception"
        return "method"
    if concept.concept_id.startswith("sql_kw_") or concept.category in _SQL_TOPIC_CATEGORIES:
        return "keyword"
    return "function"


def _is_eligible(concept: TaxonomyConcept) -> bool:
    if concept.language == "python":
        return (
            concept.tier in ("builtin", "method", "exception")
            or concept.category == "keywords"
        )
    return (
        concept.concept_id.startswith("sql_kw_")
        or concept.tier == "library"
        or concept.category in _SQL_TOPIC_CATEGORIES
    )


def extract_mappable(
    language: Language,
) -> tuple[list[MappableConcept], list[TaxonomyConcept]]:
    """(mappable concepts grouped by canonical name, skipped concepts).

    Skipped = topic/tutorial pages with no single-token identity; they are
    intentionally NOT themeable tokens.
    """
    groups: dict[str, list[TaxonomyConcept]] = {}
    skipped: list[TaxonomyConcept] = []

    for concept in load_taxonomy(language):
        if not _is_eligible(concept):
            skipped.append(concept)
            continue
        name = canonical_name_for(concept)
        if name is None:
            skipped.append(concept)
            continue
        groups.setdefault(name, []).append(concept)

    mappable: list[MappableConcept] = []
    for name, members in groups.items():
        primary = members[0]
        hint = primary.description or primary.real_syntax
        mappable.append(
            MappableConcept(
                canonical_name=name,
                kind=_kind_for(primary),
                language=language,
                concept_ids=tuple(m.concept_id for m in members),
                hint=_shorten(hint),
                category=primary.category,
            )
        )
    return mappable, skipped


def _shorten(text: str, limit: int = 110) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "â€¦"


def chunk_mappable(
    items: list[MappableConcept], chunk_size: int = 40
) -> list[list[MappableConcept]]:
    """Deterministic batches: grouped by kind, then alphabetical, then cut.

    Grouping by kind keeps each prompt's style instructions focused (a batch
    of methods reads differently than a batch of keywords); alphabetical
    order makes reruns reproducible.
    """
    ordered = sorted(items, key=lambda m: (m.kind, m.canonical_name))
    return [ordered[i : i + chunk_size] for i in range(0, len(ordered), chunk_size)]


# --------------------------------------------------------------------------
# Phase A â€” theme distillation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ThemeProfile:
    theme: str
    motifs: tuple[str, ...]
    tone: str
    output_language: str
    raw_model_output: str = ""
    clean_theme: str = ""
    learner_summary: str = ""
    primary_world: str = ""
    learning_pain_points: tuple[str, ...] = ()
    concept_preferences: dict[str, str] = field(default_factory=dict)
    family_motifs: dict[str, tuple[str, ...]] = field(default_factory=dict)
    domain_lexicon: dict[str, tuple[str, ...]] = field(default_factory=dict)
    domain_lexicon_source: str = ""
    #: "llm" = the model really produced this profile; "fallback" = the
    #: deterministic backup built it because every LLM attempt failed.
    #: Downstream token generation trusts the LLM profile as the single
    #: brain and only lets curated theme tables lead on the fallback path.
    source: str = "llm"

    def as_prompt_block(self) -> str:
        family_lines = "; ".join(
            f"{family}={', '.join(motifs)}"
            for family, motifs in self.family_motifs.items()
            if motifs
        )
        lexicon_lines = "; ".join(
            f"{category}={', '.join(words)}"
            for category, words in self.domain_lexicon.items()
            if words
        )
        return (
            f"Theme: {self.theme}\n"
            f"Clean theme: {self.clean_theme or self.theme}\n"
            f"Learner summary: {self.learner_summary or 'not specified'}\n"
            f"Primary world: {self.primary_world or self.clean_theme or self.theme}\n"
            f"Motifs: {', '.join(self.motifs)}\n"
            f"Learning pain points: {', '.join(self.learning_pain_points) or 'not specified'}\n"
            f"Family motifs: {family_lines or 'not specified'}\n"
            f"Compact domain lexicon: {lexicon_lines or 'not specified'}\n"
            f"Tone: {self.tone}\n"
            f"Token language: {self.output_language}"
        )


THEME_PROFILE_SYSTEM_PROMPT = """\
You are CodeVerse's theme analyst. You receive a user's theme — a single word
("Valorant"), a whole sentence ("someone who loves and deeply knows black
holes in space"), or any free text in any language — and distill it into a
reusable THEME PROFILE that later vocabulary-generation steps will share.

This must work for ANY input: a game, a sport, an anime, a job, a hobby, a
fictional universe, or a personal sentence that names no famous world at all.
Every input goes through the same analysis — never fall back to generic
programming words; always build the profile from the world the user actually
describes.

Motif hygiene: motifs are concrete nouns, actions, places, and jargon from
the world itself. NEVER copy learner filler from the user's sentence into
motifs or names ("I love", "seviyorum", "oynamayı seviyorum", "karışık
geliyor", "evreniyle oluştur", "bana", "python") — those words describe the
learner, not the world.

Produce:
- "clean_theme": the short canonical label of the user's main world/fandom
  (for example "Counter-Strike 2", "GTA San Andreas", "Formula 1"). Never
  include filler such as "I like playing", "I love", "oynamayi seviyorum".
- "learner_summary": one short sentence describing the learner's interests
  and what they find confusing.
- "primary_world": the strongest concrete world/game/domain to build from.
- "motifs": 8 to 15 short, concrete, evocative elements of that world â€”
  objects, actions, roles, places, jargon. Prefer words a fan would use.
- "learning_pain_points": Python concepts the user mentions as confusing
  (for example "if", "for", "function", "class"). Empty list if absent.
- "concept_preferences": a JSON object that maps concept families to motif
  preferences, e.g. {"condition": "clutch/round state", "loop": "site rotation"}.
- "family_motifs": a JSON object that ALWAYS maps the user's world into the
  same Python concept families: condition, iteration, function, output, data,
  oop, error, general. Each value is a list of 2-4 short concrete motifs
  (1-3 words each) from the user's world. Do this for every input, even very
  unusual personal text. Never leave a family empty and avoid reusing the
  same motif in two families.
  Example for a cooking learner:
  {"condition": ["taste check", "heat level"], "iteration": ["prep line"],
   "function": ["recipe method"], "output": ["order call"],
   "data": ["recipe card"], "oop": ["dish blueprint"],
  "error": ["burnt pan"], "general": ["kitchen station"]}.
- "domain_lexicon": a compact semantic vocabulary with EXACTLY these keys:
  entities, actions, states, containers, signals, failures, results. Give
  4-8 distinct English entries per key. Each entry must be one word when
  possible and never more than two short words. Use concrete full words from
  the user's world, not abbreviations, Python terms, generic programming
  words, or pieces of the learner's raw sentence. This lexicon is the source
  material for short identifiers, so prefer "patrol", "dispatch", "alert",
  "roster" over phrases such as "police_operations_dispatch_protocol".
- "tone": one short phrase describing the voice (e.g. "tactical and terse",
  "cosmic and awed").
- "output_language": the language the themed tokens should be written in.
  Use the requested language if one is given; otherwise use English. English
  identifiers are preferred because they stay shorter, more stable, and more
  programming-like for a personal Python syntax layer.

Respond with ONLY a JSON object:
{"clean_theme": "...", "learner_summary": "...", "primary_world": "...",
 "motifs": ["..."], "learning_pain_points": ["..."],
 "concept_preferences": {"condition": "..."},
 "family_motifs": {"condition": ["..."], "iteration": ["..."],
  "function": ["..."], "output": ["..."], "data": ["..."],
  "oop": ["..."], "error": ["..."], "general": ["..."]},
 "domain_lexicon": {"entities": ["..."], "actions": ["..."],
  "states": ["..."], "containers": ["..."], "signals": ["..."],
  "failures": ["..."], "results": ["..."]},
 "tone": "...", "output_language": "..."}
"""

_PROFILE_FEW_SHOT_USER = "Theme: Valorant\nRequested token language: en"
_PROFILE_FEW_SHOT_ASSISTANT = json.dumps(
    {
        "clean_theme": "Valorant",
        "learner_summary": "The learner likes tactical shooters and wants Python to feel like Valorant.",
        "primary_world": "Valorant",
        "motifs": [
            "agent", "ability", "spike", "site", "round", "economy",
            "crosshair", "smoke", "flash", "rotation", "clutch", "callout",
        ],
        "learning_pain_points": ["conditionals", "loops", "functions"],
        "concept_preferences": {
            "condition": "clutch or round state",
            "loop": "site rotation",
            "function": "agent ability",
            "output": "team callout",
        },
        "family_motifs": {
            "condition": ["clutch check", "round state"],
            "iteration": ["site rotation", "map route"],
            "function": ["agent ability", "utility lineup"],
            "output": ["team callout", "mic check"],
            "data": ["buy menu", "loadout card"],
            "oop": ["agent blueprint", "squad role"],
            "error": ["failed clutch", "missed smoke"],
            "general": ["site", "spike"],
        },
        "domain_lexicon": {
            "entities": ["agent", "spike", "site", "squad"],
            "actions": ["rotate", "defuse", "peek", "clutch"],
            "states": ["ready", "planted", "clear", "contested"],
            "containers": ["loadout", "roster", "inventory", "buy menu"],
            "signals": ["callout", "ping", "alert", "radio"],
            "failures": ["miss", "jam", "loss", "timeout"],
            "results": ["win", "save", "score", "payout"],
        },
        "tone": "tactical and terse",
        "output_language": "en",
    },
    ensure_ascii=False,
)


# second few-shot: a personal free-text sentence in Turkish that names no
# famous fandom — teaches the model that ANY input gets the same full
# analysis (strip learner filler, invent a concrete world, fill all eight
# families) instead of degrading to generic programming words.
_PROFILE_FEW_SHOT_USER_2 = (
    "Theme: ben deniz alti kesiflerini seviyorum ve donguler bana karisik geliyor"
)
_PROFILE_FEW_SHOT_ASSISTANT_2 = json.dumps(
    {
        "clean_theme": "Deep Sea Exploration",
        "learner_summary": (
            "The learner loves deep sea exploration and finds loops confusing."
        ),
        "primary_world": "Deep Sea Exploration",
        "motifs": [
            "sonar", "submarine", "dive route", "coral reef", "pressure gauge",
            "logbook", "radio ping", "airlock", "depth chart", "current drift",
        ],
        "learning_pain_points": ["for", "while"],
        "concept_preferences": {
            "condition": "sonar check",
            "loop": "dive route",
            "function": "mission protocol",
            "output": "radio ping",
            "data": "logbook",
        },
        "family_motifs": {
            "condition": ["sonar check", "pressure gate", "depth alarm"],
            "iteration": ["dive route", "current drift", "patrol sweep"],
            "function": ["mission protocol", "launch sequence", "salvage plan"],
            "output": ["radio ping", "surface report", "beacon flash"],
            "data": ["logbook", "depth chart", "cargo manifest"],
            "oop": ["vessel blueprint", "crew role", "hull design"],
            "error": ["pressure leak", "lost signal", "engine flood"],
            "general": ["airlock", "deep trench"],
        },
        "domain_lexicon": {
            "entities": ["submarine", "reef", "trench", "crew"],
            "actions": ["dive", "scan", "surface", "salvage"],
            "states": ["sealed", "deep", "stable", "pressurized"],
            "containers": ["logbook", "cargo", "chart", "airlock"],
            "signals": ["sonar", "beacon", "ping", "radio"],
            "failures": ["leak", "flood", "drift", "blackout"],
            "results": ["discovery", "sample", "recovery", "report"],
        },
        "tone": "calm and exploratory",
        "output_language": "en",
    },
    ensure_ascii=False,
)


def build_theme_profile_messages(
    theme: str,
    output_language: str | None = None,
    clarifying_answers: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    user = f"Theme: {theme}"
    if output_language:
        user += f"\nRequested token language: {output_language}"
    if clarifying_answers:
        qa_lines = "\n".join(f"- {q}: {a}" for q, a in clarifying_answers.items())
        user += f"\n\nAdditional details from the user:\n{qa_lines}"
    return [
        {"role": "system", "content": THEME_PROFILE_SYSTEM_PROMPT},
        {"role": "user", "content": _PROFILE_FEW_SHOT_USER},
        {"role": "assistant", "content": _PROFILE_FEW_SHOT_ASSISTANT},
        {"role": "user", "content": _PROFILE_FEW_SHOT_USER_2},
        {"role": "assistant", "content": _PROFILE_FEW_SHOT_ASSISTANT_2},
        {"role": "user", "content": user},
    ]


def parse_theme_profile_output(raw: str, theme: str) -> ThemeProfile:
    data = _extract_json_object(raw)
    motifs = data.get("motifs")
    if not isinstance(motifs, list) or not motifs:
        raise ValueError("tema profili Ã§Ä±ktÄ±sÄ±nda 'motifs' listesi yok")
    learning_pain_points = data.get("learning_pain_points") or []
    if not isinstance(learning_pain_points, list):
        learning_pain_points = []
    concept_preferences = data.get("concept_preferences") or {}
    if not isinstance(concept_preferences, dict):
        concept_preferences = {}
    family_motifs = _parse_family_motifs(data.get("family_motifs"))
    domain_lexicon = _parse_domain_lexicon(data.get("domain_lexicon"))
    return ThemeProfile(
        theme=theme,
        motifs=tuple(str(m).strip() for m in motifs if str(m).strip()),
        tone=str(data.get("tone", "")).strip() or "neutral",
        output_language=str(data.get("output_language", "")).strip() or "en",
        raw_model_output=raw,
        clean_theme=str(data.get("clean_theme", "")).strip(),
        learner_summary=str(data.get("learner_summary", "")).strip(),
        primary_world=str(data.get("primary_world", "")).strip(),
        learning_pain_points=tuple(
            str(item).strip() for item in learning_pain_points if str(item).strip()
        ),
        concept_preferences={
            str(key).strip(): str(value).strip()
            for key, value in concept_preferences.items()
            if str(key).strip() and str(value).strip()
        },
        family_motifs=family_motifs,
        domain_lexicon=domain_lexicon,
        domain_lexicon_source="llm" if domain_lexicon else "",
    )


_PROFILE_FAMILY_ALIASES = {
    "condition": "condition",
    "conditional": "condition",
    "branch": "condition",
    "control": "condition",
    "loop": "iteration",
    "loops": "iteration",
    "iteration": "iteration",
    "route": "iteration",
    "function": "function",
    "functions": "function",
    "return": "function",
    "output": "output",
    "input": "output",
    "communication": "output",
    "collection": "data",
    "collections": "data",
    "data": "data",
    "storage": "data",
    "oop": "oop",
    "class": "oop",
    "type": "oop",
    "error": "error",
    "errors": "error",
    "exception": "error",
    "exceptions": "error",
    "file": "error",
    "general": "general",
}


def _parse_family_motifs(raw: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(raw, dict):
        return {}

    parsed: dict[str, tuple[str, ...]] = {}
    for key, value in raw.items():
        family = _PROFILE_FAMILY_ALIASES.get(str(key).casefold().strip())
        if family is None:
            continue
        values = value if isinstance(value, list) else [value]
        motifs = tuple(
            str(item).strip()
            for item in values
            if str(item).strip()
        )
        if motifs:
            parsed[family] = motifs
    return parsed


_DOMAIN_LEXICON_CATEGORIES = (
    "entities",
    "actions",
    "states",
    "containers",
    "signals",
    "failures",
    "results",
)


def _parse_domain_lexicon(raw: object) -> dict[str, tuple[str, ...]]:
    """Normalize model vocabulary without trusting schema length support."""
    if not isinstance(raw, dict):
        return {}

    parsed: dict[str, tuple[str, ...]] = {}
    for category in _DOMAIN_LEXICON_CATEGORIES:
        value = raw.get(category)
        if not isinstance(value, list):
            continue
        words: list[str] = []
        seen: set[str] = set()
        for item in value:
            word = " ".join(str(item).strip().split())
            folded = word.casefold()
            if (
                not word
                or len(word) > 24
                or len(word.split()) > 2
                or folded in seen
            ):
                continue
            words.append(word)
            seen.add(folded)
            if len(words) == 8:
                break
        if words:
            parsed[category] = tuple(words)
    return parsed


# --------------------------------------------------------------------------
# Phase B â€” category batch mapping
# --------------------------------------------------------------------------

CATEGORY_MAPPING_SYSTEM_PROMPT = """\
You are CodeVerse's theme-vocabulary designer. A THEME PROFILE and a batch of programming constructs are given.
Invent one themed token per construct drawing from the profile's motifs.

Rules:
- One identifier: letters, digits, underscores; no digit start; no spaces/punctuation. snake_case.
- Must be distinct, and not in the FORBIDDEN list.
- No real programming keywords or built-ins.
- Do not mechanically append the canonical name or concept_id (bad: sign_if,
  ship_select, castle_len). The token itself must be a themed metaphor for
  what the construct does.
- Avoid one-prefix dictionaries. Spread the theme profile across tokens so
  each concept feels designed, not stamped.
- Meaning first: combine a concrete theme motif with the construct's role
  (condition, loop, output, join, count, inheritance, table creation, etc.).
- Family consistency: related variants should share a common stem.
- Tone/style matches the theme profile.
- Output tokens and rationale in the profile's token language.

Respond ONLY with a JSON object containing "mappings" and "rationale":
{"mappings": {"<canonical_name>": "<themed_token>", ...},
 "rationale": {"<canonical_name>": "<ultra-short explanation>", ...}}
Include every canonical name exactly once.
"""

_BATCH_FEW_SHOT_USER = """\
THEME PROFILE
Theme: Valorant
Motifs: ajan, yetenek, bomba (spike), site, raund, ekonomi, niÅŸan, duman, flaÅŸ, rotasyon
Tone: taktiksel
Token language: tr

FORBIDDEN (already taken): yetenek, tetiklendiginde

CONSTRUCTS (kind=method)
- upper: converts to upper case
- lower: converts to lower case
- split: splits a string
"""

_BATCH_FEW_SHOT_ASSISTANT = json.dumps(
    {
        "mappings": {
            "upper": "yuksek_ses",
            "lower": "sessiz_adim",
            "split": "takimlara_ayir",
        },
        "rationale": {
            "upper": "Harfleri taktik çağrı gibi yükseltir",
            "lower": "Harfleri sessiz yürüyüşe indirir",
            "split": "Metni ayrı takımlara böler",
        },
    },
    ensure_ascii=False,
)


def build_category_mapping_messages(
    profile: ThemeProfile,
    batch: list[MappableConcept],
    forbidden_tokens: list[str],
    correction_feedback: str | None = None,
) -> list[dict[str, str]]:
    if not batch:
        raise ValueError("boÅŸ kavram grubu ile prompt kurulamaz")

    kind = batch[0].kind
    lines = "\n".join(f"- {m.canonical_name}: {m.hint}" for m in batch)
    forbidden = ", ".join(forbidden_tokens) if forbidden_tokens else "(none yet)"

    user_parts = [
        "THEME PROFILE\n" + profile.as_prompt_block(),
        f"FORBIDDEN (already taken): {forbidden}",
        f"CONSTRUCTS (kind={kind})\n{lines}",
    ]
    if correction_feedback:
        user_parts.append(
            "Your previous attempt was rejected by the validator. Fix exactly "
            f"these problems and answer again:\n{correction_feedback}"
        )

    return [
        {"role": "system", "content": CATEGORY_MAPPING_SYSTEM_PROMPT},
        {"role": "user", "content": _BATCH_FEW_SHOT_USER},
        {"role": "assistant", "content": _BATCH_FEW_SHOT_ASSISTANT},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


@dataclass(frozen=True)
class BatchMappingResult:
    mappings: dict[str, str]  # canonical_name -> themed token
    rationale: dict[str, str] = field(default_factory=dict)
    raw_model_output: str = ""


def parse_category_mapping_output(
    raw: str, batch: list[MappableConcept]
) -> BatchMappingResult:
    """Parse one batch answer; missing/extra names raise so the orchestrator
    can retry the batch with corrective feedback."""
    data = _extract_json_object(raw)
    mappings = data.get("mappings")
    if not isinstance(mappings, dict):
        raise ValueError("Ã§Ä±ktÄ±da 'mappings' nesnesi yok")

    expected = {m.canonical_name for m in batch}
    got = {str(k) for k in mappings}
    missing = expected - got
    if missing:
        raise ValueError(f"eksik kavramlar: {', '.join(sorted(missing)[:8])}")

    rationale = data.get("rationale") or {}
    if not isinstance(rationale, dict):
        rationale = {}
    return BatchMappingResult(
        mappings={str(k): str(v).strip() for k, v in mappings.items() if str(k) in expected},
        rationale={str(k): str(v) for k, v in rationale.items() if str(k) in expected},
        raw_model_output=raw,
    )


# --------------------------------------------------------------------------
# shared
# --------------------------------------------------------------------------

# Re-exported so existing call sites in this module (and any other module
# importing it from here) keep working unchanged. The real implementation
# lives in json_extraction.py so clarifying_questions.py can reuse it too
# without duplicating the fence-stripping/brace-scanning logic.
_extract_json_object = extract_json_object
