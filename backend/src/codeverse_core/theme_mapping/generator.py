"""Orchestrates provider + validator into a validated ThemeDictionary."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Iterable

from codeverse_core.concepts import UniversalConcept
from codeverse_core.data.taxonomy_loader import Language, TaxonomyConcept
from codeverse_core.theme_mapping.dictionary import ThemeDictionary
from codeverse_core.theme_mapping.llm_provider import (
    LLMProvider,
    ThemeMappingRequest,
)
from codeverse_core.theme_mapping.taxonomy_generator import (
    ChatCapableProvider,
    TaxonomyGenerationError,
    generate_theme_profile,
)
from codeverse_core.theme_mapping.taxonomy_prompts import (
    BatchMappingResult,
    MappableConcept,
    ThemeProfile,
    build_category_mapping_messages,
    chunk_mappable,
    extract_mappable,
    parse_category_mapping_output,
)
from codeverse_core.theme_mapping.theme_families import (
    DOMAIN_FAMILY_MOTIFS as _DOMAIN_FAMILY_MOTIFS,
    DOMAIN_LABELS as _DOMAIN_LABELS,
    detect_domain as _domain_theme_key,
)
from codeverse_core.theme_mapping.validator import (
    PERSONAL_PYTHON_COMPACT_IDS,
    ThemeDictionaryValidationError,
    validate_personal_python_dictionary_quality,
    validate_mappings,
    validate_taxonomy_batch,
)

logger = logging.getLogger(__name__)


class ThemeDictionaryGenerator:
    def __init__(self, provider: LLMProvider, max_attempts: int = 3) -> None:
        self._provider = provider
        self._max_attempts = max_attempts

    def generate(
        self,
        theme: str,
        output_language: str | None = None,
        existing: ThemeDictionary | None = None,
    ) -> tuple[ThemeDictionary, str]:
        """Generate and validate a dictionary for a free-text theme.

        Returns (dictionary, raw_model_output). Retries with corrective
        feedback when the validator rejects the model's tokens; raises
        ThemeDictionaryValidationError after ``max_attempts`` failures.
        """
        feedback: str | None = None
        last_problems: list[str] = []

        for attempt in range(1, self._max_attempts + 1):
            request = ThemeMappingRequest(
                theme=theme,
                output_language=output_language,
                existing_mappings=existing.mappings if existing else None,
                correction_feedback=feedback,
            )
            response = self._provider.generate_theme_mapping(request)

            mappings: dict[UniversalConcept, str] = {}
            unknown_keys: list[str] = []
            for key, token in response.mappings.items():
                try:
                    mappings[UniversalConcept.from_key(key)] = token.strip()
                except ValueError:
                    unknown_keys.append(key)

            problems = validate_mappings(mappings)
            if unknown_keys:
                problems.append(f"unknown concept keys in output: {', '.join(unknown_keys)}")

            if not problems:
                rationale = {}
                for key, why in response.rationale.items():
                    try:
                        rationale[UniversalConcept.from_key(key)] = why
                    except ValueError:
                        pass
                return (
                    ThemeDictionary(theme=theme, mappings=mappings, rationale=rationale),
                    response.raw_model_output,
                )

            last_problems = problems
            feedback = "\n".join(f"- {p}" for p in problems)
            logger.warning(
                "theme mapping attempt %d/%d rejected (%s): %s",
                attempt,
                self._max_attempts,
                self._provider.provider_name,
                feedback,
            )

        raise ThemeDictionaryValidationError(last_problems)


@dataclass(frozen=True)
class TaxonomyBatchSummary:
    """One category call executed by the taxonomy orchestrator."""

    language: Language
    category: str
    kind: str
    canonical_names: tuple[str, ...]
    concept_ids: tuple[str, ...]
    attempts: int


@dataclass(frozen=True)
class TaxonomyResolvedConcept:
    """Lexer-facing resolved taxonomy concept.

    Structural concepts that already exist in ``UniversalConcept`` resolve to
    that enum directly. Everything else resolves to this lightweight object so
    the lexer can keep it as a NAME while replacing the themed spelling with
    the canonical construct name.
    """

    concept_id: str
    canonical: str
    kind: str
    language: Language


@dataclass(frozen=True)
class TaxonomyThemeDictionary:
    """Expanded theme dictionary keyed by taxonomy ``concept_id``.

    This deliberately does not replace :class:`ThemeDictionary`: the current
    compiler still consumes ``UniversalConcept`` keys, while Adım 9 prepares
    the wider taxonomy vocabulary that later validator/codegen steps can bind.
    """

    theme: str
    mappings: dict[str, str]
    rationale: dict[str, str] = field(default_factory=dict)
    profile: ThemeProfile | None = None
    skipped_concept_ids: tuple[str, ...] = ()
    batches: tuple[TaxonomyBatchSummary, ...] = ()
    provider_name: str = ""
    model: str = ""

    @property
    def theme_dictionary(self) -> dict[str, str]:
        """Plan wording alias: a single user dictionary of concept_id -> token."""
        return self.mappings

    def __post_init__(self) -> None:
        reverse: dict[str, UniversalConcept | TaxonomyResolvedConcept] = {}
        universal_tokens: dict[UniversalConcept, str] = {}
        index = _mappable_by_concept_id()
        for concept_id, token in self.mappings.items():
            item = index.get(concept_id)
            if item is None:
                continue
            universal = _taxonomy_universal_alias(item.language, item.canonical_name)
            resolved: UniversalConcept | TaxonomyResolvedConcept
            if universal is not None:
                resolved = universal
                universal_tokens.setdefault(universal, token)
            else:
                resolved = TaxonomyResolvedConcept(
                    concept_id=concept_id,
                    canonical=item.canonical_name,
                    kind=item.kind,
                    language=item.language,
                )
            reverse[token] = resolved
        object.__setattr__(self, "_reverse", reverse)
        object.__setattr__(self, "_universal_tokens", universal_tokens)

    def resolve(self, token: str) -> UniversalConcept | TaxonomyResolvedConcept | None:
        return self._reverse.get(token)  # type: ignore[attr-defined]

    def token_for(self, concept_id: str | UniversalConcept) -> str:
        if isinstance(concept_id, UniversalConcept):
            return self._universal_tokens.get(  # type: ignore[attr-defined]
                concept_id, concept_id.canonical
            )
        return self.mappings[concept_id]

    def to_json_mappings(self) -> dict[str, str]:
        return dict(self.mappings)


@dataclass(frozen=True)
class _TaxonomyBatch:
    language: Language
    category: str
    kind: str
    concepts: tuple[MappableConcept, ...]

    @property
    def label(self) -> str:
        return f"{self.language}/{self.category}/{self.kind}"

    @property
    def canonical_names(self) -> tuple[str, ...]:
        return tuple(c.canonical_name for c in self.concepts)

    @property
    def concept_ids(self) -> tuple[str, ...]:
        return tuple(cid for c in self.concepts for cid in c.concept_ids)


class TaxonomyThemeDictionaryGenerator:
    """Adım 9: category-by-category taxonomy theme generation.

    The class owns the full taxonomy-scale orchestration:
    profile once, category batches in deterministic order, accumulated
    forbidden tokens, validator feedback retries, and alias fan-out from
    canonical names to every taxonomy concept_id.
    """

    def __init__(
        self,
        provider: ChatCapableProvider,
        max_attempts: int = 4,
        chunk_size: int = 25,
    ) -> None:
        self._provider = provider
        self._max_attempts = max_attempts
        self._chunk_size = chunk_size

    def generate(
        self,
        theme: str,
        output_language: str | None = None,
        languages: tuple[Language, ...] = ("python", "sql"),
        concepts: Iterable[MappableConcept] | None = None,
    ) -> TaxonomyThemeDictionary:
        """Generate one expanded ``concept_id -> themed_token`` dictionary.

        ``concepts`` is an injectable subset for targeted generation/tests;
        when omitted, all mappable taxonomy concepts for ``languages`` are
        loaded and grouped by language/category/kind.
        """
        profile = generate_theme_profile(
            self._provider,
            theme,
            output_language=output_language,
            max_attempts=self._max_attempts,
            fallback_on_failure=True,
        )
        batches, skipped = self._plan_batches(languages, concepts)
        all_canonical_names = {
            _fold(c.canonical_name) for batch in batches for c in batch.concepts
        }

        mappings: dict[str, str] = {}
        rationale: dict[str, str] = {}
        used_tokens: dict[str, str] = {}
        forbidden_tokens: list[str] = []
        summaries: list[TaxonomyBatchSummary] = []

        for batch in batches:
            result, attempts = self._generate_validated_batch(
                profile,
                batch,
                forbidden_tokens,
                used_tokens,
                all_canonical_names,
            )
            for concept in batch.concepts:
                token = result.mappings[concept.canonical_name].strip()
                rationale_text = result.rationale.get(concept.canonical_name, "")
                used_tokens[_fold(token)] = concept.canonical_name
                forbidden_tokens.append(token)
                for concept_id in concept.concept_ids:
                    mappings[concept_id] = token
                    if rationale_text:
                        rationale[concept_id] = rationale_text

            summaries.append(
                TaxonomyBatchSummary(
                    language=batch.language,
                    category=batch.category,
                    kind=batch.kind,
                    canonical_names=batch.canonical_names,
                    concept_ids=batch.concept_ids,
                    attempts=attempts,
                )
            )

        return TaxonomyThemeDictionary(
            theme=theme,
            mappings=mappings,
            rationale=rationale,
            profile=profile,
            skipped_concept_ids=tuple(c.concept_id for c in skipped),
            batches=tuple(summaries),
            provider_name=self._provider.provider_name,
            model=str(getattr(self._provider, "model", "")),
        )

    def generate_profile_seeded(
        self,
        theme: str,
        output_language: str | None = None,
        languages: tuple[Language, ...] = ("python", "sql"),
        concepts: Iterable[MappableConcept] | None = None,
        clarifying_answers: dict[str, str] | None = None,
        *,
        critical_overrides_enabled: bool = True,
        profile_fallback_on_failure: bool = True,
        compact_profile_prompt: bool = False,
    ) -> TaxonomyThemeDictionary:
        """Fast app path: use the LLM once for theme motifs, then produce a
        complete, validated taxonomy dictionary deterministically.

        Full per-batch LLM generation remains available through ``generate``;
        this mode keeps the interactive UI responsive while still binding the
        vocabulary to the user's free-form theme via the LLM profile.

        ``clarifying_answers``: optional onboarding-wizard answers threaded
        straight into the profile call for extra grounding context.
        """
        profile = generate_theme_profile(
            self._provider,
            theme,
            output_language=output_language,
            max_attempts=self._max_attempts,
            fallback_on_failure=profile_fallback_on_failure,
            clarifying_answers=clarifying_answers,
            compact_prompt=compact_profile_prompt,
        )
        profile = _harden_personal_profile(profile)
        batches, skipped = self._plan_batches(languages, concepts)
        all_canonical_names = {
            _fold(c.canonical_name) for batch in batches for c in batch.concepts
        }
        motif_slugs = _profile_motif_slugs(profile, theme)
        reserved_preferred_tokens = _reserved_preferred_tokens(profile, batches)

        mappings: dict[str, str] = {}
        rationale: dict[str, str] = {}
        used_tokens: dict[str, str] = {}
        summaries: list[TaxonomyBatchSummary] = []
        # Quality-first: one extra LLM pass proposes bespoke tokens for the
        # ~50 concepts learners type most (if/for/def/print/...). Slower by
        # design — product call: better names beat faster generation. Degrades
        # gracefully to the deterministic path when the call fails.
        critical_overrides = self._generate_critical_overrides(
            profile,
            batches,
            all_canonical_names,
            enabled=critical_overrides_enabled,
        )

        # Reserve concise names for the concepts learners type most often
        # before the long taxonomy tail can consume every strong theme motif.
        compact_concepts = [
            concept
            for batch in batches
            for concept in batch.concepts
            if concept.canonical_name.casefold() in _COMPACT_LEARNING_CONCEPTS
        ]
        for concept in compact_concepts:
            token = _unique_profile_token(
                profile,
                motif_slugs,
                concept,
                used_tokens,
                all_canonical_names,
                reserved_preferred_tokens,
            )
            token, rationale_text = _repair_mapping_quality(
                profile,
                concept,
                token,
                _profile_rationale(profile, concept, token),
                used_tokens,
                all_canonical_names,
                reserved_preferred_tokens,
            )
            for concept_id in concept.concept_ids:
                mappings[concept_id] = token
                rationale[concept_id] = _profile_rationale(profile, concept, token)

        for batch in batches:
            for concept in batch.concepts:
                if all(concept_id in mappings for concept_id in concept.concept_ids):
                    continue
                override = critical_overrides.get(concept.canonical_name)
                if override is not None and _is_available_generated_token(
                    override.mappings[concept.canonical_name], used_tokens, all_canonical_names
                ):
                    token = override.mappings[concept.canonical_name]
                    rationale_text = override.rationale.get(concept.canonical_name, "")
                    used_tokens[_fold(token)] = concept.canonical_name
                else:
                    token = _unique_profile_token(
                        profile,
                        motif_slugs,
                        concept,
                        used_tokens,
                        all_canonical_names,
                        reserved_preferred_tokens,
                    )
                    rationale_text = _profile_rationale(profile, concept, token)
                token, rationale_text = _repair_mapping_quality(
                    profile,
                    concept,
                    token,
                    rationale_text,
                    used_tokens,
                    all_canonical_names,
                    reserved_preferred_tokens,
                )
                rationale_text = _profile_rationale(profile, concept, token)
                for concept_id in concept.concept_ids:
                    mappings[concept_id] = token
                    rationale[concept_id] = rationale_text
            summaries.append(
                TaxonomyBatchSummary(
                    language=batch.language,
                    category=batch.category,
                    kind=batch.kind,
                    canonical_names=batch.canonical_names,
                    concept_ids=batch.concept_ids,
                    attempts=1,
                )
            )

        if concepts is None and languages == ("python",):
            quality_problems = validate_personal_python_dictionary_quality(
                mappings,
                rationale,
                require_python_only=True,
            )
            if quality_problems:
                # A single bad token must never sink the whole request: repair
                # the named concepts in place and re-run the gate. Only truly
                # unrepairable output still raises.
                quality_problems = self._auto_repair_gate_problems(
                    profile,
                    batches,
                    quality_problems,
                    mappings,
                    rationale,
                    used_tokens,
                    all_canonical_names,
                    reserved_preferred_tokens,
                )
            if quality_problems:
                raise TaxonomyGenerationError(
                    "Personal Python dictionary failed quality gate: "
                    + "; ".join(quality_problems[:8])
                )

        return TaxonomyThemeDictionary(
            theme=_theme_label(profile),
            mappings=mappings,
            rationale=rationale,
            profile=profile,
            skipped_concept_ids=tuple(c.concept_id for c in skipped),
            batches=tuple(summaries),
            provider_name=self._provider.provider_name,
            model=str(getattr(self._provider, "model", "")),
        )

    def _auto_repair_gate_problems(
        self,
        profile: ThemeProfile,
        batches: list[_TaxonomyBatch],
        problems: list[str],
        mappings: dict[str, str],
        rationale: dict[str, str],
        used_tokens: dict[str, str],
        all_canonical_names: set[str],
        reserved_preferred_tokens: dict[str, str],
    ) -> list[str]:
        """Repair final-gate failures in place instead of failing the request.

        The gate names offending concept_ids ("py_set_add: token ... is too
        long for learning UI"); each named concept gets its token regenerated
        under the strictest rules — with a deterministic shortening fallback —
        and the gate re-runs. Returns whatever problems remain (empty on
        success).
        """
        concept_by_id = {
            concept_id: concept
            for batch in batches
            for concept in batch.concepts
            for concept_id in concept.concept_ids
        }
        motif_slugs = _profile_motif_slugs(profile, profile.clean_theme or profile.theme)

        for _round in range(3):
            offending: list[str] = []
            for problem in problems:
                concept_id = problem.split(":", 1)[0].strip()
                if concept_id in concept_by_id and concept_id not in offending:
                    offending.append(concept_id)
            if not offending:
                return problems

            repaired_any = False
            seen_canonicals: set[str] = set()
            for concept_id in offending:
                concept = concept_by_id[concept_id]
                if concept.canonical_name in seen_canonicals:
                    continue
                seen_canonicals.add(concept.canonical_name)

                old_token = mappings.get(concept_id, "")
                if old_token and used_tokens.get(_fold(old_token)) == concept.canonical_name:
                    used_tokens.pop(_fold(old_token), None)

                token = _unique_profile_token(
                    profile,
                    motif_slugs,
                    concept,
                    used_tokens,
                    all_canonical_names,
                    reserved_preferred_tokens,
                )
                token, _ = _repair_mapping_quality(
                    profile,
                    concept,
                    token,
                    _profile_rationale(profile, concept, token),
                    used_tokens,
                    all_canonical_names,
                    reserved_preferred_tokens,
                )

                # Deterministic last resort: force the gate's own length
                # budget so this round always converges.
                limit = 16 if any(
                    cid in PERSONAL_PYTHON_COMPACT_IDS for cid in concept.concept_ids
                ) else 20
                if len(token) > limit or len([p for p in token.split("_") if p]) > 2:
                    if used_tokens.get(_fold(token)) == concept.canonical_name:
                        used_tokens.pop(_fold(token), None)
                    stem = (_compact_slug(token) or token.split("_", 1)[0])[:limit]
                    candidate = stem
                    index = 2
                    while not _is_available_generated_token(
                        candidate, used_tokens, all_canonical_names
                    ):
                        suffix = str(index)
                        candidate = f"{stem[: max(1, limit - len(suffix) - 1)]}_{suffix}"
                        index += 1
                    token = candidate
                    used_tokens[_fold(token)] = concept.canonical_name

                if token != old_token:
                    repaired_any = True
                for cid in concept.concept_ids:
                    mappings[cid] = token
                    rationale[cid] = _profile_rationale(profile, concept, token)

            problems = validate_personal_python_dictionary_quality(
                mappings,
                rationale,
                require_python_only=True,
            )
            if not problems:
                return []
            if not repaired_any:
                break
        return problems

    def _generate_critical_overrides(
        self,
        profile: ThemeProfile,
        batches: list[_TaxonomyBatch],
        all_canonical_names: set[str],
        *,
        enabled: bool,
    ) -> dict[str, BatchMappingResult]:
        if not enabled:
            return {}
        critical = [
            concept
            for batch in batches
            for concept in batch.concepts
            if concept.language == "python"
            and concept.canonical_name.casefold() in _CRITICAL_PYTHON_CONCEPTS
        ]
        if not critical:
            return {}
        batch = _TaxonomyBatch(
            language="python",
            category="personal_core",
            kind="keyword",
            concepts=tuple(critical),
        )
        try:
            result, _attempts = self._generate_validated_batch(
                profile,
                batch,
                forbidden_tokens=[],
                used_tokens={},
                all_canonical_names=all_canonical_names,
            )
        except Exception as exc:  # noqa: BLE001 - LLM quality path must degrade gracefully
            logger.warning("critical Python override generation skipped: %s", exc)
            return {}

        accepted: dict[str, BatchMappingResult] = {}
        for concept in critical:
            token = result.mappings.get(concept.canonical_name, "").strip()
            rationale = result.rationale.get(concept.canonical_name, "").strip()
            if not _quality_issues(profile, concept, token, rationale, all_canonical_names):
                accepted[concept.canonical_name] = BatchMappingResult(
                    mappings={concept.canonical_name: token},
                    rationale={concept.canonical_name: rationale},
                    raw_model_output=result.raw_model_output,
                )
        return accepted

    def _plan_batches(
        self,
        languages: tuple[Language, ...],
        concepts: Iterable[MappableConcept] | None,
    ) -> tuple[list[_TaxonomyBatch], list[TaxonomyConcept]]:
        skipped: list[TaxonomyConcept] = []
        if concepts is None:
            items: list[MappableConcept] = []
            for language in languages:
                language_items, language_skipped = extract_mappable(language)
                items.extend(language_items)
                skipped.extend(language_skipped)
        else:
            items = list(concepts)

        buckets: dict[tuple[Language, str, str], list[MappableConcept]] = {}
        for concept in items:
            category = concept.category or concept.kind
            buckets.setdefault((concept.language, category, concept.kind), []).append(concept)

        batches: list[_TaxonomyBatch] = []
        for (language, category, kind), bucket in sorted(buckets.items()):
            for chunk in chunk_mappable(bucket, self._chunk_size):
                batches.append(
                    _TaxonomyBatch(
                        language=language,
                        category=category,
                        kind=kind,
                        concepts=tuple(chunk),
                    )
                )
        return batches, skipped

    def _generate_validated_batch(
        self,
        profile: ThemeProfile,
        batch: _TaxonomyBatch,
        forbidden_tokens: list[str],
        used_tokens: dict[str, str],
        all_canonical_names: set[str],
    ) -> tuple[BatchMappingResult, int]:
        feedback: str | None = None
        last_problem = "unknown validation failure"

        for attempt in range(1, self._max_attempts + 1):
            messages = build_category_mapping_messages(
                profile,
                list(batch.concepts),
                forbidden_tokens,
                correction_feedback=feedback,
            )
            raw = self._provider.chat(messages, temperature=0.8, max_tokens=8192)
            try:
                result = parse_category_mapping_output(raw, list(batch.concepts))
                problems = self._validate_batch_result(
                    result,
                    batch,
                    used_tokens,
                    all_canonical_names,
                )
            except ValueError as exc:
                problems = [str(exc)]

            if not problems:
                return result, attempt

            feedback = "\n".join(f"- {problem}" for problem in problems)
            last_problem = feedback
            logger.warning(
                "taxonomy batch attempt %d/%d rejected (%s, %s): %s",
                attempt,
                self._max_attempts,
                self._provider.provider_name,
                batch.label,
                feedback,
            )

        raise TaxonomyGenerationError(
            f"{batch.label} batch {self._max_attempts} denemede üretilemedi: "
            f"{last_problem}"
        )

    def _validate_batch_result(
        self,
        result: BatchMappingResult,
        batch: _TaxonomyBatch,
        used_tokens: dict[str, str],
        all_canonical_names: set[str],
    ) -> list[str]:
        # Adım 10: rule implementation lives in validator.py (shared,
        # independently unit-tested); this method only shapes this batch's
        # data into that function's plain-dict contract.
        batch_mappings = {
            concept.canonical_name: result.mappings.get(concept.canonical_name, "")
            for concept in batch.concepts
        }
        return validate_taxonomy_batch(
            batch_mappings,
            used_tokens=used_tokens,
            reserved_names=all_canonical_names,
        )


def _fold(token: str) -> str:
    return unicodedata.normalize("NFKC", token).casefold()


def _profile_motif_slugs(profile: ThemeProfile, theme: str) -> tuple[str, ...]:
    family_motifs = [
        motif
        for motifs in _family_motifs(profile).values()
        for motif in motifs
    ]
    lexicon_words = [
        word
        for words in profile.domain_lexicon.values()
        for word in words
    ]
    if _profile_is_trusted(profile):
        candidates = list(profile.motifs) + lexicon_words + family_motifs
    else:
        candidates = family_motifs + lexicon_words + list(profile.motifs)
    slugs: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        slug = _identifier_slug(candidate)
        if slug and slug not in seen and not _is_weak_motif_slug(slug):
            slugs.append(slug)
            seen.add(slug)
    if not slugs:
        fallback = _identifier_slug(theme)
        if fallback:
            slugs.append(fallback)
    return tuple(slugs[:64] or ("theme",))


def _is_weak_motif_slug(slug: str) -> bool:
    parts = set(slug.split("_"))
    return (
        slug in _WEAK_MOTIF_SLUGS
        or bool(parts & _WEAK_MOTIF_PARTS)
        or any(bad in slug for bad in _BAD_TOKEN_SUBSTRINGS)
    )


def _known_theme_motifs(profile: ThemeProfile) -> tuple[str, ...]:
    return tuple(
        motif
        for motifs in _known_theme_family_motifs(profile).values()
        for motif in motifs
    )


def _harden_personal_profile(profile: ThemeProfile) -> ThemeProfile:
    """Normalize the profile into a complete Personal Python learning brain.

    The LLM is allowed to be creative, but the product contract is stricter:
    every prompt must end with concrete, short motifs for every Python concept
    family. Weak/filler motifs are removed, missing families are filled from
    domain or personal fallback cues, and concept preferences are aligned with
    the same family map.
    """

    backing_label, backing_families = _profile_backing_assets(profile)
    family_motifs: dict[str, tuple[str, ...]] = {}
    personal_fallback = _personal_fallback_family_motifs(profile)
    prefer_backing = _has_curated_specific_theme(profile)

    for family in _CONCEPT_FAMILIES:
        candidates: list[str] = []
        candidates.extend(profile.family_motifs.get(family, ()))
        candidates.extend(
            value
            for key, value in profile.concept_preferences.items()
            if _normalize_family_name(key) == family
        )
        if prefer_backing:
            candidates.extend(backing_families.get(family, ()))
            candidates.extend(personal_fallback.get(family, ()))
        else:
            candidates.extend(personal_fallback.get(family, ()))
            candidates.extend(backing_families.get(family, ()))
        if family == "general":
            candidates.extend(profile.motifs)
        family_motifs[family] = tuple(_strong_unique_motifs(candidates, limit=4))

    for family in _CONCEPT_FAMILIES:
        if family_motifs.get(family):
            continue
        family_motifs[family] = tuple(
            _strong_unique_motifs(personal_fallback.get(family, ()), limit=3)
        )

    motifs = _strong_unique_motifs(
        [
            *profile.motifs,
            *(motif for motifs in family_motifs.values() for motif in motifs),
        ],
        limit=18,
    )
    if not motifs:
        motifs = list(_strong_unique_motifs(personal_fallback["general"], limit=3))

    concept_preferences: dict[str, str] = {}
    for key, value in profile.concept_preferences.items():
        family = _normalize_family_name(key)
        if family and _strong_motif(value):
            concept_preferences[family] = value
    for family in ("condition", "iteration", "function", "output", "data", "oop", "error"):
        if family not in concept_preferences and family_motifs.get(family):
            concept_preferences[family] = family_motifs[family][0]

    domain_lexicon = _harden_domain_lexicon(profile, family_motifs)

    clean_theme = profile.clean_theme.strip() or backing_label
    clean_theme_parts = set(_identifier_parts(clean_theme))
    if (
        _is_weak_motif_slug(_identifier_slug(clean_theme))
        or clean_theme_parts & _WEAK_MOTIF_PARTS
        or clean_theme_parts & _GENERIC_TOKEN_PARTS
        or clean_theme_parts & _TECHNICAL_TOKEN_PARTS
    ):
        clean_theme = backing_label if _has_curated_specific_theme(profile) else (
            _personal_base_label(profile) or backing_label
        )
    if clean_theme == clean_theme.casefold():
        clean_theme = clean_theme.title()
    primary_world = profile.primary_world.strip() or clean_theme
    learner_summary = profile.learner_summary.strip() or (
        f"The learner wants Python concepts to feel connected to {clean_theme}."
    )

    return replace(
        profile,
        clean_theme=clean_theme,
        primary_world=primary_world,
        learner_summary=learner_summary,
        motifs=tuple(motifs),
        concept_preferences=concept_preferences,
        family_motifs=family_motifs,
        domain_lexicon=domain_lexicon,
        output_language=profile.output_language or "en",
    )


_LEXICON_FAMILY_SOURCES: dict[str, tuple[str, ...]] = {
    "condition": ("states", "entities"),
    "iteration": ("actions", "entities"),
    "function": ("actions", "results"),
    "output": ("signals", "results"),
    "data": ("containers", "entities"),
    "oop": ("entities", "containers"),
    "error": ("failures", "states"),
    "general": ("entities", "actions", "states"),
}

_LEXICON_CATEGORY_FAMILIES: dict[str, tuple[str, ...]] = {
    "entities": ("general", "oop"),
    "actions": ("iteration", "function"),
    "states": ("condition",),
    "containers": ("data",),
    "signals": ("output",),
    "failures": ("error",),
    "results": ("function", "general"),
}


def _harden_domain_lexicon(
    profile: ThemeProfile,
    family_motifs: dict[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    """Build a short semantic vocabulary even when the model omits a bucket."""
    lexicon: dict[str, tuple[str, ...]] = {}
    for category, fallback_families in _LEXICON_CATEGORY_FAMILIES.items():
        candidates = [*profile.domain_lexicon.get(category, ())]
        candidates.extend(
            motif
            for family in fallback_families
            for motif in family_motifs.get(family, ())
        )
        lexicon[category] = tuple(_compact_lexicon_entries(candidates, limit=8))
    return lexicon


def _compact_lexicon_entries(values: Iterable[str], *, limit: int) -> list[str]:
    entries: list[str] = []
    seen: set[str] = set()
    for value in values:
        slug = _identifier_slug(value)
        if (
            not slug
            or len(slug) > 24
            or len(slug.split("_")) > 2
            or _is_weak_motif_slug(slug)
            or slug in seen
        ):
            continue
        entries.append(slug.replace("_", " "))
        seen.add(slug)
        if len(entries) == limit:
            break
    return entries


def _lexicon_family_motifs(profile: ThemeProfile) -> dict[str, tuple[str, ...]]:
    return {
        family: tuple(
            word
            for category in categories
            for word in profile.domain_lexicon.get(category, ())
        )
        for family, categories in _LEXICON_FAMILY_SOURCES.items()
    }


def _profile_backing_assets(profile: ThemeProfile) -> tuple[str, dict[str, tuple[str, ...]]]:
    known = _known_theme_family_motifs(profile)
    if known:
        return _theme_label(profile), known

    combined = " ".join(
        part
        for part in (
            profile.clean_theme,
            profile.primary_world,
            profile.theme,
            profile.learner_summary,
            " ".join(profile.motifs),
        )
        if part
    )
    domain_key = _domain_theme_key(combined)
    if domain_key is not None:
        return (
            _DOMAIN_LABELS.get(domain_key, domain_key.replace("_", " ").title()),
            _DOMAIN_FAMILY_MOTIFS.get(domain_key, {}),
        )
    return _personal_base_label(profile), _personal_fallback_family_motifs(profile)


def _has_curated_specific_theme(profile: ThemeProfile) -> bool:
    label = _theme_label(profile).casefold()
    return any(
        needle in label
        for needle in (
            "gta san andreas",
            "counter-strike 2",
            "counter strike 2",
            "minecraft",
            "formula 1",
            "harry potter",
            "witcher",
            "philosopher",
            "philosophy",
        )
    )


def _personal_base_label(profile: ThemeProfile) -> str:
    words = _personal_base_words(profile)
    return " ".join(words).title() if words else "Personal Learning"


def _personal_base_words(profile: ThemeProfile) -> tuple[str, ...]:
    candidates = " ".join(
        part
        for part in (
            *profile.motifs,
            profile.clean_theme,
            profile.primary_world,
            profile.theme,
        )
        if part
    )
    words: list[str] = []
    for part in _identifier_parts(candidates):
        if part in _PERSONAL_PROFILE_STOP_WORDS:
            continue
        if part in words:
            continue
        words.append(part)
        if len(words) == 2:
            break
    return tuple(words or ("personal",))


def _personal_fallback_family_motifs(profile: ThemeProfile) -> dict[str, tuple[str, ...]]:
    words = _personal_base_words(profile)
    first = words[0]
    second = words[1] if len(words) > 1 else "learning"
    return {
        "condition": (f"{first} check", f"{second} choice", "decision gate"),
        "iteration": (f"{first} route", f"{second} cycle", "step path"),
        "function": (f"{first} method", f"{second} result", "action plan"),
        "output": (f"{first} signal", f"{second} message", "clear note"),
        "data": (f"{first} record", f"{second} list", "memory card"),
        "oop": (f"{first} blueprint", f"{second} type", "role model"),
        "error": (f"{first} fault", f"{second} recovery", "safe retry"),
        "general": (f"{first} cue", f"{second} map", "learning path"),
    }


def _strong_unique_motifs(candidates: Iterable[str], *, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = " ".join(str(candidate).strip().split())
        if not _strong_motif(value):
            continue
        slug = _identifier_slug(value)
        if slug in seen:
            continue
        result.append(value)
        seen.add(slug)
        if len(result) >= limit:
            break
    return result


def _strong_motif(value: str) -> bool:
    slug = _identifier_slug(value)
    if not slug or _is_weak_motif_slug(slug):
        return False
    parts = set(slug.split("_"))
    if parts & _TECHNICAL_TOKEN_PARTS or parts & _GENERIC_TOKEN_PARTS:
        return False
    return True


def _known_theme_family_motifs(profile: ThemeProfile) -> dict[str, tuple[str, ...]]:
    label = _theme_label(profile).casefold()
    if "gta san andreas" in label:
        return {
            "condition": ("wanted level", "heat check", "safehouse plan"),
            "iteration": ("street route", "Grove Street", "next checkpoint"),
            "function": ("mission plan", "side job", "mission payout"),
            "output": ("radio callout", "phone contact", "crew message"),
            "data": ("garage stash", "crew profile", "safehouse inventory"),
            "oop": ("gang hierarchy", "crew blueprint", "safehouse blueprint"),
            "error": ("busted attempt", "wanted escape", "save file"),
        }
    if "counter-strike 2" in label or "counter strike 2" in label:
        return {
            "condition": ("clutch check", "round state", "angle check"),
            "iteration": ("site rotation", "map route", "next angle"),
            "function": ("utility lineup", "execute plan", "round result"),
            "output": ("team callout", "radio message", "mic check"),
            "data": ("buy menu", "loadout card", "grenade stack"),
            "oop": ("agent blueprint", "squad role", "team class"),
            "error": ("failed clutch", "missed smoke", "save round"),
        }
    if "minecraft" in label:
        return {
            "condition": ("redstone signal", "biome check", "spawn rule"),
            "iteration": ("minecart route", "chunk path", "next block"),
            "function": ("crafting recipe", "workbench plan", "crafted item"),
            "output": ("beacon signal", "chat message", "note block"),
            "data": ("inventory slots", "chest record", "item stack"),
            "oop": ("mob blueprint", "block type", "entity class"),
            "error": ("tool break", "creeper blast", "missing block"),
        }
    if "formula 1" in label:
        return {
            "condition": ("strategy check", "weather shift", "drs window"),
            "iteration": ("lap route", "sector cycle", "next corner"),
            "function": ("pit plan", "race strategy", "podium result"),
            "output": ("radio message", "pit wall", "timing screen"),
            "data": ("tyre set", "telemetry map", "garage setup"),
            "oop": ("car blueprint", "driver class", "team hierarchy"),
            "error": ("box mistake", "track limits", "engine fault"),
        }
    if "harry potter" in label:
        return {
            "condition": ("spell check", "house rule", "wand choice"),
            "iteration": ("hall patrol", "marauder map", "stair route"),
            "function": ("spell cast", "potion recipe", "charm lesson"),
            "output": ("owl message", "portrait whisper", "howler note"),
            "data": ("spellbook", "potion shelf", "house points"),
            "oop": ("wizard lineage", "house class", "wand blueprint"),
            "error": ("backfired spell", "broken wand", "forbidden corridor"),
        }
    if "witcher" in label:
        return {
            "condition": ("monster check", "curse sign", "contract clause"),
            "iteration": ("monster trail", "quest path", "next clue"),
            "function": ("sign cast", "witcher contract", "quest reward"),
            "output": ("quest notice", "tavern rumor", "bestiary note"),
            "data": ("alchemy kit", "inventory pouch", "bestiary"),
            "oop": ("school lineage", "monster type", "gear blueprint"),
            "error": ("failed sign", "toxic potion", "broken blade"),
        }
    if "philosopher" in label or "philosophy" in label:
        return {
            "condition": ("logic test", "premise check", "paradox gate"),
            "iteration": ("academy walk", "dialogue path", "next argument"),
            "function": ("argument method", "thesis result", "debate plan"),
            "output": ("dialogue voice", "public lecture", "written reply"),
            "data": ("scroll archive", "idea catalog", "library shelf"),
            "oop": ("school lineage", "thinker type", "academy blueprint"),
            "error": ("flawed proof", "false premise", "lost manuscript"),
        }
    domain_key = _domain_theme_key(label)
    if domain_key is not None:
        return _DOMAIN_FAMILY_MOTIFS[domain_key]
    return {}


def _profile_is_trusted(profile: ThemeProfile) -> bool:
    """Is the LLM profile the brain for this dictionary?

    Yes when the model really answered (not the deterministic fallback) and
    the answer carries at least one strong, non-filler motif. Then curated
    theme tables only fill gaps — whatever the user typed, the same LLM
    analysis drives the vocabulary. The tables lead only when the LLM failed
    outright or returned filler ("witcher evreniyle flow", "generic route").
    """
    if profile.source != "llm":
        return False
    family_hits = sum(
        1
        for family in ("condition", "iteration", "function", "output", "data", "oop", "error")
        if any(_strong_motif(motif) for motif in profile.family_motifs.get(family, ()))
    )
    if family_hits >= 4:
        return True

    strong_general = sum(1 for motif in profile.motifs if _strong_motif(motif))
    strong_preferences = sum(
        1 for motif in profile.concept_preferences.values() if _strong_motif(motif)
    )
    return strong_general >= 6 and strong_preferences >= 3


def _family_motifs(profile: ThemeProfile) -> dict[str, tuple[str, ...]]:
    known_families = _known_theme_family_motifs(profile)
    prefer_known = bool(known_families) and not _profile_is_trusted(profile)
    families = {
        family: list(motifs)
        for family, motifs in known_families.items()
    }
    lexicon_families = _lexicon_family_motifs(profile)
    for key, motifs in profile.family_motifs.items():
        family = _normalize_family_name(key)
        if family is None:
            continue
        cleaned = [motif for motif in motifs if _strong_motif(motif)]
        if cleaned:
            families.setdefault(family, [])
            if prefer_known:
                families[family].extend(
                    motif for motif in cleaned if motif not in families[family]
                )
            else:
                families[family] = cleaned + [
                    motif for motif in families[family] if motif not in cleaned
                ]
    for key, value in profile.concept_preferences.items():
        family = _normalize_family_name(key)
        if family is None:
            continue
        families.setdefault(family, [])
        if _strong_motif(value):
            if prefer_known:
                if value not in families[family]:
                    families[family].append(value)
            else:
                families[family].insert(0, value)
    if _profile_is_trusted(profile) and profile.domain_lexicon_source == "llm":
        for family, motifs in lexicon_families.items():
            cleaned = [motif for motif in motifs if _strong_motif(motif)]
            if not cleaned:
                continue
            families.setdefault(family, [])
            families[family] = cleaned + [
                motif for motif in families[family] if motif not in cleaned
            ]

    generic = tuple(profile.motifs)
    if generic:
        for index, family in enumerate(_CONCEPT_FAMILIES):
            families.setdefault(family, [])
            if not families[family]:
                offset = index % len(generic)
                families[family].extend(generic[offset:] + generic[:offset])
    return {family: tuple(values) for family, values in families.items()}


def _normalize_family_name(name: str) -> str | None:
    folded = name.casefold().strip()
    aliases = {
        "condition": "condition",
        "conditional": "condition",
        "branch": "condition",
        "control": "condition",
        "loop": "iteration",
        "iteration": "iteration",
        "route": "iteration",
        "function": "function",
        "return": "function",
        "ability": "function",
        "output": "output",
        "input": "output",
        "communication": "output",
        "collection": "data",
        "data": "data",
        "storage": "data",
        "type": "oop",
        "oop": "oop",
        "class": "oop",
        "error": "error",
        "file": "error",
        "exception": "error",
    }
    return aliases.get(folded)


def _identifier_slug(text: str) -> str:
    parts = _identifier_parts(text)
    # "shout of victory" -> "shout_victory" (drop connector words) and
    # "ship's log" -> "ship_log" (drop the stray 1-letter "s" left by the
    # apostrophe); neither carries theme meaning, so they never take a slot.
    strong = [
        part
        for part in parts
        if part not in _SLUG_CONNECTOR_WORDS and len(part) > 1
    ]
    return "_".join((strong or parts)[:2])


def _compact_slug(slug: str) -> str:
    parts = [part for part in slug.split("_") if part]
    for part in parts:
        if (
            part not in _SLUG_CONNECTOR_WORDS
            and part not in _GENERIC_TOKEN_PARTS
            and part not in _TECHNICAL_TOKEN_PARTS
            and not _is_weak_motif_slug(part)
        ):
            return part
    return parts[0] if len(parts) > 1 else slug


_SLUG_CONNECTOR_WORDS = frozenset(
    {"of", "the", "a", "an", "and", "or", "to", "in", "on", "ve", "ile", "bir"}
)


def _identifier_parts(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text).translate(_ASCII_TRANSLATION)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.findall(r"[a-z][a-z0-9]*", ascii_text)


def _unique_profile_token(
    profile: ThemeProfile,
    motif_slugs: tuple[str, ...],
    concept: MappableConcept,
    used_tokens: dict[str, str],
    all_canonical_names: set[str],
    reserved_preferred_tokens: dict[str, str] | None = None,
) -> str:
    semantic = _semantic_slug(concept.canonical_name)
    compact_semantic = _compact_slug(semantic)
    category = _identifier_slug(concept.category or concept.kind) or "concept"
    kind = _identifier_slug(concept.kind) or "code"
    motif = _motif_for_concept(motif_slugs, concept, profile)
    preferred_known = _preferred_known_token(profile, concept)
    role = _role_family_slug(concept)
    nearby_motif = motif_slugs[
        _stable_index(
            concept.canonical_name,
            concept.kind,
            concept.language,
            modulo=len(motif_slugs),
        )
    ]
    # Concepts with a curated motif hint (if/for/def/print/iter/... ~50 core
    # learning concepts) keep their hint-relevant motif up front. The long
    # tail (dict/list/set/str methods with no hint) instead SPREADS the whole
    # rich motif pool so siblings don't all re-stamp one family motif
    # (appointment_book_add_one, appointment_book_lookup, ...) — each gets a
    # distinct themed stem plus its meaning (mirror_lookup, fade_add_one).
    hinted = concept.canonical_name.casefold() in _CONCEPT_MOTIF_HINTS
    motif_first = (
        f"{motif}_{compact_semantic}",
        f"{motif}_{semantic}",
        motif,
        f"{motif}_{role}",
    )
    spread = _spread_motif_options(motif_slugs, concept, semantic, used_tokens)
    middle = (*motif_first, *spread) if hinted else (*spread, *motif_first)
    candidates = (
        preferred_known or "",
        # Core & flagship concepts grab their family's own motif first
        # (relevance): "if" -> client_request, "for" -> cutting_sequence.
        *_family_slug_options(profile, concept, motif_slugs),
        *middle,
        f"{role}_{motif}",
        f"{nearby_motif}_{compact_semantic}",
        f"{nearby_motif}_{role}",
        f"{semantic}_{motif}",
        f"{motif}_{category}_{semantic}",
        f"{nearby_motif}_{kind}_{semantic}",
        f"{category}_{motif}_{semantic}",
    )
    for candidate in candidates:
        token = _clean_identifier(candidate)
        if (
            token
            and not _reserved_for_other(token, concept, reserved_preferred_tokens)
            and _is_available_generated_token(token, used_tokens, all_canonical_names)
        ):
            used_tokens[_fold(token)] = concept.canonical_name
            return token

    base = _clean_identifier(f"{motif}_{category}_{kind}_{semantic}") or f"{motif}_token"
    token = base
    index = 2
    while (
        _reserved_for_other(token, concept, reserved_preferred_tokens)
        or not _is_available_generated_token(token, used_tokens, all_canonical_names)
    ):
        token = f"{base}_{index}"
        index += 1
    used_tokens[_fold(token)] = concept.canonical_name
    return token


def _spread_motif_options(
    motif_slugs: tuple[str, ...],
    concept: MappableConcept,
    semantic: str,
    used_tokens: dict[str, str],
) -> tuple[str, ...]:
    """Themed-stem candidates that rotate the FULL motif pool per concept.

    Each concept starts the rotation at its own stable offset, and motifs
    whose STEM is not yet used anywhere in this dictionary are offered first.
    So sibling long-tail methods land on different theme motifs instead of
    all reusing the family's single motif, and the pool is spent evenly
    rather than piling on the first motif. The semantic slug keeps the
    meaning, so a salon token still reads as "what it does":
    ``razor_add_one``, ``clipper_lookup``, ``fade_set_difference``.
    """
    if not motif_slugs:
        return ()
    total = len(motif_slugs)
    start = _stable_index(
        concept.canonical_name,
        concept.category,
        concept.kind,
        modulo=total,
    )
    rotated = [motif_slugs[(start + offset) % total] for offset in range(total)]
    used_stems = {token.split("_", 1)[0] for token in used_tokens}
    fresh = [m for m in rotated if m.split("_", 1)[0] not in used_stems]
    stale = [m for m in rotated if m.split("_", 1)[0] in used_stems]
    ordered = fresh + stale
    # meaning-carrying first ("mirror_lookup"), then the plain motif as a
    # looser fallback ("mirror").
    compact_semantic = _compact_slug(semantic)
    return (
        *(f"{motif}_{compact_semantic}" for motif in ordered),
        *(f"{motif}_{semantic}" for motif in ordered),
        *ordered,
    )


def _family_slug_options(
    profile: ThemeProfile,
    concept: MappableConcept,
    motif_slugs: tuple[str, ...],
) -> tuple[str, ...]:
    """Ordered plain-token candidates from the concept's own motif family.

    Offering every strong family motif (not just the first) lets siblings
    like if/elif/else each claim their own motif instead of piling suffix
    combos onto a single stem.
    """
    family = _concept_family(concept)
    if family == "general":
        return ()
    options: list[str] = []
    for motif in _family_motifs(profile).get(family, ()):
        slug = _identifier_slug(motif)
        if slug and slug in motif_slugs and slug not in options:
            options.append(slug)
    return tuple(options)


def _semantic_slug(canonical_name: str) -> str:
    folded = canonical_name.casefold()
    if folded in _SEMANTIC_SLUGS:
        return _SEMANTIC_SLUGS[folded]
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", canonical_name)
    token = re.sub(r"[^A-Za-z0-9_]+", "_", snake).strip("_").lower()
    return _clean_identifier(token) or "concept"


def _stable_index(*parts: str, modulo: int) -> int:
    seed = "|".join(parts)
    total = sum((index + 1) * ord(char) for index, char in enumerate(seed))
    return total % modulo


def _clean_identifier(token: str) -> str:
    cleaned = re.sub(r"_+", "_", token.strip("_").lower())
    if not cleaned:
        return ""
    if not re.match(r"^[a-z_]", cleaned):
        cleaned = f"theme_{cleaned}"
    return cleaned


def _is_available_generated_token(
    token: str,
    used_tokens: dict[str, str],
    all_canonical_names: set[str],
) -> bool:
    folded = _fold(token)
    return folded not in used_tokens and folded not in all_canonical_names


#: each concept family's flagship learning concepts, strongest-first — on the
#: trusted LLM path the family's k-th strong motif is reserved for the k-th
#: present flagship, so alphabetically earlier family members ("and",
#: "break", ...) can't claim the best names first and siblings like elif/else
#: get their own motifs instead of generic suffix combos on if's motif.
_FLAGSHIP_CONCEPTS: dict[str, tuple[str, ...]] = {
    "condition": ("if", "elif", "else"),
    "iteration": ("for", "range", "while", "iter", "next"),
    "function": ("def", "return"),
    "output": ("print", "input"),
    "data": ("dict", "list"),
    "oop": ("class",),
    "error": ("try", "except"),
}


def _reserved_preferred_tokens(
    profile: ThemeProfile,
    batches: list[_TaxonomyBatch],
) -> dict[str, str]:
    reserved: dict[str, str] = {}
    if _profile_is_trusted(profile):
        present = {
            concept.canonical_name.casefold()
            for batch in batches
            for concept in batch.concepts
        }
        family_map = _family_motifs(profile)
        for family, flagships in _FLAGSHIP_CONCEPTS.items():
            waiting = [name for name in flagships if name in present]
            for motif in family_map.get(family, ()):
                if not waiting:
                    break
                slug = _identifier_slug(motif)
                if (
                    slug
                    and not _is_weak_motif_slug(slug)
                    and _fold(slug) not in reserved
                ):
                    reserved[_fold(slug)] = waiting.pop(0)
        return reserved
    for batch in batches:
        for concept in batch.concepts:
            token = _preferred_known_token(profile, concept)
            if token:
                reserved[_fold(token)] = concept.canonical_name.casefold()
    return reserved


def _reserved_for_other(
    token: str,
    concept: MappableConcept,
    reserved_preferred_tokens: dict[str, str] | None,
) -> bool:
    if not reserved_preferred_tokens:
        return False
    owner = reserved_preferred_tokens.get(_fold(token))
    return owner is not None and owner != concept.canonical_name.casefold()


def _repair_mapping_quality(
    profile: ThemeProfile,
    concept: MappableConcept,
    token: str,
    rationale: str,
    used_tokens: dict[str, str],
    all_canonical_names: set[str],
    reserved_preferred_tokens: dict[str, str] | None = None,
) -> tuple[str, str]:
    if not _quality_issues(profile, concept, token, rationale, all_canonical_names):
        return token, rationale

    original_key = _fold(token)
    original_owner = used_tokens.get(original_key)
    if original_owner == concept.canonical_name:
        used_tokens.pop(original_key)

    motif_slugs = _profile_motif_slugs(profile, profile.clean_theme or profile.theme)
    semantic = _semantic_slug(concept.canonical_name)
    compact_semantic = _compact_slug(semantic)
    compact_cue = _COMPACT_ROLE_CUES.get(concept.canonical_name.casefold(), compact_semantic)
    preferred_motif = _motif_for_concept(motif_slugs, concept, profile)
    preferred_known = _preferred_known_token(profile, concept)
    grounding_motifs: Iterable[str] = motif_slugs
    if _profile_is_trusted(profile):
        if profile.domain_lexicon_source == "llm":
            grounding_motifs = (
                word
                for words in profile.domain_lexicon.values()
                for word in words
            )
        else:
            anchor_parts = set(
                _identifier_parts(
                    f"{profile.clean_theme} {profile.primary_world}"
                )
            )
            anchored = tuple(
                motif
                for motif in profile.motifs
                if _compact_slug(_identifier_slug(motif)) in anchor_parts
            )
            grounding_motifs = anchored or profile.motifs[:8]
    primary_motifs = tuple(
        dict.fromkeys(
            compact
            for motif in grounding_motifs
            if (compact := _compact_slug(_identifier_slug(motif)))
        )
    )
    fallback_motifs = tuple(
        motif
        for motif in dict.fromkeys(_compact_slug(item) for item in motif_slugs)
        if motif not in primary_motifs
    )

    def rotated(values: tuple[str, ...], salt: str) -> tuple[str, ...]:
        if not values:
            return ()
        start = _stable_index(
            concept.canonical_name,
            concept.category,
            concept.kind,
            salt,
            modulo=len(values),
        )
        return tuple(
            values[(start + offset) % len(values)]
            for offset in range(len(values))
        )
    compact_motifs = rotated(primary_motifs, "primary") + rotated(
        fallback_motifs, "fallback"
    )
    candidates = [
        preferred_known or "",
        _compact_slug(preferred_known or ""),
        *(f"{motif}_{compact_cue}" for motif in compact_motifs),
        *(f"{motif}_{compact_semantic}" for motif in compact_motifs),
        _compact_slug(preferred_motif),
        *compact_motifs,
        preferred_motif,
        f"{preferred_motif}_{compact_semantic}",
        f"{preferred_motif}_{semantic}",
        f"{preferred_motif}_{_role_family_slug(concept)}",
        f"{_role_family_slug(concept)}_{preferred_motif}",
    ]
    for candidate in candidates:
        repaired = _clean_identifier(candidate)
        if (
            repaired
            and not _reserved_for_other(repaired, concept, reserved_preferred_tokens)
            and _is_available_generated_token(repaired, used_tokens, all_canonical_names)
            and not _quality_issues(
                profile,
                concept,
                repaired,
                _profile_rationale(profile, concept, repaired),
                all_canonical_names,
            )
        ):
            used_tokens[_fold(repaired)] = concept.canonical_name
            return repaired, _profile_rationale(profile, concept, repaired)

    if original_owner == concept.canonical_name:
        used_tokens[original_key] = original_owner
    return token, _profile_rationale(profile, concept, token)


def _quality_issues(
    profile: ThemeProfile,
    concept: MappableConcept,
    token: str,
    rationale: str,
    all_canonical_names: set[str],
) -> list[str]:
    issues: list[str] = []
    folded_token = _fold(token)
    folded_name = concept.canonical_name.casefold()
    raw_prompt = profile.theme.casefold()
    rationale_folded = rationale.casefold()

    # Aligned with validate_personal_python_dictionary_quality: any concept
    # whose ids fall in the gate's compact set gets the same 16-char budget
    # here, so generation can never emit a token the final gate would reject.
    compact_learning_token = folded_name in _COMPACT_LEARNING_CONCEPTS or any(
        concept_id in PERSONAL_PYTHON_COMPACT_IDS for concept_id in concept.concept_ids
    )
    python_token = concept.language == "python"
    max_parts = 2 if python_token else 3
    max_length = 16 if compact_learning_token else (20 if python_token else 36)
    if not token or len(token.split("_")) > max_parts or len(token) > max_length:
        issues.append("token too long")
    if folded_token in all_canonical_names or folded_token == folded_name:
        issues.append("copies canonical name")
    token_parts = set(folded_token.split("_"))
    token_part_list = folded_token.split("_")
    if len(set(token_part_list)) < len(token_part_list):
        issues.append("repeated token part")
    if token_parts & _TECHNICAL_TOKEN_PARTS:
        issues.append("technical token part")
    if token_parts & _GENERIC_TOKEN_PARTS:
        issues.append("generic token part")
    required_cue = _COMPACT_ROLE_CUES.get(folded_name)
    if (
        python_token
        and not compact_learning_token
        and required_cue
        and required_cue not in token_parts
    ):
        issues.append("weak Python behavior cue")
    if any(bad in folded_token for bad in _BAD_TOKEN_SUBSTRINGS):
        issues.append("generic token substring")
    if (
        folded_name in token_parts
        or (folded_name == "iter" and "iter" in folded_token)
        or (folded_name == "dict" and "dictionary" in token_parts)
    ) and (
        folded_name in _COMPACT_LEARNING_CONCEPTS
        and folded_name not in _ALLOWED_SEMANTIC_NAME_PARTS
    ):
        issues.append("blindly appends canonical name")
    if raw_prompt and len(raw_prompt) > 20 and raw_prompt in rationale_folded:
        issues.append("rationale includes raw prompt")
    if (
        folded_name in _CRITICAL_PYTHON_CONCEPTS
        and _known_theme_motifs(profile)
        and not _token_uses_known_theme_anchor(profile, concept, folded_token)
    ):
        issues.append("weak theme anchor")
    for phrase in _BANNED_RATIONALE_PHRASES:
        if phrase in rationale_folded:
            issues.append("generic rationale")
            break
    if "specific name" in rationale_folded:
        issues.append("generic name rationale")
    return issues


def _token_uses_known_theme_anchor(
    profile: ThemeProfile,
    concept: MappableConcept,
    folded_token: str,
) -> bool:
    token_parts = set(folded_token.split("_"))
    family = _concept_family(concept)
    for motif in _family_motifs(profile).get(family, ()):
        motif_slug = _identifier_slug(motif)
        motif_parts = {part for part in motif_slug.split("_") if len(part) >= 4}
        if token_parts & motif_parts:
            return True

    motif_slugs = tuple(_identifier_slug(motif) for motif in _known_theme_motifs(profile))
    role_hints = _CONCEPT_MOTIF_HINTS.get(concept.canonical_name.casefold(), ())
    for motif in motif_slugs:
        motif_parts = {part for part in motif.split("_") if len(part) >= 4}
        if token_parts & motif_parts:
            if not role_hints or any(hint in motif for hint in role_hints):
                return True
    return False


def _preferred_known_token(profile: ThemeProfile, concept: MappableConcept) -> str | None:
    # Curated core tokens are the backup plan only: while the LLM profile is
    # trusted, every token derives from that profile instead.
    if _profile_is_trusted(profile):
        return None
    label = _theme_label(profile).casefold()
    name = concept.canonical_name.casefold()
    theme_key = _curated_theme_key(label)
    if theme_key:
        token = _CURATED_CORE_TOKENS.get(theme_key, {}).get(name)
        if token:
            return token
    return None


def _curated_theme_key(label: str) -> str | None:
    if "gta san andreas" in label:
        return "gta"
    if "counter-strike 2" in label or "counter strike 2" in label or "cs2" in label:
        return "cs2"
    if "minecraft" in label:
        return "minecraft"
    if "formula 1" in label or label == "f1":
        return "formula1"
    if "harry potter" in label or "hogwarts" in label:
        return "harry_potter"
    if "witcher" in label:
        return "witcher"
    if "philosopher" in label or "philosophy" in label:
        return "philosophers"
    domain_key = _domain_theme_key(label)
    if domain_key is not None:
        return domain_key
    return None


def _profile_rationale(
    profile: ThemeProfile,
    concept: MappableConcept,
    token: str,
) -> str:
    motif = _token_motif_label(profile, token)
    folded = concept.canonical_name.casefold()
    if folded in _RATIONALE_TEMPLATES:
        return _RATIONALE_TEMPLATES[folded].format(motif=motif, theme=_theme_label(profile))
    if concept.language == "python" and concept.hint.strip():
        hint = re.sub(
            rf"^Represents the Python (?:built-in|keyword|method) [`']?{re.escape(concept.canonical_name)}(?:\(\))?[`']?,?\s*which\s*",
            "",
            concept.hint.strip(),
            flags=re.IGNORECASE,
        ).rstrip(".")
        return f"{motif} is the memory cue for the operation that {hint}."
    family = _concept_family(concept)
    return _family_rationale(family, motif, concept.canonical_name)


def _family_rationale(family: str, motif: str, canonical_name: str) -> str:
    if family == "condition":
        return f"{motif} marks the decision point for this branch."
    if family == "iteration":
        return f"{motif} frames the step-by-step path through repeated items."
    if family == "function":
        return f"{motif} represents a reusable action and its result."
    if family == "output":
        return f"{motif} represents sending information to or from the user."
    if family == "data":
        return f"{motif} represents storing, finding, or changing grouped values."
    if family == "oop":
        return f"{motif} represents object shape, type, or inheritance."
    if family == "error":
        return f"{motif} represents handling files, failures, or cleanup."
    return f"{motif} is the memory cue for Python's {canonical_name} concept."


def _humanize_token(token: str) -> str:
    return token.replace("_", " ").strip() or "theme motif"


def _token_motif_label(profile: ThemeProfile, token: str) -> str:
    motif_slugs = sorted(
        _profile_motif_slugs(profile, profile.theme),
        key=len,
        reverse=True,
    )
    for slug in motif_slugs:
        if token == slug or token.startswith(f"{slug}_"):
            return _humanize_token(slug)
    return _humanize_token(token.split("_", maxsplit=1)[0])


def _theme_label(theme: ThemeProfile | str) -> str:
    if isinstance(theme, ThemeProfile):
        # A trusted LLM profile names its own world ("One Piece", "Barbering");
        # domain tables only label fallback/weak profiles — otherwise they
        # would flatten specific worlds into broad categories ("Anime").
        if _profile_is_trusted(theme) and theme.clean_theme.strip():
            return " ".join(theme.clean_theme.split()).strip()
        combined = " ".join(
            part
            for part in (
                theme.clean_theme,
                theme.primary_world,
                theme.theme,
                theme.learner_summary,
            )
            if part
        )
        known_label = _known_theme_label(combined)
        if known_label:
            return known_label
        theme = theme.clean_theme or theme.primary_world or theme.theme
    cleaned = " ".join(str(theme).split()).strip()
    known_label = _known_theme_label(cleaned)
    if known_label:
        return known_label
    folded = cleaned.casefold()
    domain_key = _domain_theme_key(folded)
    if domain_key:
        return _DOMAIN_LABELS.get(domain_key, domain_key.replace("_", " ").title())
    ascii_folded = (
        unicodedata.normalize("NFKD", cleaned)
        .translate(_ASCII_TRANSLATION)
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
    )
    domain_key = _domain_theme_key(ascii_folded)
    if domain_key:
        return _DOMAIN_LABELS.get(domain_key, domain_key.replace("_", " ").title())
    if "felsefe" in ascii_folded or "sokrates" in ascii_folded:
        return "Philosophers"
    if "ucak" in ascii_folded or "uçak" in folded:
        return "Aviation"
    known = (
        ("gta san andreas", "GTA San Andreas"),
        ("grand theft auto san andreas", "GTA San Andreas"),
        ("gta 6", "GTA 6"),
        ("grand theft auto 6", "GTA 6"),
        ("witcher 3", "The Witcher 3"),
        ("philosophers", "Philosophers"),
        ("philosophy", "Philosophy"),
        ("valorant", "Valorant"),
    )
    for needle, label in known:
        if needle in folded:
            return label
    filler_patterns = (
        r"\bi love playing\b",
        r"\bi like playing\b",
        r"\boynamayi seviyorum\b",
        r"\boynamayı seviyorum\b",
        r"\boyununu\b",
        r"\bseviyorum\b",
    )
    ascii_cleaned = unicodedata.normalize("NFKD", cleaned).translate(_ASCII_TRANSLATION)
    ascii_cleaned = ascii_cleaned.encode("ascii", "ignore").decode("ascii")
    for pattern in filler_patterns:
        ascii_cleaned = re.sub(pattern, "", ascii_cleaned, flags=re.IGNORECASE)
    label = " ".join(ascii_cleaned.split()).strip(" -_.,")
    return label.title() if label else "the theme"


def _known_theme_label(text: str) -> str | None:
    folded = str(text).casefold()
    ascii_folded = (
        unicodedata.normalize("NFKD", str(text))
        .translate(_ASCII_TRANSLATION)
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
    )
    haystack = f"{folded} {ascii_folded}"
    known = (
        (("gta san andreas", "grand theft auto san andreas", "grove street"), "GTA San Andreas"),
        (("counter-strike 2", "counter strike 2", "cs2"), "Counter-Strike 2"),
        (("minecraft", "redstone", "minecart"), "Minecraft"),
        (("formula 1", "formula one", "f1", "pit stop"), "Formula 1"),
        (("harry potter", "hogwarts"), "Harry Potter"),
        (("witcher", "geralt", "rivia", "kaer morhen"), "The Witcher 3"),
        (("philosopher", "philosophy", "socrates", "plato", "felsefe", "sokrates"), "Philosophers"),
    )
    for needles, label in known:
        if any(needle in haystack for needle in needles):
            return label
    return None


def _motif_for_concept(
    motif_slugs: tuple[str, ...],
    concept: MappableConcept,
    profile: ThemeProfile | None = None,
) -> str:
    if profile is not None:
        family = _concept_family(concept)
        if family != "general":
            family_slugs = tuple(
                slug
                for motif in _family_motifs(profile).get(family, ())
                if (slug := _identifier_slug(motif))
                and not _is_weak_motif_slug(slug)
            )
            for motif in family_slugs:
                if motif in motif_slugs:
                    return motif
    preferred = _CONCEPT_MOTIF_HINTS.get(concept.canonical_name.casefold(), ())
    for hint in preferred:
        for motif in motif_slugs:
            if hint in motif:
                return motif
    return motif_slugs[
        _stable_index(
            concept.language,
            concept.category,
            concept.kind,
            concept.canonical_name,
            modulo=len(motif_slugs),
        )
    ]


def _role_family_slug(concept: MappableConcept) -> str:
    family = _concept_family(concept)
    if family == "iteration":
        return "route"
    if family == "function":
        return "ability"
    if family == "data":
        return "stash"
    if family == "output":
        return "signal"
    if family == "oop":
        return "blueprint"
    if family == "error":
        return "handle"
    if family == "condition":
        return "flow"
    return "concept"


def _concept_family(concept: MappableConcept) -> str:
    """Route EVERY concept to a Python-role family — never randomly.

    Precedence: explicit name sets first (the critical ~50), then kind/
    category fallbacks so the remaining ~160 mappable concepts (string
    methods, numeric builtins, exceptions, ...) still land in a semantically
    matching motif family instead of "general" noise.
    """
    folded = concept.canonical_name.casefold()
    if folded in _FUNCTION_CONCEPTS:
        return "function"
    if folded in _ITERATION_CONCEPTS or folded in {"for", "while"}:
        return "iteration"
    if folded in _COLLECTION_CONCEPTS:
        return "data"
    if folded in _OUTPUT_INPUT_CONCEPTS:
        return "output"
    if folded in _OOP_TYPE_CONCEPTS:
        return "oop"
    if folded in _FILE_ERROR_CONCEPTS:
        return "error"
    if folded in _CONTROL_FLOW_CONCEPTS:
        return "condition"
    if folded in _LOGIC_VALUE_CONCEPTS:
        return "condition"

    # ---- kind/category fallbacks (the deepening layer) ----
    if concept.kind == "exception":
        return "error"
    category = (concept.category or "").casefold()
    if category in _DATA_METHOD_CATEGORIES:
        return "data"
    if category == "file_methods":
        return "error"  # file handling shares the risk/recovery family
    if concept.kind == "builtin":
        # remaining builtins (abs, round, sum, sorted, hash, repr, ...) all
        # take a value and produce a value — the record/inventory family
        # reads most naturally for them
        return "data"
    return "general"


#: logical operators & truth literals — decisions, so: condition family
_LOGIC_VALUE_CONCEPTS = frozenset({"and", "or", "not", "is", "true", "false", "none", "bool"})

_DATA_METHOD_CATEGORIES = frozenset(
    {"string_methods", "list_methods", "dict_methods", "set_methods", "tuple_methods"}
)


_ASCII_TRANSLATION = str.maketrans(
    {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "İ": "I",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "Ç": "C",
        "Ğ": "G",
        "Ö": "O",
        "Ş": "S",
        "Ü": "U",
    }
)


_SEMANTIC_SLUGS: dict[str, str] = {
    "abs": "mutlak_deger",
    "add": "ekle",
    "all": "hepsi",
    "alter_database": "veritabani_degistir",
    "alter_table": "tablo_degistir",
    "and": "ve",
    "any": "herhangi",
    "append": "sona_ekle",
    "as": "takma_ad",
    "assert": "dogrula",
    "async": "es_zamansiz",
    "await": "bekle",
    "avg": "ortalama",
    "between": "aralikta",
    "bool": "mantik_degeri",
    "break": "donguyu_kir",
    "case": "durum",
    "cast": "tipe_cevir",
    "check": "kontrol",
    "class": "sinif",
    "clear": "temizle",
    "close": "kapat",
    "commit": "onayla",
    "continue": "devam_et",
    "copy": "kopyala",
    "count": "say",
    "create_database": "veritabani_kur",
    "create_index": "indeks_kur",
    "create_table": "tablo_kur",
    "create_view": "gorunum_kur",
    "def": "islev_tanimla",
    "del": "sil",
    "delete": "kayit_sil",
    "dict": "sozluk",
    "distinct": "benzersiz",
    "drop": "dusur",
    "drop_database": "veritabani_sil",
    "drop_index": "indeks_sil",
    "drop_table": "tablo_sil",
    "drop_view": "gorunum_sil",
    "elif": "degilse_kosul",
    "else": "degilse",
    "except": "yakala",
    "execute": "calistir",
    "exists": "var_mi",
    "false": "yanlis",
    "fetchall": "hepsini_getir",
    "fetchone": "birini_getir",
    "filter": "suz",
    "finally": "sonunda",
    "float": "ondalik",
    "for": "dongu",
    "from": "kaynaktan",
    "fromkeys": "anahtarlardan",
    "get": "al",
    "global": "genel",
    "group_by": "gruplandir",
    "having": "grup_kosulu",
    "if": "kosul",
    "import": "ice_aktar",
    "in": "icinde",
    "inner_join": "ic_bagla",
    "input": "girdi_al",
    "insert_into": "kayit_ekle",
    "int": "tam_sayi",
    "is": "aynisi_mi",
    "is_not_null": "bos_degil",
    "is_null": "bos_mu",
    "isinstance": "tur_kontrol",
    "issubclass": "miras_kontrol",
    "items": "ogeler",
    "join": "birlestir",
    "keys": "anahtarlar",
    "lambda": "isimsiz_islev",
    "left_join": "sol_bagla",
    "len": "uzunluk",
    "like": "benzer",
    "list": "liste",
    "lower": "kucult",
    "match": "eslestir",
    "max": "en_buyuk",
    "min": "en_kucuk",
    "nonlocal": "dis_kapsam",
    "none": "bos_deger",
    "not": "degil",
    "not_null": "bos_olmaz",
    "or": "veya",
    "order_by": "sirala",
    "pop": "cek_cikar",
    "print": "yazdir",
    "primary_key": "ana_anahtar",
    "raise": "hata_yukselt",
    "range": "aralik",
    "remove": "kaldir",
    "replace": "degistir",
    "return": "geri_ver",
    "right_join": "sag_bagla",
    "rollback": "geri_al",
    "round": "yuvarla",
    "select": "sec",
    "set": "kume",
    "sort": "sirala",
    "split": "parcala",
    "str": "metin",
    "sum": "topla",
    "true": "dogru",
    "truncate_table": "tabloyu_bosalt",
    "try": "dene",
    "tuple": "demet",
    "union": "birlesim",
    "unique": "tekil",
    "update": "guncelle",
    "upper": "buyut",
    "values": "degerler",
    "where": "kosul_suzgeci",
    "while": "suredongu",
    "with": "baglam",
    "yield": "uret",
}


_KIND_LABELS: dict[str, str] = {
    "keyword": "dil yapısı",
    "builtin": "hazır işlev",
    "method": "nesne/metot işlemi",
    "exception": "hata türü",
    "function": "SQL işlevi",
}


_RATIONALE_TEMPLATES: dict[str, str] = {
    "def": "{motif} defines a reusable ability in the {theme} world",
    "return": "{motif} carries the result back once the action completes",
    "yield": "{motif} hands out the next value while the flow keeps going",
    "if": "{motif} steps in when a specific condition holds",
    "elif": "{motif} tries the alternative case when the first check fails",
    "else": "{motif} opens the remaining path when no condition holds",
    "for": "{motif} visits the items of a collection one by one",
    "in": "{motif} tells whether an item belongs to a collection",
    "while": "{motif} keeps going as long as the condition stays true",
    "break": "{motif} ends the ongoing flow immediately",
    "continue": "{motif} skips the current step and moves to the next one",
    "class": "{motif} sets up a shared blueprint for objects",
    "import": "{motif} brings an outside tool into the scene",
    "try": "{motif} attempts the risky move in a controlled way",
    "except": "{motif} catches the failed move and handles it",
    "finally": "{motif} runs the final cleanup no matter the outcome",
    "and": "{motif} requires both conditions to be true together",
    "or": "{motif} lets any one of the alternatives be enough",
    "not": "{motif} checks the opposite of the condition",
    "True": "{motif} stands for the yes/active decision",
    "False": "{motif} stands for the no/inactive decision",
    "None": "{motif} stands for a deliberate blank or absence",
    "print": "{motif} announces the result out loud",
    "range": "{motif} lays out a numeric span to travel through",
    "len": "{motif} measures how many items something holds",
    "append": "{motif} adds a new piece to the end of the list",
    "remove": "{motif} takes the target piece out of the collection",
    "get": "{motif} safely fetches the value behind a key",
    "keys": "{motif} reveals every key stored in the mapping",
    "values": "{motif} shows every value stored in the mapping",
    "select": "{motif} picks the requested data from the table",
    "where": "{motif} filters the query down to a condition",
    "left_join": "{motif} links tables while keeping every left-side row",
    "right_join": "{motif} links tables while keeping every right-side row",
    "inner_join": "{motif} combines only the rows that match",
    "count": "{motif} counts the matching rows or items",
    "sum": "{motif} adds the values into a single total",
    "avg": "{motif} works out the average of the values",
    "min": "{motif} finds the smallest value",
    "max": "{motif} finds the largest value",
    "group_by": "{motif} groups records by a shared property",
    "order_by": "{motif} arranges the result in the chosen order",
    "insert_into": "{motif} adds a new record to the table",
    "update": "{motif} refreshes an existing record with new values",
    "delete": "{motif} removes the target record from the table",
    "create_table": "{motif} builds a brand-new table structure",
    "drop_table": "{motif} removes the table entirely",
    "alter_table": "{motif} reshapes the table's structure",
    "primary_key": "{motif} is the mark that uniquely identifies a record",
    "not_null": "{motif} says the field can never be left empty",
    "unique": "{motif} forces the value to stay one of a kind",
}




_WEAK_MOTIF_SLUGS = frozenset(
    {
        "theme",
        "tone",
        "epic",
        "gritty",
        "dark",
        "light",
        "story",
        "world",
        "game",
        "final",
        "quality",
        "code",
        "concept",
        "system",
        "style",
        "run_test",
        "test_run",
    }
)

_WEAK_MOTIF_PARTS = frozenset(
    {
        "generic",
        "python",
        "syntax",
        "token",
        "code",
        "coding",
        "program",
        "variable",
        "helper",
        "statement",
        "script",
        "theme",
        "specific",
        "evren",
        "evreni",
        "evreniyle",
        "olustur",
        "olusturmak",
        "seviyorum",
        "karisik",
    }
)


_SEMANTIC_SLUGS.update(
    {
        "abs": "absolute_value",
        "add": "add_item",
        "all": "all_true",
        "alter_database": "alter_database",
        "alter_table": "alter_table",
        "and": "and_gate",
        "any": "any_true",
        "append": "append_item",
        "as": "alias_as",
        "assert": "assert_check",
        "async": "async_task",
        "await": "await_result",
        "avg": "average",
        "between": "between_range",
        "bool": "boolean",
        "break": "break_loop",
        "case": "case_branch",
        "cast": "cast_type",
        "check": "check_rule",
        "class": "class_blueprint",
        "clear": "clear_all",
        "close": "close_handle",
        "commit": "commit_changes",
        "continue": "skip_step",
        "copy": "copy_value",
        "count": "count_items",
        "create_database": "create_database",
        "create_index": "create_index",
        "create_table": "create_table",
        "create_view": "create_view",
        "def": "define_function",
        "del": "delete_name",
        "delete": "delete_rows",
        "dict": "dictionary",
        "distinct": "distinct_rows",
        "drop": "drop_object",
        "drop_database": "drop_database",
        "drop_index": "drop_index",
        "drop_table": "drop_table",
        "drop_view": "drop_view",
        "elif": "else_if_branch",
        "else": "fallback_branch",
        "except": "catch_error",
        "execute": "execute_query",
        "exists": "exists_check",
        "false": "false_value",
        "fetchall": "fetch_all",
        "fetchone": "fetch_one",
        "filter": "filter_items",
        "finally": "final_cleanup",
        "float": "float_number",
        "for": "for_loop",
        "from": "from_source",
        "fromkeys": "from_keys",
        "get": "get_value",
        "global": "global_scope",
        "group_by": "group_rows",
        "having": "group_filter",
        "if": "condition_branch",
        "import": "import_module",
        "in": "inside_check",
        "inner_join": "inner_join",
        "input": "read_input",
        "insert_into": "insert_rows",
        "int": "integer",
        "is": "identity_check",
        "is_not_null": "not_null_check",
        "is_null": "null_check",
        "isinstance": "type_check",
        "issubclass": "inheritance_check",
        "items": "key_value_items",
        "join": "join_values",
        "keys": "dictionary_keys",
        "lambda": "anonymous_function",
        "left_join": "left_join",
        "len": "length_count",
        "like": "pattern_match",
        "list": "list_value",
        "lower": "lowercase",
        "match": "pattern_switch",
        "max": "maximum",
        "min": "minimum",
        "nonlocal": "outer_scope",
        "none": "empty_value",
        "not": "negate_condition",
        "not_null": "not_null",
        "or": "or_gate",
        "order_by": "sort_rows",
        "pop": "pop_item",
        "print": "print_output",
        "primary_key": "primary_key",
        "raise": "raise_error",
        "range": "number_range",
        "remove": "remove_item",
        "replace": "replace_text",
        "return": "return_value",
        "right_join": "right_join",
        "rollback": "rollback_changes",
        "round": "round_number",
        "select": "select_rows",
        "set": "set_value",
        "sort": "sort_items",
        "split": "split_text",
        "str": "string_value",
        "sum": "sum_values",
        "true": "true_value",
        "truncate_table": "truncate_table",
        "try": "try_block",
        "tuple": "tuple_value",
        "union": "union_rows",
        "unique": "unique_rule",
        "update": "update_rows",
        "upper": "uppercase",
        "values": "dictionary_values",
        "where": "filter_rows",
        "while": "while_loop",
        "with": "context_block",
        "yield": "yield_value",
    }
)


_KIND_LABELS = {
    "keyword": "language construct",
    "builtin": "built-in function",
    "method": "method operation",
    "exception": "exception type",
    "function": "SQL function",
}


_RATIONALE_TEMPLATES = {
    "def": "Uses {motif} as the theme image for defining a reusable ability.",
    "return": "Uses {motif} as the payout/result that comes back from a call.",
    "yield": "Uses {motif} for releasing the next value while a sequence continues.",
    "if": "Uses {motif} for a branch that opens only when a condition is true.",
    "elif": "Uses {motif} for checking the next branch after the first condition fails.",
    "else": "Uses {motif} for the fallback path when no earlier condition matches.",
    "for": "Uses {motif} as a route through each item in a collection.",
    "in": "Uses {motif} for checking whether an item belongs inside a collection.",
    "while": "Uses {motif} for a loop that keeps running while its condition holds.",
    "break": "Uses {motif} for cutting the current loop short.",
    "continue": "Uses {motif} for skipping the current pass and moving ahead.",
    "class": "Uses {motif} as the blueprint for related objects.",
    "import": "Uses {motif} for calling an outside module into the program.",
    "try": "Uses {motif} for a risky block that may fail.",
    "except": "Uses {motif} for catching and handling a failed block.",
    "finally": "Uses {motif} for cleanup that runs after success or failure.",
    "and": "Uses {motif} for requiring both sides of a condition.",
    "or": "Uses {motif} for accepting either side of a condition.",
    "not": "Uses {motif} for flipping a condition to its opposite.",
    "True": "Uses {motif} for an affirmative boolean state.",
    "False": "Uses {motif} for a negative boolean state.",
    "None": "Uses {motif} for an intentional empty value.",
    "print": "Uses {motif} for sending a value to visible output.",
    "range": "Uses {motif} as a numeric route for iteration.",
    "len": "Uses {motif} for measuring how many items or characters exist.",
    "append": "Uses {motif} for adding one new item to the end of a list.",
    "remove": "Uses {motif} for removing a chosen item from a collection.",
    "get": "Uses {motif} for retrieving a value by key without forcing a crash.",
    "keys": "Uses {motif} for exposing every key in a dictionary.",
    "values": "Uses {motif} for exposing every stored value in a dictionary.",
    "select": "Uses {motif} for choosing which rows or columns to read.",
    "where": "Uses {motif} for filtering rows by a condition.",
    "left_join": "Uses {motif} for joining tables while preserving left-side rows.",
    "right_join": "Uses {motif} for joining tables while preserving right-side rows.",
    "inner_join": "Uses {motif} for keeping only rows that match on both sides.",
    "count": "Uses {motif} for counting matching rows or items.",
    "sum": "Uses {motif} for combining numeric values into one total.",
    "avg": "Uses {motif} for calculating the average of matching values.",
    "min": "Uses {motif} for finding the smallest matching value.",
    "max": "Uses {motif} for finding the largest matching value.",
    "group_by": "Uses {motif} for gathering rows into shared groups.",
    "order_by": "Uses {motif} for arranging results in a chosen order.",
    "insert_into": "Uses {motif} for adding new rows to a table.",
    "update": "Uses {motif} for changing existing rows.",
    "delete": "Uses {motif} for removing matching rows.",
    "create_table": "Uses {motif} for building a new table shape.",
    "drop_table": "Uses {motif} for removing a table completely.",
    "alter_table": "Uses {motif} for changing an existing table shape.",
    "primary_key": "Uses {motif} for uniquely identifying each row.",
    "not_null": "Uses {motif} for preventing a field from being empty.",
    "unique": "Uses {motif} for forcing values to stay distinct.",
}


_SEMANTIC_SLUGS.update(
    {
        "def": "ability",
        "return": "payout",
        "yield": "drop",
        "if": "trigger",
        "elif": "second_trigger",
        "else": "fallback",
        "for": "route",
        "in": "inside",
        "while": "ongoing_loop",
        "break": "abort",
        "continue": "skip_ahead",
        "class": "blueprint",
        "import": "call_in",
        "try": "risky_move",
        "except": "recovery",
        "finally": "cleanup",
        "and": "combo",
        "or": "choice",
        "not": "denial",
        "true": "confirmed",
        "false": "rejected",
        "none": "empty",
        "print": "broadcast",
        "range": "route_range",
        "len": "headcount",
        "append": "add_one",
        "remove": "remove_one",
        "get": "lookup",
        "keys": "keyring",
        "values": "stash",
        "isinstance": "type_scan",
        "issubclass": "lineage_scan",
        "select": "pick_rows",
        "where": "screen_rows",
        "left_join": "left_link",
        "right_join": "right_link",
        "inner_join": "match_link",
        "count": "tally",
        "sum": "total",
        "avg": "average",
        "group_by": "grouping",
        "order_by": "ranking",
        "insert_into": "add_rows",
        "update": "revise_rows",
        "delete": "remove_rows",
        "create_table": "build_table",
        "drop_table": "erase_table",
        "alter_table": "reshape_table",
    }
)


_RATIONALE_TEMPLATES.update(
    {
        "isinstance": "{motif} checks whether a value belongs to a specific type.",
        "issubclass": "{motif} checks whether one class inherits from another.",
    }
)


_SEMANTIC_SLUGS.update(
    {
        "ascii": "safe_text",
        "bin": "binary_code",
        "bytearray": "mutable_bytes",
        "bytes": "byte_pack",
        "callable": "can_call",
        "chr": "code_to_char",
        "compile": "compile_script",
        "complex": "complex_number",
        "delattr": "remove_attribute",
        "dir": "list_names",
        "divmod": "split_division",
        "enumerate": "numbered_route",
        "eval": "evaluate_expression",
        "exec": "run_script",
        "format": "format_value",
        "frozenset": "frozen_set",
        "getattr": "read_attribute",
        "globals": "global_map",
        "hasattr": "has_attribute",
        "hex": "hex_code",
        "id": "identity_tag",
        "iter": "iterator",
        "locals": "local_map",
        "map": "map_each",
        "memoryview": "memory_view",
        "next": "next_step",
        "object": "base_object",
        "oct": "octal_code",
        "open": "open_file",
        "ord": "char_code",
        "pow": "power_raise",
        "reversed": "reverse_path",
        "setattr": "set_attribute",
        "slice": "slice_range",
        "sorted": "sorted_route",
        "super": "parent_proxy",
        "type": "type_identity",
        "vars": "attribute_map",
        "zip": "zip_together",
        "capitalize": "first_letter_up",
        "casefold": "normalize_case",
        "center": "center_text",
        "encode": "encode_text",
        "endswith": "ends_with",
        "expandtabs": "expand_tabs",
        "find": "find_position",
        "format_map": "format_from_map",
        "index": "exact_position",
        "isalnum": "is_alnum",
        "isalpha": "is_alpha",
        "isascii": "is_ascii",
        "isdecimal": "is_decimal",
        "isdigit": "is_digit",
        "isidentifier": "is_identifier",
        "islower": "is_lowercase",
        "isnumeric": "is_numeric",
        "isprintable": "is_printable",
        "isspace": "is_space",
        "istitle": "is_titlecase",
        "isupper": "is_uppercase",
        "ljust": "left_pad",
        "lstrip": "trim_left",
        "maketrans": "make_translation",
        "partition": "split_once",
        "rfind": "find_last",
        "rindex": "last_position",
        "rjust": "right_pad",
        "rpartition": "split_once_right",
        "rsplit": "split_right",
        "rstrip": "trim_right",
        "splitlines": "split_lines",
        "startswith": "starts_with",
        "strip": "trim_edges",
        "swapcase": "swap_case",
        "title": "title_case",
        "translate": "translate_chars",
        "zfill": "zero_fill",
        "extend": "add_many",
        "insert": "insert_at",
        "reverse": "reverse_order",
        "popitem": "pop_pair",
        "difference": "set_difference",
        "difference_update": "remove_difference",
        "discard": "discard_item",
        "intersection": "set_overlap",
        "intersection_update": "keep_overlap",
        "isdisjoint": "no_overlap",
        "issubset": "subset_check",
        "issuperset": "superset_check",
        "symmetric_difference": "exclusive_difference",
        "symmetric_difference_update": "keep_exclusive_difference",
        "fileno": "file_number",
        "flush": "flush_buffer",
        "isatty": "is_terminal",
        "read": "read_file",
        "readable": "can_read",
        "readline": "read_line",
        "readlines": "read_lines",
        "seek": "move_cursor",
        "seekable": "can_seek",
        "tell": "cursor_position",
        "truncate": "cut_file",
        "writable": "can_write",
        "write": "write_file",
        "writelines": "write_lines",
        "pass": "do_nothing",
    }
)


_RATIONALE_TEMPLATES.update(
    {
        "bytearray": "{motif} cues a mutable sequence of raw bytes.",
        "bytes": "{motif} cues an immutable packet of raw bytes.",
        "callable": "{motif} cues checking whether a value can be called.",
        "chr": "{motif} cues turning a Unicode number into one character.",
        "compile": "{motif} cues turning source text into executable code.",
        "complex": "{motif} cues creating a number with real and imaginary parts.",
        "iter": "Uses {motif} for turning an object into a step-by-step route.",
        "next": "Uses {motif} for pulling the next item from an iterator.",
        "enumerate": "Uses {motif} for walking items while numbering each step.",
        "zip": "Uses {motif} for pairing items from multiple routes together.",
        "map": "Uses {motif} for applying one operation across every item.",
        "filter": "Uses {motif} for keeping only the items that pass a test.",
        "sorted": "Uses {motif} for returning items arranged in order.",
        "reversed": "Uses {motif} for walking the items in reverse order.",
        "open": "Uses {motif} for opening an external file handle.",
        "read": "Uses {motif} for pulling data out of a file.",
        "write": "Uses {motif} for pushing data into a file.",
    }
)

_RATIONALE_TEMPLATES.update(
    {
        "def": "{motif} names a reusable action you can call again later.",
        "return": "{motif} is the value a function gives back when it finishes.",
        "yield": "{motif} releases one value while keeping the sequence alive.",
        "lambda": "{motif} is a small inline function for one quick idea.",
        "if": "{motif} starts the branch that runs when a condition is true.",
        "elif": "{motif} checks another possible condition after the first one fails.",
        "else": "{motif} is the fallback branch when earlier checks do not match.",
        "for": "{motif} walks through each item in a collection one by one.",
        "in": "{motif} asks whether an item belongs inside a collection.",
        "while": "{motif} keeps a loop moving as long as its condition stays true.",
        "break": "{motif} stops the current loop immediately.",
        "continue": "{motif} skips this pass and moves to the next one.",
        "print": "{motif} sends a value to visible output.",
        "input": "{motif} asks the user for a value.",
        "range": "{motif} creates the number path a loop can follow.",
        "iter": "{motif} turns a value into something you can step through.",
        "next": "{motif} pulls the next value from an iterator.",
        "enumerate": "{motif} walks items while also counting their position.",
        "zip": "{motif} pairs items from multiple collections side by side.",
        "map": "{motif} applies one operation across every item.",
        "filter": "{motif} keeps only the items that pass a test.",
        "len": "{motif} counts how many items or characters are present.",
        "list": "{motif} stores ordered values that can change.",
        "dict": "{motif} stores values behind named keys.",
        "set": "{motif} stores unique values without duplicates.",
        "tuple": "{motif} stores ordered values that should stay fixed.",
        "append": "{motif} adds one new item to the end of a list.",
        "remove": "{motif} removes a chosen item from a collection.",
        "get": "{motif} looks up a value by key without forcing a crash.",
        "keys": "{motif} shows every key inside a dictionary.",
        "values": "{motif} shows every stored value inside a dictionary.",
        "items": "{motif} walks through key and value pairs together.",
        "class": "{motif} defines the shape shared by related objects.",
        "isinstance": "{motif} checks whether a value belongs to a type.",
        "issubclass": "{motif} checks whether one class inherits from another.",
        "type": "{motif} reveals what kind of value you are holding.",
        "super": "{motif} reaches behavior from a parent class.",
        "try": "{motif} marks code that might fail.",
        "except": "{motif} handles the failure from a try block.",
        "finally": "{motif} runs cleanup after success or failure.",
        "open": "{motif} opens a file handle.",
        "read": "{motif} pulls data out of a file.",
        "write": "{motif} sends data into a file.",
    }
)


_CONCEPT_MOTIF_HINTS: dict[str, tuple[str, ...]] = {
    "def": ("mission", "ability", "crew", "safehouse", "grove"),
    "return": ("cash", "money", "payout", "hustle", "reward", "loot"),
    "if": ("wanted", "mission", "gang", "territory", "cops", "heat"),
    "elif": ("wanted", "mission", "gang", "territory", "cops", "heat"),
    "else": ("wanted", "mission", "gang", "territory", "cops", "heat"),
    "iter": ("street", "road", "route", "mission", "drive", "race", "patrol"),
    "next": ("street", "road", "route", "mission", "drive", "race", "patrol"),
    "for": ("street", "road", "route", "mission", "drive", "race", "patrol"),
    "while": ("street", "road", "route", "mission", "drive", "race", "patrol"),
    "range": ("street", "road", "route", "mission", "drive", "race", "patrol"),
    "print": ("radio", "broadcast", "phone", "call", "message", "mission"),
    "input": ("phone", "call", "message", "contact"),
    "select": ("target", "mission", "crew", "heist", "map"),
    "where": ("wanted", "target", "map", "territory", "district"),
    "count": ("score", "cash", "wanted", "crew", "stash"),
    "len": ("crew", "stash", "garage", "inventory", "safehouse"),
}


_CRITICAL_PYTHON_CONCEPTS = frozenset(
    {
        "def", "return", "yield", "lambda",
        "if", "elif", "else", "for", "in", "while", "break", "continue",
        "class", "import", "try", "except", "finally", "raise", "assert",
        "print", "input", "range", "len", "iter", "next", "enumerate",
        "zip", "map", "filter", "list", "dict", "set", "tuple", "append",
        "remove", "get", "keys", "values", "items", "isinstance",
        "issubclass", "type", "super", "open", "read", "write",
    }
)

_COMPACT_LEARNING_CONCEPTS = _CRITICAL_PYTHON_CONCEPTS | frozenset(
    {
        "str", "int", "float", "round", "abs", "pow",
        "and", "or", "not", "true", "false", "none",
        "discard", "union", "with", "as", "from",
    }
)

_COMPACT_ROLE_CUES = {
    "def": "action", "return": "result",
    "if": "check", "elif": "alternate", "else": "fallback",
    "for": "route", "in": "inside", "while": "repeat",
    "break": "stop", "continue": "skip",
    "print": "signal", "input": "request", "range": "span", "len": "count",
    "str": "text", "int": "whole", "float": "decimal", "round": "precision",
    "abs": "distance", "pow": "power",
    "list": "sequence", "dict": "record", "set": "unique", "tuple": "fixed",
    "append": "insert", "remove": "drop", "get": "lookup", "keys": "fields",
    "values": "contents", "items": "entries", "add": "insert",
    "discard": "release", "union": "merge",
    "class": "blueprint", "type": "kind", "super": "parent",
    "isinstance": "kindcheck", "issubclass": "lineage",
    "open": "access", "read": "inspect", "write": "record", "close": "seal",
    "with": "context", "as": "alias", "from": "source", "import": "load",
    "try": "attempt", "except": "recover", "finally": "cleanup",
    "raise": "alert", "assert": "verify",
    "iter": "route", "next": "advance", "enumerate": "number",
    "zip": "pair", "map": "apply", "filter": "select",
    "ascii": "safe", "bin": "binary", "bytearray": "mutable",
    "bytes": "packet", "callable": "ready", "chr": "glyph",
    "compile": "build", "complex": "imaginary", "delattr": "unset",
    "dir": "names", "divmod": "split", "eval": "evaluate",
    "exec": "execute", "format": "shape", "frozenset": "frozen",
    "getattr": "fetch", "globals": "global", "hasattr": "has",
    "hex": "hex", "id": "identity", "locals": "local",
    "memoryview": "view", "object": "base", "oct": "octal",
    "ord": "ordinal", "reversed": "reverse", "setattr": "assign",
    "slice": "segment", "sorted": "order", "vars": "attributes",
    "isalnum": "alphanumeric", "isalpha": "alphabetic",
    "isascii": "ascii", "isdecimal": "decimal", "isdigit": "digit",
    "isidentifier": "identifier", "islower": "lowercase",
    "isnumeric": "numeric", "isprintable": "printable",
    "isspace": "whitespace", "istitle": "titlecase",
    "isupper": "uppercase", "startswith": "prefix", "endswith": "suffix",
    "readable": "readable", "seekable": "seekable", "writable": "writable",
}

_CONTROL_FLOW_CONCEPTS = frozenset(
    {"if", "elif", "else", "for", "in", "while", "break", "continue", "match", "case"}
)
_FUNCTION_CONCEPTS = frozenset({"def", "return", "yield", "lambda"})
_ITERATION_CONCEPTS = frozenset({"iter", "next", "range", "enumerate", "zip", "map", "filter"})
_COLLECTION_CONCEPTS = frozenset(
    {"list", "dict", "set", "tuple", "append", "remove", "get", "keys", "values", "items"}
)
_OUTPUT_INPUT_CONCEPTS = frozenset({"print", "input"})
_OOP_TYPE_CONCEPTS = frozenset(
    {"class", "isinstance", "issubclass", "type", "super", "object", "getattr", "setattr"}
)
_FILE_ERROR_CONCEPTS = frozenset(
    {"open", "read", "write", "close", "try", "except", "finally", "raise", "assert"}
)

_CONCEPT_FAMILIES = (
    "condition",
    "iteration",
    "function",
    "output",
    "data",
    "oop",
    "error",
    "general",
)


# _DOMAIN_LABELS, _domain_theme_key, _DOMAIN_FAMILY_MOTIFS artık
# theme_families.py'den geliyor (tek kaynak) — import bloğuna bakın.
# Kategori eklemek için SADECE theme_families.py düzenlenir.

_ALLOWED_SEMANTIC_NAME_PARTS = frozenset({"in", "is", "or", "and", "not"})

_TECHNICAL_TOKEN_PARTS = frozenset(
    {
        "keyword",
        "keywords",
        "builtin",
        "builtins",
        "function",
        "functions",
        "concept",
    }
)

_GENERIC_TOKEN_PARTS = frozenset(
    {
        "trigger",
        "second",
        "generic",
        "specific",
        "name",
        "thing",
        "stuff",
        "python",
        "code",
        "coding",
        "program",
        "variable",
        "helper",
        "config",
        "console",
        "debug",
        "terminal",
        "loop",
        "iteration",
        "print",
        "logs",
        "statement",
        "script",
        "syntax",
        "token",
    }
)

_BAD_TOKEN_SUBSTRINGS = frozenset(
    {
        "python",
        "code",
        "coding",
        "token",
        "syntax",
        "generic",
        "statement",
        "variable",
        "helper",
        "config",
        "console",
        "debug",
        "terminal",
        "loop",
        "iteration",
    }
)

_PERSONAL_PROFILE_STOP_WORDS = frozenset(
    {
        "i", "me", "my", "mine", "we", "our", "you", "your",
        "and", "or", "but", "the", "a", "an", "to", "of", "for",
        "in", "on", "with", "about", "like", "love", "learn", "learning",
        "confuse", "confusing", "hard", "difficult", "python", "code",
        "coding", "programming", "theme", "world", "system", "want",
        "wants", "make", "feel", "connected", "ben", "bana", "beni",
        "biz", "bir", "ve", "veya", "ama", "ile", "icin", "için",
        "seviyorum", "severim", "karisik", "karışık", "geliyor",
        "ogrenmek", "öğrenmek", "istiyorum", "tema", "evren",
        "evreni", "evreniyle", "olustur", "oluştur", "yap", "kur",
    }
)

_CURATED_CORE_TOKENS: dict[str, dict[str, str]] = {
    "cs2": {
        "if": "clutch_check", "elif": "backup_angle", "else": "save_round",
        "for": "site_rotation", "in": "inside_site", "while": "hold_angle",
        "break": "call_save", "continue": "repeek_angle", "def": "utility_lineup",
        "return": "round_result", "yield": "drop_flash", "lambda": "quick_strat",
        "class": "agent_blueprint", "import": "load_kit", "try": "clutch_attempt",
        "except": "failed_clutch", "finally": "post_round", "raise": "call_foul",
        "assert": "verify_angle", "print": "team_callout", "input": "mic_check",
        "range": "round_window", "len": "team_count", "iter": "site_route",
        "next": "next_angle", "enumerate": "numbered_peek", "zip": "duo_swing",
        "map": "utility_spread", "filter": "pick_targets", "list": "buy_menu",
        "dict": "loadout_card", "set": "unique_angles", "tuple": "fixed_setup",
        "append": "add_grenade", "remove": "drop_gear", "get": "read_loadout",
        "keys": "loadout_slots", "values": "loadout_items", "items": "full_loadout",
        "isinstance": "role_check", "issubclass": "squad_lineage",
        "type": "agent_type", "super": "captain_call", "open": "open_demo",
        "read": "read_strat", "write": "write_call",
    },
    "gta": {
        "if": "wanted_check", "elif": "heat_shift", "else": "safehouse_plan",
        "for": "street_route", "in": "inside_zone", "while": "keep_driving",
        "break": "ditch_cops", "continue": "next_block", "def": "mission_plan",
        "return": "mission_payout", "yield": "side_hustle", "lambda": "quick_job",
        "class": "crew_blueprint", "import": "load_contact", "try": "risky_job",
        "except": "busted_escape", "finally": "save_game", "raise": "raise_heat",
        "assert": "verify_deal", "print": "radio_callout", "input": "phone_contact",
        "range": "block_range", "len": "crew_count", "iter": "grove_route",
        "next": "next_checkpoint", "enumerate": "number_stops", "zip": "pair_rides",
        "map": "crew_jobs", "filter": "pick_targets", "list": "garage_stash",
        "dict": "crew_profile", "set": "unique_turfs", "tuple": "fixed_crew",
        "append": "add_ride", "remove": "drop_weapon", "get": "read_profile",
        "keys": "profile_fields", "values": "profile_values", "items": "crew_records",
        "isinstance": "crew_check", "issubclass": "gang_lineage",
        "type": "ride_type", "super": "boss_call", "open": "open_save",
        "read": "read_file", "write": "write_save",
    },
    "minecraft": {
        "if": "redstone_check", "elif": "biome_shift", "else": "spawn_fallback",
        "for": "minecart_route", "in": "inside_chest", "while": "keep_mining",
        "break": "tool_break", "continue": "next_block", "def": "craft_recipe",
        "return": "crafted_item", "yield": "ore_drop", "lambda": "quick_craft",
        "class": "mob_blueprint", "import": "load_mod", "try": "risky_dig",
        "except": "creeper_blast", "finally": "return_spawn", "raise": "alert_mob",
        "assert": "check_block", "print": "beacon_signal", "input": "chat_command",
        "range": "chunk_range", "len": "stack_count", "iter": "minecart_path",
        "next": "next_chunk", "enumerate": "number_slots", "zip": "pair_items",
        "map": "craft_all", "filter": "keep_ores", "list": "inventory_slots",
        "dict": "chest_record", "set": "unique_blocks", "tuple": "fixed_recipe",
        "append": "add_item", "remove": "drop_item", "get": "open_slot",
        "keys": "chest_keys", "values": "chest_loot", "items": "chest_items",
        "isinstance": "mob_check", "issubclass": "entity_lineage",
        "type": "block_type", "super": "parent_block", "open": "open_world",
        "read": "read_book", "write": "write_sign",
    },
    "formula1": {
        "if": "strategy_check", "elif": "weather_shift", "else": "box_plan",
        "for": "lap_cycle", "in": "inside_window", "while": "push_lap",
        "break": "box_now", "continue": "next_sector", "def": "pit_plan",
        "return": "podium_result", "yield": "split_time", "lambda": "quick_setup",
        "class": "car_blueprint", "import": "load_setup", "try": "risky_pass",
        "except": "track_limits", "finally": "garage_reset", "raise": "race_alert",
        "assert": "verify_lap", "print": "radio_message", "input": "pit_wall",
        "range": "lap_window", "len": "grid_count", "iter": "race_route",
        "next": "next_corner", "enumerate": "number_laps", "zip": "pair_cars",
        "map": "tune_all", "filter": "keep_fast", "list": "tyre_set",
        "dict": "telemetry_map", "set": "unique_laps", "tuple": "fixed_setup",
        "append": "add_lap", "remove": "drop_time", "get": "read_sector",
        "keys": "telemetry_keys", "values": "sector_values", "items": "lap_data",
        "isinstance": "car_check", "issubclass": "team_lineage",
        "type": "tyre_type", "super": "team_order", "open": "open_data",
        "read": "read_telemetry", "write": "write_setup",
    },
    "philosophers": {
        "if": "logic_test", "elif": "backup_premise", "else": "other_premise",
        "for": "academy_walk", "in": "inside_school", "while": "keep_debating",
        "break": "drop_argument", "continue": "resume_debate", "def": "argument_method",
        "return": "thesis_result", "yield": "shared_idea", "lambda": "quick_thesis",
        "class": "school_blueprint", "import": "cite_text", "try": "test_claim",
        "except": "false_premise", "finally": "final_note", "raise": "raise_objection",
        "assert": "prove_claim", "print": "dialogue_voice", "input": "socratic_question",
        "range": "argument_range", "len": "idea_count", "iter": "dialogue_path",
        "next": "next_argument", "enumerate": "number_claims", "zip": "pair_ideas",
        "map": "apply_reason", "filter": "keep_truths", "list": "idea_catalog",
        "dict": "scroll_archive", "set": "unique_claims", "tuple": "fixed_axiom",
        "append": "add_claim", "remove": "drop_claim", "get": "read_scroll",
        "keys": "scroll_topics", "values": "scroll_ideas", "items": "scroll_notes",
        "isinstance": "type_check", "issubclass": "school_lineage",
        "type": "idea_type", "super": "elder_argument", "open": "open_scroll",
        "read": "read_scroll", "write": "write_thesis",
    },
    "harry_potter": {
        "if": "spell_check", "elif": "house_rule", "else": "muggle_plan",
        "for": "hall_patrol", "in": "inside_hogwarts", "while": "keep_casting",
        "break": "stop_spell", "continue": "next_charm", "def": "spell_cast",
        "return": "house_points", "yield": "wand_spark", "lambda": "quick_charm",
        "class": "wizard_blueprint", "import": "summon_scroll", "try": "risky_spell",
        "except": "backfired_spell", "finally": "clean_cauldron", "raise": "raise_charm",
        "assert": "verify_spell", "print": "owl_message", "input": "howler_note",
        "range": "stair_range", "len": "spell_count", "iter": "marauder_map",
        "next": "next_corridor", "enumerate": "number_spells", "zip": "pair_wands",
        "map": "cast_all", "filter": "keep_charms", "list": "potion_shelf",
        "dict": "spellbook", "set": "unique_spells", "tuple": "fixed_potion",
        "append": "add_ingredient", "remove": "vanish_item", "get": "read_spell",
        "keys": "spell_topics", "values": "spell_effects", "items": "spell_notes",
        "isinstance": "wizard_check", "issubclass": "house_lineage",
        "type": "wand_type", "super": "elder_spell", "open": "open_scroll",
        "read": "read_spellbook", "write": "write_charm",
    },
    "witcher": {
        "if": "monster_check", "elif": "curse_shift", "else": "safe_path",
        "for": "monster_trail", "in": "inside_bestiary", "while": "keep_tracking",
        "break": "silver_strike", "continue": "next_clue", "def": "sign_cast",
        "return": "quest_reward", "yield": "loot_drop", "lambda": "quick_sign",
        "class": "school_blueprint", "import": "load_contract", "try": "risky_contract",
        "except": "failed_sign", "finally": "clean_blade", "raise": "raise_curse",
        "assert": "verify_tracks", "print": "quest_notice", "input": "tavern_rumor",
        "range": "trail_range", "len": "monster_count", "iter": "quest_path",
        "next": "next_clue", "enumerate": "number_tracks", "zip": "pair_signs",
        "map": "mark_targets", "filter": "keep_monsters", "list": "alchemy_kit",
        "dict": "bestiary_record", "set": "unique_tracks", "tuple": "fixed_potion",
        "append": "add_ingredient", "remove": "drop_trophy", "get": "read_bestiary",
        "keys": "bestiary_entries", "values": "monster_traits", "items": "contract_notes",
        "isinstance": "school_check", "issubclass": "witcher_lineage",
        "type": "monster_type", "super": "elder_sign", "open": "open_contract",
        "read": "read_bestiary", "write": "write_contract",
    },
}

_CURATED_CORE_TOKENS.update(
    {
        "music": {
            "if": "sound_check", "elif": "key_change", "else": "mute_track",
            "for": "beat_loop", "in": "inside_track", "while": "keep_playing",
            "break": "cut_song", "continue": "next_bar", "def": "song_hook",
            "return": "final_chord", "yield": "drop_note", "lambda": "quick_riff",
            "print": "stage_shout", "input": "mic_input", "range": "bar_count",
            "len": "track_length", "iter": "chorus_cycle", "next": "next_bar",
            "list": "track_list", "dict": "mix_board", "set": "unique_notes",
            "tuple": "fixed_chord", "class": "band_blueprint", "try": "live_take",
            "except": "wrong_note", "finally": "fade_out",
        },
        "cooking": {
            "if": "taste_check", "elif": "heat_shift", "else": "backup_recipe",
            "for": "prep_line", "in": "inside_pantry", "while": "keep_stirring",
            "break": "stop_cook", "continue": "next_step", "def": "recipe_method",
            "return": "dish_result", "yield": "serve_portion", "lambda": "quick_mix",
            "print": "order_call", "input": "guest_order", "range": "batch_count",
            "len": "serving_count", "iter": "stir_cycle", "next": "next_step",
            "list": "ingredient_list", "dict": "recipe_card", "set": "unique_spices",
            "tuple": "fixed_menu", "class": "dish_blueprint", "try": "oven_test",
            "except": "burnt_pan", "finally": "clean_station",
        },
        "football": {
            "if": "goal_check", "elif": "offside_flag", "else": "reset_play",
            "for": "wing_run", "in": "inside_box", "while": "keep_pressing",
            "break": "stop_play", "continue": "next_pass", "def": "set_piece",
            "return": "match_result", "yield": "through_ball", "lambda": "quick_pass",
            "print": "team_shout", "input": "coach_call", "range": "minute_window",
            "len": "squad_count", "iter": "passing_lane", "next": "next_play",
            "list": "squad_sheet", "dict": "tactics_board", "set": "unique_roles",
            "tuple": "fixed_lineup", "class": "player_blueprint", "try": "risky_tackle",
            "except": "foul_call", "finally": "final_whistle",
        },
        "space": {
            "if": "orbit_check", "elif": "gravity_shift", "else": "abort_path",
            "for": "orbit_path", "in": "inside_orbit", "while": "keep_flying",
            "break": "abort_burn", "continue": "next_planet", "def": "launch_plan",
            "return": "mission_result", "yield": "signal_ping", "lambda": "quick_burn",
            "print": "radio_ping", "input": "mission_control", "range": "star_range",
            "len": "crew_count", "iter": "star_route", "next": "next_planet",
            "list": "star_chart", "dict": "planet_record", "set": "unique_orbits",
            "tuple": "fixed_course", "class": "ship_blueprint", "try": "risky_launch",
            "except": "signal_loss", "finally": "mission_log",
        },
        "robotics": {
            "if": "sensor_check", "elif": "logic_gate", "else": "safe_mode",
            "for": "servo_cycle", "in": "inside_queue", "while": "keep_scanning",
            "break": "halt_motor", "continue": "next_joint", "def": "control_routine",
            "return": "task_result", "yield": "status_tick", "lambda": "quick_command",
            "print": "status_beep", "input": "operator_prompt", "range": "joint_range",
            "len": "sensor_count", "iter": "patrol_path", "next": "next_joint",
            "list": "command_queue", "dict": "sensor_map", "set": "unique_parts",
            "tuple": "fixed_pose", "class": "robot_blueprint", "try": "motion_test",
            "except": "fault_code", "finally": "power_down",
        },
        "aviation": {
            "if": "preflight_check", "elif": "weather_window", "else": "hold_short",
            "for": "flight_path", "in": "inside_airspace", "while": "keep_climbing",
            "break": "abort_takeoff", "continue": "next_waypoint", "def": "flight_plan",
            "return": "landing_result", "yield": "position_report", "lambda": "quick_turn",
            "print": "tower_call", "input": "radio_clearance", "range": "altitude_band",
            "len": "crew_count", "iter": "holding_pattern", "next": "next_waypoint",
            "list": "flight_log", "dict": "instrument_panel", "set": "unique_routes",
            "tuple": "fixed_course", "class": "airframe_blueprint", "try": "approach_test",
            "except": "stall_warning", "finally": "landing_check",
        },
        "architecture": {
            "if": "site_check", "elif": "zoning_rule", "else": "revise_plan",
            "for": "floor_plan", "in": "inside_room", "while": "keep_drafting",
            "break": "stop_build", "continue": "next_room", "def": "design_method",
            "return": "build_result", "yield": "draft_view", "lambda": "quick_sketch",
            "print": "client_note", "input": "site_brief", "range": "floor_range",
            "len": "room_count", "iter": "stair_route", "next": "next_room",
            "list": "material_list", "dict": "blueprint_index", "set": "unique_styles",
            "tuple": "fixed_layout", "class": "building_blueprint", "try": "load_test",
            "except": "code_violation", "finally": "site_report",
        },
        "medicine": {
            "if": "diagnosis_check", "elif": "symptom_shift", "else": "triage_plan",
            "for": "rounds_route", "in": "inside_chart", "while": "monitor_patient",
            "break": "stop_treatment", "continue": "next_patient", "def": "treatment_plan",
            "return": "recovery_result", "yield": "dose_step", "lambda": "quick_check",
            "print": "patient_note", "input": "symptom_input", "range": "dose_range",
            "len": "case_count", "iter": "care_cycle", "next": "next_patient",
            "list": "dose_list", "dict": "medical_chart", "set": "unique_symptoms",
            "tuple": "fixed_protocol", "class": "case_blueprint", "try": "lab_test",
            "except": "alert_code", "finally": "chart_update",
        },
        "finance": {
            "if": "risk_check", "elif": "market_shift", "else": "hold_cash",
            "for": "trade_cycle", "in": "inside_market", "while": "watch_price",
            "break": "stop_loss", "continue": "next_candle", "def": "strategy_rule",
            "return": "profit_result", "yield": "dividend_tick", "lambda": "quick_order",
            "print": "market_alert", "input": "trade_order", "range": "price_range",
            "len": "asset_count", "iter": "price_route", "next": "next_candle",
            "list": "watchlist", "dict": "ledger_map", "set": "unique_assets",
            "tuple": "fixed_portfolio", "class": "fund_blueprint", "try": "risky_trade",
            "except": "margin_call", "finally": "report_line",
        },
        "mythology": {
            "if": "oracle_check", "elif": "fate_shift", "else": "mortal_path",
            "for": "hero_path", "in": "inside_realm", "while": "keep_questing",
            "break": "break_oath", "continue": "next_trial", "def": "spell_rite",
            "return": "quest_reward", "yield": "relic_drop", "lambda": "quick_charm",
            "print": "bard_song", "input": "oracle_message", "range": "trial_range",
            "len": "hero_count", "iter": "quest_cycle", "next": "next_trial",
            "list": "hero_scroll", "dict": "relic_vault", "set": "unique_relics",
            "tuple": "fixed_prophecy", "class": "realm_blueprint", "try": "risky_rite",
            "except": "cursed_relic", "finally": "legend_note",
        },
    }
)

_BANNED_RATIONALE_PHRASES = frozenset(
    {
        "theme-specific name",
        "gives iter",
        "gives ",
        "python function",
        "programming construct",
        "maps this",
        "feel connected",
        "concept idea",
    }
)


@lru_cache(maxsize=1)
def _mappable_by_concept_id() -> dict[str, MappableConcept]:
    out: dict[str, MappableConcept] = {}
    for language in ("python", "sql"):
        concepts, _ = extract_mappable(language)  # type: ignore[arg-type]
        for concept in concepts:
            for concept_id in concept.concept_ids:
                out[concept_id] = concept
    return out


def _taxonomy_universal_alias(
    language: Language, canonical_name: str
) -> UniversalConcept | None:
    if language != "python":
        return None
    return _PYTHON_TAXONOMY_TO_UNIVERSAL.get(canonical_name)


_PYTHON_TAXONOMY_TO_UNIVERSAL: dict[str, UniversalConcept] = {
    "def": UniversalConcept.FUNCTION_DEF,
    "return": UniversalConcept.RETURN,
    "if": UniversalConcept.IF,
    "elif": UniversalConcept.ELIF,
    "else": UniversalConcept.ELSE,
    "for": UniversalConcept.FOR,
    "in": UniversalConcept.IN,
    "while": UniversalConcept.WHILE,
    "break": UniversalConcept.BREAK,
    "continue": UniversalConcept.CONTINUE,
    "class": UniversalConcept.CLASS_DEF,
    "import": UniversalConcept.IMPORT,
    "try": UniversalConcept.TRY,
    "except": UniversalConcept.EXCEPT,
    "finally": UniversalConcept.FINALLY,
    "and": UniversalConcept.AND,
    "or": UniversalConcept.OR,
    "not": UniversalConcept.NOT,
    "True": UniversalConcept.TRUE,
    "False": UniversalConcept.FALSE,
    "None": UniversalConcept.NONE,
    "lambda": UniversalConcept.LAMBDA,
    "global": UniversalConcept.GLOBAL,
    "nonlocal": UniversalConcept.NONLOCAL,
    "del": UniversalConcept.DEL,
    "assert": UniversalConcept.ASSERT,
    "raise": UniversalConcept.RAISE,
    "print": UniversalConcept.PRINT,
    "range": UniversalConcept.RANGE,
    "len": UniversalConcept.LEN,
    "append": UniversalConcept.LIST_APPEND,
    "remove": UniversalConcept.LIST_REMOVE,
    "get": UniversalConcept.DICT_GET,
    "keys": UniversalConcept.DICT_KEYS,
    "values": UniversalConcept.DICT_VALUES,
}
