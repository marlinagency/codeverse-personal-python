from __future__ import annotations

import contextlib
import io

import pytest

from codeverse_core.cvl.pipeline import CompilationPipeline
from codeverse_core.personal_python import build_personal_python_lesson
from codeverse_core.theme_mapping.generator import TaxonomyThemeDictionaryGenerator


class _StubProvider:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    @property
    def provider_name(self) -> str:
        return "stub"

    def chat(self, messages, *, temperature, max_tokens) -> str:
        return self._responses.pop(0)


def _run_lesson(dictionary) -> tuple[str, str]:
    lesson = build_personal_python_lesson(dictionary)
    compiled = CompilationPipeline().compile(lesson.source_content, dictionary)
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exec(compiled.codegen.source_code, {})  # noqa: S102 - generated test code.
    return lesson.source_content, stdout.getvalue()


@pytest.mark.parametrize(
    "prompt",
    [
        "witcher evreniyle olustur",
        "counter strike 2 seviyorum if for def print karisik geliyor",
        "gta san andreas evreniyle olustur",
        "felsefe ve socrates ile dusunen bir python dili",
        "ben deniz alti kesiflerini seviyorum ve donguler bana karisik geliyor",
    ],
)
def test_personal_python_lesson_compiles_and_runs_for_theme_families(prompt):
    provider = _StubProvider(["junk"] * 4)
    generator = TaxonomyThemeDictionaryGenerator(provider)
    dictionary = generator.generate_profile_seeded(prompt, languages=("python",))

    source, stdout = _run_lesson(dictionary)

    assert stdout == "100\n150\n150\n200\n4\n"
    for concept_id in (
        "py_kw_def",
        "py_kw_if",
        "py_kw_elif",
        "py_kw_else",
        "py_kw_for",
        "py_kw_return",
        "py_fn_print",
        "py_fn_range",
        "py_fn_list",
        "py_fn_dict",
        "py_list_append",
        "py_dict_get",
    ):
        assert dictionary.mappings[concept_id] in source
    assert "cv_" in source


def test_personal_python_lesson_supports_legacy_universal_dictionary(space_dictionary):
    source, stdout = _run_lesson(space_dictionary)

    assert stdout == "100\n150\n150\n200\n4\n"
    assert "singularity cv_build_scores" in source
    assert "orbit cv_score around cv_scores" in source
    assert "radiate(mass(cv_scores))" in source
