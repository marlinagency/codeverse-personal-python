"""Whole-dictionary quality evidence for Personal Python vocabularies."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from codeverse_core.theme_mapping.taxonomy_prompts import extract_mappable


@dataclass(frozen=True)
class DictionaryQualityReport:
    overall_score: int
    grade: str
    brevity_score: int
    uniqueness_score: int
    diversity_score: int
    semantic_score: int
    max_token_length: int
    max_token_parts: int
    dominant_root_share: float
    upgrade_recommended: bool
    issues: tuple[str, ...]


_BAD_RATIONALE_PHRASES = (
    "theme-specific",
    "feel connected",
    "concept idea",
    "specific name",
    "python function",
    "gives iter",
)


def assess_dictionary_quality(
    mappings: dict[str, str],
    rationale: dict[str, str] | None = None,
) -> DictionaryQualityReport:
    rationale = rationale or {}
    python_mappings = {
        concept_id: str(token).strip()
        for concept_id, token in mappings.items()
        if concept_id.startswith("py_") and str(token).strip()
    }
    if not python_mappings:
        return DictionaryQualityReport(
            overall_score=0,
            grade="F",
            brevity_score=0,
            uniqueness_score=0,
            diversity_score=0,
            semantic_score=0,
            max_token_length=0,
            max_token_parts=0,
            dominant_root_share=1.0,
            upgrade_recommended=True,
            issues=("No Python mappings are available.",),
        )

    canonical_by_id = {
        concept_id: concept.canonical_name.casefold()
        for concept in extract_mappable("python")[0]
        for concept_id in concept.concept_ids
    }
    canonical_tokens: dict[str, str] = {}
    for concept_id, token in python_mappings.items():
        canonical = canonical_by_id.get(concept_id, concept_id)
        canonical_tokens.setdefault(canonical, token)

    tokens = list(canonical_tokens.values())
    part_counts = [len([part for part in token.split("_") if part]) for token in tokens]
    lengths = [len(token) for token in tokens]
    concise = sum(parts <= 2 and length <= 20 for parts, length in zip(part_counts, lengths))
    brevity_score = round(100 * concise / len(tokens))

    unique_count = len({token.casefold() for token in tokens})
    uniqueness_score = round(100 * unique_count / len(tokens))

    roots = [token.casefold().split("_", 1)[0] for token in tokens]
    root_counts = Counter(roots)
    dominant_root_share = max(root_counts.values()) / len(roots)
    healthy_share = max(0.12, 1 / len(roots))
    if dominant_root_share <= healthy_share:
        diversity_score = 100
    else:
        diversity_score = round(
            max(0.0, min(1.0, (0.35 - dominant_root_share) / (0.35 - healthy_share)))
            * 100
        )

    # Semantic axis: a mapping earns its point when its explanation is (a)
    # present and free of filler, (b) tied to THIS token (the token's stem
    # appears in the text, so the cue and the story match), and (c) specific
    # (the same sentence isn't stamped verbatim onto many concepts). Single
    # -word tokens are fine — brevity and semantics must not fight.
    canonical_rationales: dict[str, str] = {}
    text_reuse: Counter[str] = Counter()
    for canonical in canonical_tokens:
        concept_ids = [cid for cid, name in canonical_by_id.items() if name == canonical]
        texts = [rationale.get(cid, "") for cid in concept_ids]
        text = next((item for item in texts if item), "").strip()
        canonical_rationales[canonical] = text
        if text:
            text_reuse[text.casefold()] += 1

    semantic_hits = 0
    for canonical, token in canonical_tokens.items():
        text = canonical_rationales[canonical]
        folded_text = text.casefold()
        has_clean_rationale = bool(text) and not any(
            phrase in folded_text for phrase in _BAD_RATIONALE_PHRASES
        )
        stem = token.casefold().split("_", 1)[0]
        tied_to_token = bool(stem) and stem in folded_text
        behavior_specific = bool(text) and text_reuse[folded_text] <= 3
        if has_clean_rationale and tied_to_token and behavior_specific:
            semantic_hits += 1
    semantic_score = round(100 * semantic_hits / len(tokens))

    overall_score = round(
        brevity_score * 0.30
        + uniqueness_score * 0.25
        + diversity_score * 0.20
        + semantic_score * 0.25
    )
    grade = "A" if overall_score >= 90 else "B" if overall_score >= 80 else "C" if overall_score >= 70 else "D" if overall_score >= 60 else "F"

    issues: list[str] = []
    long_count = len(tokens) - concise
    if long_count:
        issues.append(f"{long_count} token(s) exceed two parts or 20 characters.")
    duplicate_count = len(tokens) - unique_count
    if duplicate_count:
        issues.append(f"{duplicate_count} canonical concept(s) reuse another token.")
    if root_counts.most_common(1)[0][1] > 1 and dominant_root_share > 0.20:
        root, count = root_counts.most_common(1)[0]
        issues.append(f"The root '{root}' is repeated across {count} concepts.")
    missing_semantics = len(tokens) - semantic_hits
    if missing_semantics:
        issues.append(f"{missing_semantics} concept(s) lack a specific behavior explanation.")

    return DictionaryQualityReport(
        overall_score=overall_score,
        grade=grade,
        brevity_score=brevity_score,
        uniqueness_score=uniqueness_score,
        diversity_score=diversity_score,
        semantic_score=semantic_score,
        max_token_length=max(lengths),
        max_token_parts=max(part_counts),
        dominant_root_share=round(dominant_root_share, 3),
        upgrade_recommended=overall_score < 85 or bool(long_count),
        issues=tuple(issues),
    )
