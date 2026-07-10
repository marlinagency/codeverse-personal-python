"""Loader for the W3Schools-derived language taxonomy (Taksonomi Planı Adım 5).

Reads ``taxonomy_python.json`` / ``taxonomy_sql.json`` (built by
``scripts/build_taxonomy.py`` + ``scripts/fill_taxonomy_descriptions.py``,
see ``scripts/taxonomy/README.md``) and exposes them as typed, indexed
Python objects. Results are cached in-process — the files are read once.

This taxonomy is reference/design material for expanding the theme-mapping
concept list and codegen coverage (Adım 6+); it is NOT loaded by the live
compilation pipeline, which still runs on ``codeverse_core.concepts.
UniversalConcept``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

Language = Literal["python", "sql"]
ConceptTier = Literal["core", "builtin", "method", "type", "exception", "library"]

_DATA_DIR = Path(__file__).resolve().parent

_FILENAMES: dict[Language, str] = {
    "python": "taxonomy_python.json",
    "sql": "taxonomy_sql.json",
}


class TaxonomyLoadError(Exception):
    """A taxonomy JSON file is missing or fails schema validation."""


@dataclass(frozen=True)
class TaxonomyConcept:
    concept_id: str
    language: Language
    category: str
    tier: ConceptTier
    title: str
    real_syntax: str
    code_examples: tuple[str, ...]
    source_url: str
    description: str

    @property
    def is_sandbox_safe(self) -> bool:
        """False for ``library`` tier: themeable by name only, not guaranteed
        to run error-free (third-party packages / dialect-specific
        functions — see scripts/taxonomy/README.md)."""
        return self.tier != "library"


def _parse_concept(raw: dict, language: Language) -> TaxonomyConcept:
    try:
        return TaxonomyConcept(
            concept_id=raw["concept_id"],
            language=language,
            category=raw["category"],
            tier=raw["tier"],
            title=raw["title"],
            real_syntax=raw["real_syntax"],
            code_examples=tuple(raw.get("code_examples", [])),
            source_url=raw["source_url"],
            description=raw["description"] or "",
        )
    except KeyError as exc:
        raise TaxonomyLoadError(
            f"taksonomi girdisinde eksik alan: {exc} (concept_id="
            f"{raw.get('concept_id', '?')!r})"
        ) from exc


@lru_cache(maxsize=None)
def load_taxonomy(language: Language) -> tuple[TaxonomyConcept, ...]:
    """All concepts for one language, in file order. Cached after first call."""
    filename = _FILENAMES.get(language)
    if filename is None:
        raise ValueError(f"desteklenmeyen dil: {language!r} (python | sql)")

    path = _DATA_DIR / filename
    if not path.exists():
        raise TaxonomyLoadError(f"taksonomi dosyası bulunamadı: {path}")

    raw_list = json.loads(path.read_text(encoding="utf-8"))
    concepts = tuple(_parse_concept(item, language) for item in raw_list)

    seen: set[str] = set()
    for c in concepts:
        if c.concept_id in seen:
            raise TaxonomyLoadError(f"tekrarlanan concept_id: {c.concept_id!r}")
        seen.add(c.concept_id)

    return concepts


def load_all_taxonomies() -> dict[Language, tuple[TaxonomyConcept, ...]]:
    return {lang: load_taxonomy(lang) for lang in _FILENAMES}


@lru_cache(maxsize=None)
def _index_by_id(language: Language) -> dict[str, TaxonomyConcept]:
    return {c.concept_id: c for c in load_taxonomy(language)}


def get_concept(language: Language, concept_id: str) -> TaxonomyConcept | None:
    return _index_by_id(language).get(concept_id)


@lru_cache(maxsize=None)
def _index_by_category(language: Language) -> dict[str, tuple[TaxonomyConcept, ...]]:
    buckets: dict[str, list[TaxonomyConcept]] = {}
    for c in load_taxonomy(language):
        buckets.setdefault(c.category, []).append(c)
    return {cat: tuple(items) for cat, items in buckets.items()}


def concepts_by_category(language: Language, category: str) -> tuple[TaxonomyConcept, ...]:
    return _index_by_category(language).get(category, ())


def categories(language: Language) -> tuple[str, ...]:
    return tuple(_index_by_category(language).keys())


@lru_cache(maxsize=None)
def _index_by_tier(language: Language) -> dict[str, tuple[TaxonomyConcept, ...]]:
    buckets: dict[str, list[TaxonomyConcept]] = {}
    for c in load_taxonomy(language):
        buckets.setdefault(c.tier, []).append(c)
    return {tier: tuple(items) for tier, items in buckets.items()}


def concepts_by_tier(language: Language, tier: ConceptTier) -> tuple[TaxonomyConcept, ...]:
    return _index_by_tier(language).get(tier, ())
