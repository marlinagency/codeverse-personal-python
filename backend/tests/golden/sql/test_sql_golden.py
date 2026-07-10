from __future__ import annotations

from pathlib import Path

import pytest

from tests.golden.util import assert_matches_golden, compile_case

CASES_DIR = Path(__file__).parent / "cases"
EXPECTED_DIR = Path(__file__).parent / "expected"

CASE_NAMES = sorted(p.stem for p in CASES_DIR.glob("*.cvl"))


@pytest.mark.parametrize("name", CASE_NAMES)
def test_generated_sql_matches_golden(name):
    generated = compile_case(CASES_DIR / f"{name}.cvl")
    assert_matches_golden(generated, EXPECTED_DIR / f"{name}.sql")
