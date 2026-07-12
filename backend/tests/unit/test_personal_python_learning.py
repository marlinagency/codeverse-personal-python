from __future__ import annotations

import contextlib
import io
import tempfile

from codeverse_core.cvl.pipeline import CompilationPipeline
from codeverse_core.personal_python.learning import (
    bridge_expected_stdout,
    bridge_reference_solution,
    build_bridge_challenge,
    build_learning_module,
    build_learning_path,
    build_progress_proof,
    code_task_expected_stdout,
    code_task_reference_solution,
    diagnose_learning_prompt,
    evaluate_practice_answer,
    grade_practice_answers,
)
from codeverse_core.theme_mapping.generator import TaxonomyThemeDictionaryGenerator


class _StubProvider:
    @property
    def provider_name(self) -> str:
        return "stub"

    def chat(self, messages, *, temperature, max_tokens) -> str:
        return "not json"


def _dictionary(prompt: str = "I love Counter-Strike 2 and loops/functions confuse me"):
    return TaxonomyThemeDictionaryGenerator(_StubProvider()).generate_profile_seeded(
        prompt,
        languages=("python",),
    )


def test_diagnose_learning_prompt_extracts_practical_learning_profile():
    diagnosis = diagnose_learning_prompt(
        "Ben CS2 seviyorum, Python'da if/for/function çok karışık geliyor.",
        {"favorite learning style": "visible examples"},
    )

    assert diagnosis.level == "beginner"
    assert "games" in diagnosis.interests
    assert "work" not in diagnosis.interests
    assert "conditionals" in diagnosis.pain_points
    assert "loops" in diagnosis.pain_points
    assert "functions" in diagnosis.pain_points
    assert diagnosis.recommended_start == "choices"
    assert diagnosis.confidence_score >= 70


def test_learning_path_prioritizes_detected_pain_points_and_uses_personal_tokens():
    dictionary = _dictionary()
    diagnosis = diagnose_learning_prompt("loops and functions confuse me")
    path = build_learning_path(dictionary, diagnosis)

    module_ids = [module.module_id for module in path.modules[:4]]
    assert module_ids[0] == "signals-and-values"
    assert "routes" in module_ids
    assert "tools" in module_ids

    route_module = next(module for module in path.modules if module.module_id == "routes")
    tokens = {concept.concept_id: concept.personal_token for concept in route_module.concepts}
    assert tokens["py_kw_for"] == dictionary.mappings["py_kw_for"]
    assert "Personal:" in route_module.bridge_steps[0]


def test_signals_module_has_progressive_chapters_and_deeper_practice():
    dictionary = _dictionary("I am new to Python and want visible examples")
    module = build_learning_module(dictionary, "signals-and-values")

    assert len(module.lesson_sections) == 4
    assert [section.section_id for section in module.lesson_sections] == [
        "signals-visible-output",
        "signals-values-and-types",
        "signals-named-values",
        "signals-debug-labels",
    ]
    assert all(section.personal_example for section in module.lesson_sections)
    assert all(section.real_python_example for section in module.lesson_sections)
    assert all(section.expected_output for section in module.lesson_sections)
    assert len(module.practice_tasks) == 6
    assert len(module.success_criteria) == 5


def test_learning_modules_compile_and_run_for_core_path():
    dictionary = _dictionary("gta san andreas oyununu seviyorum loops functions")
    pipeline = CompilationPipeline()

    for module_id, expected_stdout in {
        "signals-and-values": "Personal Python ready\n7\n",
        "strings-and-text": "CODEVERSE PYTHON\n['codeverse', 'python']\n2026\n",
        "numbers-and-conversion": "37.5\n8\n8\n",
        "imports-and-library": "9.0\n4\n",
        "choices": "keep practicing\n",
        "routes": "1\n2\n3\n",
        "loop-control": "1\n3\n",
        "tools": "150\n",
        "logic": "go\nempty\n",
        "collections": "[100, 150]\n150\n2\n",
        "tuples-and-sets": "('dock', 'market')\n3\nTrue\n",
        "files-and-context": "Python files stay safe\n",
        "objects": "Ada\n15\n",
        "errors": "attempt\ncleanup\n",
    }.items():
        module = build_learning_module(dictionary, module_id)
        compiled = pipeline.compile(module.source_content, dictionary)
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            with contextlib.chdir(temp_dir), contextlib.redirect_stdout(stdout):
                exec(compiled.codegen.source_code, {})  # noqa: S102 - generated test code.
        assert stdout.getvalue() == expected_stdout
        assert module.expected_stdout == expected_stdout
        assert module.real_python_preview
        assert module.why_it_matters
        assert module.lesson_steps
        assert module.misconception_checks
        assert module.success_criteria


def _run_compiled(pipeline: CompilationPipeline, source: str, dictionary) -> str:
    compiled = pipeline.compile(source, dictionary)
    stdout = io.StringIO()
    with tempfile.TemporaryDirectory() as temp_dir:
        with contextlib.chdir(temp_dir), contextlib.redirect_stdout(stdout):
            exec(compiled.codegen.source_code, {})  # noqa: S102 - generated test code.
    return stdout.getvalue()


def _run_practice_source(
    pipeline: CompilationPipeline,
    source: str,
    dictionary,
    syntax_mode: str,
) -> str:
    if syntax_mode == "personal":
        return _run_compiled(pipeline, source, dictionary)
    stdout = io.StringIO()
    with tempfile.TemporaryDirectory() as temp_dir:
        with contextlib.chdir(temp_dir), contextlib.redirect_stdout(stdout):
            exec(source, {})  # noqa: S102 - generated standard-Python exercise.
    return stdout.getvalue()


def test_rich_lesson_section_examples_match_real_python_behavior():
    dictionary = _dictionary("I want visible examples for strings")
    pipeline = CompilationPipeline()

    for module_id, expected_sections, expected_tasks in (
        ("signals-and-values", 4, 6),
        ("strings-and-text", 5, 6),
        ("numbers-and-conversion", 5, 6),
        ("imports-and-library", 4, 6),
        ("choices", 5, 6),
        ("routes", 5, 6),
        ("loop-control", 5, 6),
        ("tools", 5, 6),
    ):
        module = build_learning_module(dictionary, module_id)
        assert len(module.lesson_sections) == expected_sections
        assert len(module.practice_tasks) == expected_tasks

        for section in module.lesson_sections:
            personal_source = (
                f"@theme: {dictionary.theme}\n"
                "@language: python\n"
                "@version: 1\n"
                "---\n"
                f"{section.personal_example}\n"
            )
            assert _run_compiled(pipeline, personal_source, dictionary) == section.expected_output

            real_stdout = io.StringIO()
            with contextlib.redirect_stdout(real_stdout):
                exec(section.real_python_example, {})  # noqa: S102 - verified lesson code.
            assert real_stdout.getvalue() == section.expected_output


def test_code_tasks_are_solvable_and_starters_do_not_pass():
    """Every module's write_code exercise must be PROVEN solvable: the hidden
    reference solution compiles and prints exactly the goal output, while the
    starter compiles but does NOT already satisfy the goal (otherwise there
    is nothing to learn)."""
    pipeline = CompilationPipeline()
    module_ids = (
        "signals-and-values", "choices", "routes", "loop-control",
        "strings-and-text", "numbers-and-conversion", "imports-and-library",
        "tools", "logic", "collections", "tuples-and-sets",
        "files-and-context", "errors", "objects",
    )
    for prompt in (
        "I love Counter-Strike 2 and loops/functions confuse me",
        "philosophers",
    ):
        dictionary = _dictionary(prompt)
        for module_id in module_ids:
            module = build_learning_module(dictionary, module_id)
            code_tasks = [task for task in module.practice_tasks if task.kind == "write_code"]
            assert len(code_tasks) == 1, (prompt, module_id)
            task = code_tasks[0]
            assert task.starter_source
            assert task.hint

            expected = code_task_expected_stdout(task.id)
            assert expected, task.id

            solution = code_task_reference_solution(dictionary, task.id)
            assert solution
            assert _run_practice_source(
                pipeline,
                solution,
                dictionary,
                task.syntax_mode,
            ) == expected, (prompt, module_id)

            starter_stdout = _run_practice_source(
                pipeline,
                task.starter_source,
                dictionary,
                task.syntax_mode,
            )
            assert starter_stdout != expected, (prompt, module_id, "starter already passes")


def test_scaffold_fades_from_personal_tokens_to_standard_python():
    path = build_learning_path(_dictionary("I am learning Python"))

    assert [module.scaffold_stage for module in path.modules[:4]] == ["personal"] * 4
    assert [module.scaffold_stage for module in path.modules[4:8]] == ["bridge"] * 4
    assert [module.scaffold_stage for module in path.modules[8:11]] == ["python_forward"] * 3
    assert [module.scaffold_stage for module in path.modules[11:]] == ["real_python"] * 3
    assert [module.personal_support_percent for module in path.modules] == sorted(
        [module.personal_support_percent for module in path.modules],
        reverse=True,
    )

    for module in path.modules[8:]:
        code_task = next(task for task in module.practice_tasks if task.kind == "write_code")
        assert code_task.syntax_mode == "python"
        assert not code_task.starter_source.startswith("@theme:")
        assert "Write standard Python." in code_task.prompt


def test_bridge_capstone_reference_is_real_python_and_solvable():
    """The graduation solution must be plain Python that runs to the goal
    output, and must contain NONE of the learner's personal tokens — while
    the personal reference the learner translates FROM is full of them."""
    for prompt in ("I love Counter-Strike 2", "philosophers", "I'm a beekeeper"):
        dictionary = _dictionary(prompt)
        challenge = build_bridge_challenge(dictionary)

        assert challenge.forbidden_tokens  # theme actually renamed the keywords
        assert challenge.expected_stdout == bridge_expected_stdout()

        # the reference solution runs as PLAIN python (no theme compile)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exec(bridge_reference_solution(dictionary), {})  # noqa: S102 - generated test code
        assert stdout.getvalue() == challenge.expected_stdout

        # real solution must not contain any personal token (it's real Python)
        solution = bridge_reference_solution(dictionary)
        for token in challenge.forbidden_tokens:
            assert token not in solution

        # the personal reference the learner sees DOES contain them (so the
        # anti-cheat check has something to catch if they just paste it)
        assert any(token in challenge.personal_reference for token in challenge.forbidden_tokens)


def test_practice_evaluation_is_concept_specific():
    correct = evaluate_practice_answer("routes-count", "three")
    wrong = evaluate_practice_answer("tools-return", "100")

    assert correct.correct is True
    assert correct.score == 100
    assert wrong.correct is False
    assert wrong.expected_answer == "150"


def test_grade_practice_answers_builds_mastery_report():
    report = grade_practice_answers(
        {
            "routes-count": "3",
            "routes-translate": "for",
            "tools-return": "100",
        }
    )

    assert report.overall_score == 67
    assert report.passed is False
    by_module = {module.module_id: module for module in report.modules}
    assert by_module["routes"].score == 100
    assert by_module["tools"].score == 0
    assert "Review tools." in report.next_steps


def test_progress_proof_exposes_coverage_for_ui():
    proof = build_progress_proof(_dictionary("philosophers"))

    assert proof.total_modules >= 9
    assert proof.total_concepts >= 25
    assert proof.runnable_programs == proof.total_modules
    assert "routes" in proof.concept_coverage
