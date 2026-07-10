from __future__ import annotations

from pathlib import Path

import pytest

from tests.golden.util import assert_matches_golden, compile_case, run_python

CASES_DIR = Path(__file__).parent / "cases"
EXPECTED_DIR = Path(__file__).parent / "expected"
OUTPUT_DIR = Path(__file__).parent / "expected_output"

CASE_NAMES = sorted(p.stem for p in CASES_DIR.glob("*.cvl"))


@pytest.mark.parametrize("name", CASE_NAMES)
def test_generated_python_matches_golden(name):
    generated = compile_case(CASES_DIR / f"{name}.cvl")
    assert_matches_golden(generated, EXPECTED_DIR / f"{name}.py")


@pytest.mark.parametrize("name", CASE_NAMES)
def test_generated_python_runs_correctly(name):
    """Execute the generated code and compare real stdout."""
    generated = compile_case(CASES_DIR / f"{name}.cvl")
    stdout = run_python(generated)
    assert_matches_golden(stdout, OUTPUT_DIR / f"{name}.out")
