from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TAXONOMY_DIR = ROOT / "scripts" / "taxonomy"


def test_taxonomy_descriptions_are_complete_and_safe():
    paths = [
        TAXONOMY_DIR / "taxonomy_python.json",
        TAXONOMY_DIR / "taxonomy_sql.json",
    ]
    concepts = [
        item
        for path in paths
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]

    assert len(concepts) == 980

    for concept in concepts:
        description = concept.get("description")
        assert isinstance(description, str), concept["concept_id"]
        assert description.endswith("."), concept["concept_id"]
        assert "\n" not in description, concept["concept_id"]
        assert len(description) <= 260, concept["concept_id"]
        assert "W3Schools" not in description, concept["concept_id"]


def test_library_tier_descriptions_mark_runtime_limits():
    concepts = [
        item
        for path in (
            TAXONOMY_DIR / "taxonomy_python.json",
            TAXONOMY_DIR / "taxonomy_sql.json",
        )
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]
    libraries = [item for item in concepts if item["tier"] == "library"]

    assert libraries
    assert all("sandbox support depends" in item["description"] for item in libraries)
