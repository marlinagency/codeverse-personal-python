from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.golden.util import SPACE_DICTIONARY

ROOT = Path(__file__).parent


@pytest.mark.parametrize("target", ["python", "sql"])
def test_golden_cases_cover_every_themed_concept_token(target):
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / target / "cases").glob("*.cvl"))
    )

    missing: list[str] = []
    for concept, token in SPACE_DICTIONARY.mappings.items():
        if not re.search(rf"(?<![\w]){re.escape(token)}(?![\w])", source):
            missing.append(f"{concept.key}:{token}")

    assert missing == []
