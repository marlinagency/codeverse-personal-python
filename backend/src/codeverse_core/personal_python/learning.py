"""Deterministic learning layer for Personal Python.

This module turns a generated Personal Python dictionary into lesson-path,
bridge-mode, practice, and proof objects. It intentionally stays offline and
deterministic: the LLM can personalize the dictionary, while the education
contract remains reliable enough for tests and demos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LearnerDiagnosis:
    level: str
    learner_summary: str
    interests: tuple[str, ...]
    goals: tuple[str, ...]
    pain_points: tuple[str, ...]
    preferred_examples: tuple[str, ...]
    recommended_start: str
    confidence_score: int
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class LearningConcept:
    concept_id: str
    python_concept: str
    personal_token: str
    title: str
    mental_model: str
    real_python: str


@dataclass(frozen=True)
class PracticeTask:
    id: str
    kind: str
    concept_id: str
    prompt: str
    expected_answer: str
    choices: tuple[str, ...] = ()
    starter_source: str | None = None
    hint: str = ""
    explanation: str = ""


@dataclass(frozen=True)
class LessonSection:
    section_id: str
    title: str
    objective: str
    explanation: str
    key_points: tuple[str, ...]
    personal_example: str
    real_python_example: str
    expected_output: str


@dataclass(frozen=True)
class LearningModule:
    module_id: str
    title: str
    goal: str
    why_it_matters: str
    concepts: tuple[LearningConcept, ...]
    bridge_steps: tuple[str, ...]
    lesson_steps: tuple[str, ...]
    lesson_sections: tuple[LessonSection, ...]
    misconception_checks: tuple[str, ...]
    success_criteria: tuple[str, ...]
    source_content: str
    real_python_preview: str
    expected_stdout: str
    practice_tasks: tuple[PracticeTask, ...]
    order: int


@dataclass(frozen=True)
class LearningPath:
    title: str
    diagnosis: LearnerDiagnosis
    modules: tuple[LearningModule, ...]
    proof_points: tuple[str, ...]


@dataclass(frozen=True)
class PracticeEvaluation:
    correct: bool
    score: int
    feedback: str
    expected_answer: str
    next_step: str


@dataclass(frozen=True)
class ModuleMastery:
    module_id: str
    score: int
    passed: bool
    correct: int
    total: int
    feedback: str


@dataclass(frozen=True)
class MasteryReport:
    overall_score: int
    passed: bool
    modules: tuple[ModuleMastery, ...]
    strengths: tuple[str, ...]
    next_steps: tuple[str, ...]


@dataclass(frozen=True)
class ProgressProof:
    headline: str
    total_modules: int
    total_concepts: int
    runnable_programs: int
    bridge_modes: tuple[str, ...]
    concept_coverage: dict[str, list[str]] = field(default_factory=dict)


_INTEREST_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("games", ("game", "oyun", "cs2", "counter", "gta", "minecraft", "witcher", "valorant")),
    ("sports", ("football", "basketball", "formula", "f1", "race", "spor", "yarış", "yaris")),
    ("music", ("music", "song", "guitar", "piano", "müzik", "muzik", "şarkı", "sarki")),
    ("science", ("space", "physics", "biology", "science", "uzay", "fizik", "bilim")),
    ("work", ("job", "career", "engineer", "school", "iş", "is", "okul", "mühendis")),
    ("stories", ("movie", "series", "anime", "fantasy", "film", "dizi", "hikaye")),
)

_GOAL_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("build AI apps", ("ai", "yapay zeka", "machine learning", "llm", "chatbot")),
    ("build apps", ("app", "uygulama", "website", "web", "api")),
    ("learn Python fundamentals", ("learn", "öğren", "ogren", "python", "beginner", "başlangıç")),
    ("pass exercises", ("exam", "quiz", "test", "sınav", "sinav", "ödev", "odev")),
)

_PAIN_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("conditionals", ("if", "elif", "else", "condition", "koşul", "kosul")),
    ("loops", ("for", "while", "loop", "range", "döngü", "dongu")),
    ("functions", ("def", "function", "return", "fonksiyon")),
    ("collections", ("list", "dict", "array", "dictionary", "liste", "sözlük", "sozluk")),
    ("errors", ("try", "except", "error", "hata")),
    ("classes", ("class", "object", "oop", "nesne", "sınıf", "sinif")),
    ("files", ("file", "files", "open", "read", "write", "dosya")),
    ("numbers", ("number", "numbers", "int", "float", "round", "math", "sayi")),
    ("imports", ("import", "module", "library", "package", "kutuphane", "modul")),
)

_MODULE_BLUEPRINTS: tuple[dict[str, Any], ...] = (
    {
        "module_id": "signals-and-values",
        "title": "Signals and Values",
        "goal": "Print values, name data, and see immediate output.",
        "why": "Beginners need fast visible feedback before abstract syntax feels useful.",
        "concept_ids": ("py_fn_print",),
    },
    {
        "module_id": "strings-and-text",
        "title": "Strings and Text",
        "goal": "Clean, transform, replace, and split text with Python string methods.",
        "why": "Text is everywhere in real programs: names, messages, files, APIs, and model prompts.",
        "concept_ids": (
            "py_fn_str",
            "py_str_strip",
            "py_str_replace",
            "py_str_upper",
            "py_str_lower",
            "py_str_split",
        ),
    },
    {
        "module_id": "numbers-and-conversion",
        "title": "Numbers and Conversion",
        "goal": "Convert numeric text and use common numeric functions in reliable calculations.",
        "why": "Inputs, files, and APIs often provide numbers as text that must be converted before calculation.",
        "concept_ids": ("py_fn_int", "py_fn_float", "py_fn_round", "py_fn_abs", "py_fn_pow"),
    },
    {
        "module_id": "imports-and-library",
        "title": "Imports and Standard Library",
        "goal": "Import modules, select individual tools, and create clear local aliases.",
        "why": "Real Python projects reuse tested standard-library tools instead of rebuilding every capability.",
        "concept_ids": ("py_kw_import", "py_kw_from", "py_kw_as"),
    },
    {
        "module_id": "choices",
        "title": "Choices",
        "goal": "Use if, elif, and else to make a program choose a path.",
        "why": "Most programs become useful when they can react to conditions.",
        "concept_ids": ("py_kw_if", "py_kw_elif", "py_kw_else"),
    },
    {
        "module_id": "routes",
        "title": "Repeated Routes",
        "goal": "Use for and range to repeat work without copying lines.",
        "why": "Loops turn repeated manual steps into one reliable pattern.",
        "concept_ids": ("py_kw_for", "py_kw_in", "py_fn_range"),
    },
    {
        "module_id": "loop-control",
        "title": "Loop Control",
        "goal": "Use while, break, and continue to control when repetition stops or skips.",
        "why": "Real programs often repeat until a condition changes, not just for a fixed count.",
        "concept_ids": ("py_kw_while", "py_kw_break", "py_kw_continue"),
    },
    {
        "module_id": "tools",
        "title": "Reusable Tools",
        "goal": "Use def and return to package behavior into a reusable function.",
        "why": "Functions let learners stop copying logic and start naming reusable ideas.",
        "concept_ids": ("py_kw_def", "py_kw_return"),
    },
    {
        "module_id": "logic",
        "title": "Boolean Logic",
        "goal": "Use and, or, not, true, false, and none to combine decisions.",
        "why": "Conditionals become expressive when learners can combine smaller checks.",
        "concept_ids": (
            "py_kw_and",
            "py_kw_or",
            "py_kw_not",
            "py_kw_true",
            "py_kw_false",
            "py_kw_none",
        ),
    },
    {
        "module_id": "collections",
        "title": "Collections",
        "goal": "Use list, dict, append, get, and len to organize data.",
        "why": "Useful programs need to hold many values and retrieve the right one.",
        "concept_ids": ("py_fn_list", "py_fn_dict", "py_list_append", "py_dict_get", "py_fn_len"),
    },
    {
        "module_id": "tuples-and-sets",
        "title": "Tuples and Sets",
        "goal": "Use tuples for stable ordered records and sets for unique values.",
        "why": "Programs often need both data that keeps its shape and data that automatically removes duplicates.",
        "concept_ids": ("py_fn_tuple", "py_fn_set", "py_set_add", "py_set_discard", "py_set_union", "py_kw_in"),
    },
    {
        "module_id": "files-and-context",
        "title": "Files and Context Managers",
        "goal": "Open, write, and read text files while closing resources safely.",
        "why": "Programs persist notes, settings, datasets, and results in files that must be handled reliably.",
        "concept_ids": ("py_kw_with", "py_kw_as", "py_fn_open", "py_file_write", "py_file_read"),
    },
    {
        "module_id": "errors",
        "title": "Safe Attempts",
        "goal": "Understand try, except, and finally as a safe execution path.",
        "why": "Learners gain confidence when errors become part of the program flow.",
        "concept_ids": ("py_kw_try", "py_kw_except", "py_kw_finally"),
    },
    {
        "module_id": "objects",
        "title": "Objects",
        "goal": "Use class to group data and behavior into one reusable shape.",
        "why": "Classes help larger programs keep related state and actions together.",
        "concept_ids": ("py_kw_class", "py_kw_def", "py_kw_return"),
    },
)

_CONCEPT_COPY: dict[str, tuple[str, str, str]] = {
    "py_fn_print": ("print", "Output", "Send a value to the screen so you can observe the program."),
    "py_fn_str": ("str", "Text conversion", "Convert a value into text so it can join other strings."),
    "py_str_strip": ("strip", "Trim text", "Remove whitespace from both ends of a string."),
    "py_str_replace": ("replace", "Replace text", "Swap one piece of text for another without changing the original string."),
    "py_str_upper": ("upper", "Uppercase text", "Create an uppercase version of a string."),
    "py_str_lower": ("lower", "Lowercase text", "Create a lowercase version of a string."),
    "py_str_split": ("split", "Split text", "Break a string into a list of smaller strings."),
    "py_fn_int": ("int", "Integer conversion", "Convert a compatible value into a whole number."),
    "py_fn_float": ("float", "Decimal conversion", "Convert a compatible value into a floating-point number."),
    "py_fn_round": ("round", "Rounded number", "Round a number to a requested precision."),
    "py_fn_abs": ("abs", "Absolute value", "Measure a number's distance from zero without its sign."),
    "py_fn_pow": ("pow", "Power", "Raise a number to an exponent and return the result."),
    "py_kw_import": ("import", "Import module", "Load a module so its public tools can be used."),
    "py_kw_from": ("from", "Import from module", "Select a named tool from a module."),
    "py_kw_if": ("if", "First condition", "Run a block only when a condition is true."),
    "py_kw_elif": ("elif", "Second condition", "Try another condition when the first one fails."),
    "py_kw_else": ("else", "Fallback", "Run a final block when no previous condition matched."),
    "py_kw_for": ("for", "Loop", "Repeat a block for each item in a sequence."),
    "py_kw_in": ("in", "Membership", "Connect a loop variable to the sequence it walks through."),
    "py_kw_while": ("while", "Condition loop", "Repeat while a condition stays true."),
    "py_kw_break": ("break", "Stop loop", "Exit the nearest loop immediately."),
    "py_kw_continue": ("continue", "Skip forward", "Skip the rest of this loop turn and continue with the next one."),
    "py_fn_range": ("range", "Number route", "Create a predictable sequence of numbers for loops."),
    "py_kw_def": ("def", "Function definition", "Name a reusable block of behavior."),
    "py_kw_return": ("return", "Function result", "Send a value back from a function."),
    "py_kw_and": ("and", "Both conditions", "Require two checks to be true at the same time."),
    "py_kw_or": ("or", "Either condition", "Allow either check to be true."),
    "py_kw_not": ("not", "Flip condition", "Invert a boolean result."),
    "py_kw_true": ("True", "True value", "Represent a condition that is satisfied."),
    "py_kw_false": ("False", "False value", "Represent a condition that is not satisfied."),
    "py_kw_none": ("None", "No value", "Represent the intentional absence of a value."),
    "py_fn_list": ("list", "List", "Store ordered values."),
    "py_fn_dict": ("dict", "Dictionary", "Store labeled values by key."),
    "py_list_append": ("append", "Add to list", "Place a new value at the end of a list."),
    "py_dict_get": ("get", "Read from dictionary", "Read a value by key with a safe fallback."),
    "py_fn_len": ("len", "Length", "Count how many items a collection contains."),
    "py_fn_tuple": ("tuple", "Fixed sequence", "Store an ordered sequence whose items cannot be replaced in place."),
    "py_fn_set": ("set", "Unique collection", "Store unique values without relying on a fixed display order."),
    "py_set_add": ("add", "Add unique value", "Add one value to a set while preserving uniqueness."),
    "py_set_discard": ("discard", "Safely remove value", "Remove a value from a set without failing when it is absent."),
    "py_set_union": ("union", "Combine sets", "Create a set containing the unique values from both sets."),
    "py_kw_with": ("with", "Managed resource", "Enter a context that cleans up its resource when the block ends."),
    "py_kw_as": ("as", "Local alias", "Bind an imported tool or managed resource to a clear local name."),
    "py_fn_open": ("open", "Open file", "Open a path in an explicit read or write mode."),
    "py_file_write": ("write", "Write text", "Store text in an open file and advance its cursor."),
    "py_file_read": ("read", "Read text", "Load text from the current position of an open file."),
    "py_kw_try": ("try", "Safe attempt", "Run code that might fail."),
    "py_kw_except": ("except", "Error handler", "Respond when the try block fails."),
    "py_kw_finally": ("finally", "Cleanup", "Run cleanup after try or except."),
    "py_kw_class": ("class", "Class definition", "Define a reusable shape for objects."),
}

_FALLBACK_TOKENS: dict[str, str] = {
    "py_fn_print": "print",
    "py_fn_str": "str",
    "py_str_strip": "strip",
    "py_str_replace": "replace",
    "py_str_upper": "upper",
    "py_str_lower": "lower",
    "py_str_split": "split",
    "py_fn_int": "int",
    "py_fn_float": "float",
    "py_fn_round": "round",
    "py_fn_abs": "abs",
    "py_fn_pow": "pow",
    "py_kw_import": "import",
    "py_kw_from": "from",
    "py_kw_if": "if",
    "py_kw_elif": "elif",
    "py_kw_else": "else",
    "py_kw_for": "for",
    "py_kw_in": "in",
    "py_kw_while": "while",
    "py_kw_break": "break",
    "py_kw_continue": "continue",
    "py_fn_range": "range",
    "py_kw_def": "func",
    "py_kw_return": "return",
    "py_kw_and": "and",
    "py_kw_or": "or",
    "py_kw_not": "not",
    "py_kw_true": "true",
    "py_kw_false": "false",
    "py_kw_none": "none",
    "py_fn_list": "list",
    "py_fn_dict": "dict",
    "py_list_append": "append",
    "py_dict_get": "get",
    "py_fn_len": "len",
    "py_fn_tuple": "tuple",
    "py_fn_set": "set",
    "py_set_add": "add",
    "py_set_discard": "discard",
    "py_set_union": "union",
    "py_kw_with": "with",
    "py_kw_as": "as",
    "py_fn_open": "open",
    "py_file_write": "write",
    "py_file_read": "read",
    "py_kw_try": "try",
    "py_kw_except": "except",
    "py_kw_finally": "finally",
    "py_kw_class": "class",
}


def diagnose_learning_prompt(
    prompt: str,
    clarifying_answers: dict[str, str] | None = None,
) -> LearnerDiagnosis:
    text = _fold(prompt)
    answers = clarifying_answers or {}
    answer_text = _fold(" ".join(f"{k} {v}" for k, v in answers.items()))
    combined = f"{text} {answer_text}".strip()

    interests = _matches(combined, _INTEREST_KEYWORDS) or ("personal interests",)
    goals = _matches(combined, _GOAL_KEYWORDS) or ("learn Python fundamentals",)
    pain_points = _matches(combined, _PAIN_KEYWORDS) or ("conditionals", "loops", "functions")
    level = _level_from_text(combined)
    confidence = min(95, 55 + 8 * len(interests) + 6 * len(pain_points) + 4 * len(answers))
    recommended_start = _recommended_start(pain_points, level)

    evidence = tuple(_evidence(prompt, answers, interests, pain_points))
    summary_interest = ", ".join(interests[:3])
    summary_pain = ", ".join(pain_points[:4])
    learner_summary = (
        f"A {level} learner who connects Python to {summary_interest} "
        f"and needs support with {summary_pain}."
    )

    return LearnerDiagnosis(
        level=level,
        learner_summary=learner_summary,
        interests=interests,
        goals=goals,
        pain_points=pain_points,
        preferred_examples=_preferred_examples(interests),
        recommended_start=recommended_start,
        confidence_score=confidence,
        evidence=evidence,
    )


def build_learning_path(
    dictionary: Any,
    diagnosis: LearnerDiagnosis | None = None,
) -> LearningPath:
    diagnosis = diagnosis or diagnose_learning_prompt(str(getattr(dictionary, "theme", "")))
    modules = tuple(
        _build_module(dictionary, blueprint, index + 1)
        for index, blueprint in enumerate(_prioritized_blueprints(diagnosis))
    )
    return LearningPath(
        title=f"Personal Python Path: {_theme_name(dictionary)}",
        diagnosis=diagnosis,
        modules=modules,
        proof_points=(
            "Every module includes a personal token, the real Python concept, and a runnable bridge example.",
            "Practice checks are concept-specific, not cosmetic theme matching.",
            "The path ends by moving from Personal Python toward standard Python.",
        ),
    )


def build_learning_module(
    dictionary: Any,
    module_id: str,
    diagnosis: LearnerDiagnosis | None = None,
) -> LearningModule:
    path = build_learning_path(dictionary, diagnosis)
    for module in path.modules:
        if module.module_id == module_id:
            return module
    raise KeyError(module_id)


def evaluate_practice_answer(task_id: str, answer: str) -> PracticeEvaluation:
    expected = _TASK_ANSWERS.get(task_id)
    if expected is None:
        return PracticeEvaluation(
            correct=False,
            score=0,
            feedback="Unknown practice task.",
            expected_answer="",
            next_step="Refresh the lesson and try a known task.",
        )

    normalized = _normalize_answer(answer)
    accepted = {_normalize_answer(value) for value in expected}
    correct = normalized in accepted
    primary = expected[0]
    return PracticeEvaluation(
        correct=correct,
        score=100 if correct else 35,
        feedback=(
            "Correct. You linked the personal surface back to the real Python behavior."
            if correct
            else "Not yet. Focus on what the Python concept does, then try the bridge example again."
        ),
        expected_answer=primary,
        next_step=(
            "Move to the next module."
            if correct
            else "Re-run the lesson code and compare the output with the prompt."
        ),
    )


def grade_practice_answers(answers: dict[str, str]) -> MasteryReport:
    module_results: dict[str, list[bool]] = {}
    for task_id, answer in answers.items():
        module_id = _TASK_MODULES.get(task_id, "unknown")
        module_results.setdefault(module_id, []).append(evaluate_practice_answer(task_id, answer).correct)

    modules: list[ModuleMastery] = []
    for module_id, results in sorted(module_results.items()):
        total = len(results)
        correct = sum(1 for item in results if item)
        score = int(round((correct / total) * 100)) if total else 0
        modules.append(
            ModuleMastery(
                module_id=module_id,
                score=score,
                passed=score >= 70,
                correct=correct,
                total=total,
                feedback=(
                    "Ready to bridge this module into real Python."
                    if score >= 70
                    else "Review the lesson bridge, then retry the missed task."
                ),
            )
        )

    total_answers = sum(module.total for module in modules)
    total_correct = sum(module.correct for module in modules)
    overall = int(round((total_correct / total_answers) * 100)) if total_answers else 0
    strengths = tuple(module.module_id for module in modules if module.passed) or ("visible output",)
    next_steps = tuple(
        f"Review {module.module_id}."
        for module in modules
        if not module.passed
    ) or ("Continue to the next lesson module.",)
    return MasteryReport(
        overall_score=overall,
        passed=overall >= 70 and bool(modules),
        modules=tuple(modules),
        strengths=strengths,
        next_steps=next_steps,
    )


def build_progress_proof(dictionary: Any) -> ProgressProof:
    modules = tuple(_build_module(dictionary, blueprint, index + 1) for index, blueprint in enumerate(_MODULE_BLUEPRINTS))
    coverage: dict[str, list[str]] = {}
    for module in modules:
        coverage[module.module_id] = [concept.python_concept for concept in module.concepts]
    return ProgressProof(
        headline="Personal Python core is ready to teach, bridge, compile, and run.",
        total_modules=len(modules),
        total_concepts=sum(len(module.concepts) for module in modules),
        runnable_programs=len(modules),
        bridge_modes=("personal syntax", "concept bridge", "real Python output"),
        concept_coverage=coverage,
    )


def _build_module(dictionary: Any, blueprint: dict[str, Any], order: int) -> LearningModule:
    concept_ids = tuple(blueprint["concept_ids"])
    concepts = tuple(_concept(dictionary, concept_id) for concept_id in concept_ids)
    module_id = str(blueprint["module_id"])
    return LearningModule(
        module_id=module_id,
        title=str(blueprint["title"]),
        goal=str(blueprint["goal"]),
        why_it_matters=str(blueprint["why"]),
        concepts=concepts,
        bridge_steps=_bridge_steps(concepts),
        lesson_steps=_lesson_steps(module_id, concepts),
        lesson_sections=_lesson_sections(module_id, dictionary),
        misconception_checks=_misconception_checks(module_id),
        success_criteria=_success_criteria(module_id),
        source_content=_module_source(dictionary, module_id),
        real_python_preview=_real_python_preview(module_id),
        expected_stdout=_expected_stdout(module_id),
        practice_tasks=_module_tasks(module_id, dictionary)
        + tuple(task for task in (_code_task(dictionary, module_id),) if task is not None),
        order=order,
    )


def _concept(dictionary: Any, concept_id: str) -> LearningConcept:
    python_concept, title, model = _CONCEPT_COPY.get(
        concept_id,
        (concept_id.removeprefix("py_"), "Python concept", "Use this as part of real Python thinking."),
    )
    token = _token(dictionary, concept_id)
    return LearningConcept(
        concept_id=concept_id,
        python_concept=python_concept,
        personal_token=token,
        title=title,
        mental_model=f"`{token}` is your personal cue for Python `{python_concept}`. {model}",
        real_python=python_concept,
    )


def _module_source(dictionary: Any, module_id: str) -> str:
    t = {concept_id: _token(dictionary, concept_id) for concept_id in _FALLBACK_TOKENS}
    theme_name = _header_value(_theme_name(dictionary))
    header = f"@theme: {theme_name}\n@language: python\n@version: 1\n---\n"

    if module_id == "signals-and-values":
        return header + f'{t["py_fn_print"]}("Personal Python ready")\ncv_score = 7\n{t["py_fn_print"]}(cv_score)\n'

    if module_id == "strings-and-text":
        return header + (
            'cv_message = "  codeverse, python  "\n'
            f'cv_clean = cv_message.{t["py_str_strip"]}().{t["py_str_replace"]}(",", "").{t["py_str_upper"]}()\n'
            f'{t["py_fn_print"]}(cv_clean)\n'
            f'cv_words = cv_clean.{t["py_str_lower"]}().{t["py_str_split"]}()\n'
            f'{t["py_fn_print"]}(cv_words)\n'
            f'{t["py_fn_print"]}({t["py_fn_str"]}(2026))\n'
        )

    if module_id == "numbers-and-conversion":
        return header + (
            f'cv_price = {t["py_fn_float"]}("12.5")\n'
            f'cv_count = {t["py_fn_int"]}("3")\n'
            f'{t["py_fn_print"]}({t["py_fn_round"]}(cv_price * cv_count, 1))\n'
            f'{t["py_fn_print"]}({t["py_fn_abs"]}(-8))\n'
            f'{t["py_fn_print"]}({t["py_fn_pow"]}(2, 3))\n'
        )

    if module_id == "imports-and-library":
        return header + (
            f'{t["py_kw_import"]} math {t["py_kw_as"]} cv_math\n'
            f'{t["py_fn_print"]}(cv_math.sqrt(81))\n'
            f'{t["py_kw_from"]} statistics {t["py_kw_import"]} mean {t["py_kw_as"]} cv_mean\n'
            f'{t["py_fn_print"]}(cv_mean([2, 4, 6]))\n'
        )

    if module_id == "choices":
        return header + (
            "cv_score = 75\n"
            f'{t["py_kw_if"]} cv_score >= 80:\n'
            f'    {t["py_fn_print"]}("mastered")\n'
            f'{t["py_kw_elif"]} cv_score >= 50:\n'
            f'    {t["py_fn_print"]}("keep practicing")\n'
            f'{t["py_kw_else"]}:\n'
            f'    {t["py_fn_print"]}("start small")\n'
        )

    if module_id == "routes":
        return header + (
            f'{t["py_kw_for"]} cv_step {t["py_kw_in"]} {t["py_fn_range"]}(1, 4):\n'
            f'    {t["py_fn_print"]}(cv_step)\n'
        )

    if module_id == "loop-control":
        return header + (
            "cv_step = 0\n"
            f'{t["py_kw_while"]} cv_step < 5:\n'
            "    cv_step = cv_step + 1\n"
            f'    {t["py_kw_if"]} cv_step == 2:\n'
            f'        {t["py_kw_continue"]}\n'
            f'    {t["py_kw_if"]} cv_step == 4:\n'
            f'        {t["py_kw_break"]}\n'
            f'    {t["py_fn_print"]}(cv_step)\n'
        )

    if module_id == "tools":
        return header + (
            f'{t["py_kw_def"]} cv_reward(cv_base):\n'
            f'    {t["py_kw_return"]} cv_base + 50\n'
            f'{t["py_fn_print"]}(cv_reward(100))\n'
        )

    if module_id == "logic":
        return header + (
            f'cv_ready = {t["py_kw_true"]}\n'
            f'cv_blocked = {t["py_kw_false"]}\n'
            f'cv_value = {t["py_kw_none"]}\n'
            f'{t["py_kw_if"]} cv_ready {t["py_kw_and"]} {t["py_kw_not"]} cv_blocked:\n'
            f'    {t["py_fn_print"]}("go")\n'
            f'{t["py_kw_if"]} cv_value == {t["py_kw_none"]} {t["py_kw_or"]} cv_blocked:\n'
            f'    {t["py_fn_print"]}("empty")\n'
        )

    if module_id == "collections":
        return header + (
            f'cv_scores = {t["py_fn_list"]}([100])\n'
            f'cv_scores.{t["py_list_append"]}(150)\n'
            f'cv_profile = {t["py_fn_dict"]}({{"best": 150}})\n'
            f'{t["py_fn_print"]}(cv_scores)\n'
            f'{t["py_fn_print"]}(cv_profile.{t["py_dict_get"]}("best"))\n'
            f'{t["py_fn_print"]}({t["py_fn_len"]}(cv_scores))\n'
        )

    if module_id == "tuples-and-sets":
        return header + (
            f'cv_route = {t["py_fn_tuple"]}(["dock", "market"])\n'
            f'cv_tags = {t["py_fn_set"]}(["red", "blue", "red"])\n'
            f'cv_tags.{t["py_set_add"]}("green")\n'
            f'cv_tags.{t["py_set_discard"]}("blue")\n'
            f'cv_backup = {t["py_fn_set"]}(["yellow"])\n'
            f'cv_all = cv_tags.{t["py_set_union"]}(cv_backup)\n'
            f'{t["py_fn_print"]}(cv_route)\n'
            f'{t["py_fn_print"]}({t["py_fn_len"]}(cv_all))\n'
            f'{t["py_fn_print"]}("red" {t["py_kw_in"]} cv_all)\n'
        )

    if module_id == "files-and-context":
        return header + (
            f'{t["py_kw_with"]} {t["py_fn_open"]}("cv_lesson_note.txt", "w") {t["py_kw_as"]} cv_file:\n'
            f'    cv_file.{t["py_file_write"]}("Python files stay safe")\n'
            f'{t["py_kw_with"]} {t["py_fn_open"]}("cv_lesson_note.txt", "r") {t["py_kw_as"]} cv_file:\n'
            f'    cv_note = cv_file.{t["py_file_read"]}()\n'
            f'    {t["py_fn_print"]}(cv_note)\n'
        )

    if module_id == "objects":
        return header + (
            f'{t["py_kw_class"]} CvLearner:\n'
            '    name = "student"\n'
            "    points = 0\n\n"
            f'    {t["py_kw_def"]} add_points(amount):\n'
            "        self.points = self.points + amount\n"
            f'        {t["py_kw_return"]} self.points\n\n'
            'cv_user = CvLearner("Ada", 10)\n'
            "cv_user.add_points(5)\n"
            f'{t["py_fn_print"]}(cv_user.name)\n'
            f'{t["py_fn_print"]}(cv_user.points)\n'
        )

    return header + (
        f'{t["py_kw_try"]}:\n'
        f'    {t["py_fn_print"]}("attempt")\n'
        f'{t["py_kw_except"]} Exception:\n'
        f'    {t["py_fn_print"]}("handled")\n'
        f'{t["py_kw_finally"]}:\n'
        f'    {t["py_fn_print"]}("cleanup")\n'
    )


def _module_tasks(module_id: str, dictionary: Any) -> tuple[PracticeTask, ...]:
    t = {concept_id: _token(dictionary, concept_id) for concept_id in _FALLBACK_TOKENS}
    if module_id == "signals-and-values":
        return (
            PracticeTask(
                id="signals-output",
                kind="predict_output",
                concept_id="py_fn_print",
                prompt=f"What appears first when `{t['py_fn_print']}` runs in this lesson?",
                expected_answer="Personal Python ready",
                hint="Look at the first output call in the lesson source.",
                explanation="print displays its argument on a new output line.",
            ),
            PracticeTask(
                id="signals-translate",
                kind="translate_token",
                concept_id="py_fn_print",
                prompt=f"Which real Python concept does `{t['py_fn_print']}` bridge to?",
                expected_answer="print",
                hint="The token is the visible-output concept.",
                explanation="Personal tokens must always bridge back to real Python concepts.",
            ),
            PracticeTask(
                id="signals-number-expression",
                kind="predict_output",
                concept_id="py_fn_print",
                prompt="What does print(7 + 1) display?",
                expected_answer="8",
                choices=("8", "71", "7 + 1"),
                hint="Python evaluates the arithmetic expression before printing its result.",
                explanation="The integers are added first, so print receives the value 8.",
            ),
            PracticeTask(
                id="signals-variable-update",
                kind="predict_output",
                concept_id="py_fn_print",
                prompt="After cv_score = 7 followed by cv_score = 9, what does print(cv_score) display?",
                expected_answer="9",
                choices=("9", "7", "cv_score"),
                hint="The second assignment replaces the value associated with the name.",
                explanation="A variable read uses its most recently assigned value.",
            ),
            PracticeTask(
                id="signals-multiple-values",
                kind="predict_output",
                concept_id="py_fn_print",
                prompt='What does print("score:", 12) display?',
                expected_answer="score: 12",
                choices=("score: 12", "score:12", "12 score:"),
                hint="print inserts one space between comma-separated arguments by default.",
                explanation="Multiple print arguments are displayed in order with a space separator.",
            ),
        )
    if module_id == "strings-and-text":
        return (
            PracticeTask(
                id="strings-clean",
                kind="concept_reasoning",
                concept_id="py_str_strip",
                prompt="What does strip remove when called without arguments?",
                expected_answer="whitespace at both ends",
                choices=("all spaces everywhere", "whitespace at both ends", "punctuation"),
                hint="It works on the outside edges, not the middle of the text.",
                explanation="strip removes leading and trailing whitespace while preserving internal spaces.",
            ),
            PracticeTask(
                id="strings-translate",
                kind="translate_token",
                concept_id="py_str_upper",
                prompt=f"Which real Python method does `{t['py_str_upper']}` bridge to?",
                expected_answer="upper",
                choices=("split", "replace", "upper"),
                hint="This method creates the all-capitals version of a string.",
                explanation="str.upper returns a new uppercase string; it does not mutate the original.",
            ),
        )
    if module_id == "numbers-and-conversion":
        return (
            PracticeTask(
                id="numbers-int-truncation",
                kind="predict_output",
                concept_id="py_fn_int",
                prompt="What whole number does int(3.9) produce?",
                expected_answer="3",
                choices=("3", "4", "3.9"),
                hint="Integer conversion removes the fractional part; it does not round to the nearest number.",
                explanation="int(3.9) truncates toward zero and produces 3.",
            ),
            PracticeTask(
                id="numbers-absolute-value",
                kind="predict_output",
                concept_id="py_fn_abs",
                prompt="What value does abs(-8) return?",
                expected_answer="8",
                choices=("8", "-8", "0"),
                hint="Absolute value is the distance from zero.",
                explanation="The distance between -8 and zero is 8.",
            ),
        )
    if module_id == "imports-and-library":
        return (
            PracticeTask(
                id="imports-module-access",
                kind="concept_reasoning",
                concept_id="py_kw_import",
                prompt="After import math as cv_math, how do you access square root?",
                expected_answer="cv_math.sqrt",
                choices=("cv_math.sqrt", "sqrt.cv_math", "math import sqrt"),
                hint="Use the local module name, then a dot, then the tool name.",
                explanation="A module alias becomes the namespace used to access that module's members.",
            ),
            PracticeTask(
                id="imports-from-purpose",
                kind="concept_reasoning",
                concept_id="py_kw_from",
                prompt="What does from statistics import mean place in the current scope?",
                expected_answer="mean",
                choices=("mean", "every statistics tool", "a copied statistics file"),
                hint="The statement selects one named member.",
                explanation="from-import binds the selected member directly in the current module.",
            ),
        )
    if module_id == "choices":
        return (
            PracticeTask(
                id="choices-branch",
                kind="predict_branch",
                concept_id="py_kw_elif",
                prompt="With cv_score = 75, which branch message prints?",
                expected_answer="keep practicing",
                choices=("mastered", "keep practicing", "start small"),
                hint="75 is below 80 but above 50.",
                explanation="if fails, elif succeeds, so else is skipped.",
            ),
            PracticeTask(
                id="choices-order",
                kind="order_reasoning",
                concept_id="py_kw_if",
                prompt="Which condition is checked first in an if/elif/else chain?",
                expected_answer="if",
                choices=("else", "elif", "if"),
                hint="Python starts at the top of the chain.",
                explanation="The first if condition decides whether later branches are needed.",
            ),
        )
    if module_id == "routes":
        return (
            PracticeTask(
                id="routes-count",
                kind="predict_output",
                concept_id="py_fn_range",
                prompt="How many numbers does range(1, 4) produce?",
                expected_answer="3",
                hint="The start is included, the stop is excluded.",
                explanation="range(1, 4) yields 1, 2, and 3.",
            ),
            PracticeTask(
                id="routes-translate",
                kind="translate_token",
                concept_id="py_kw_for",
                prompt=f"Which Python concept does `{t['py_kw_for']}` bridge to?",
                expected_answer="for",
                hint="This token starts the repeated route.",
                explanation="for repeats a block for each item in a sequence.",
            ),
        )
    if module_id == "loop-control":
        return (
            PracticeTask(
                id="loop-control-output",
                kind="predict_output",
                concept_id="py_kw_continue",
                prompt="Which numbers print before the loop stops?",
                expected_answer="1 3",
                choices=("1 2 3", "1 3", "1 3 4"),
                hint="2 is skipped by continue, 4 stops the loop before printing.",
                explanation="continue skips the current turn; break exits the loop.",
            ),
        )
    if module_id == "tools":
        return (
            PracticeTask(
                id="tools-return",
                kind="predict_output",
                concept_id="py_kw_return",
                prompt="What value does cv_reward(100) return?",
                expected_answer="150",
                hint="The function adds 50 to the input.",
                explanation="return sends the computed value back to the caller.",
            ),
            PracticeTask(
                id="tools-translate",
                kind="translate_token",
                concept_id="py_kw_def",
                prompt=f"Which real Python concept does `{t['py_kw_def']}` bridge to?",
                expected_answer="def",
                hint="This token names a reusable tool.",
                explanation="def creates a named function in real Python.",
            ),
        )
    if module_id == "logic":
        return (
            PracticeTask(
                id="logic-output",
                kind="predict_output",
                concept_id="py_kw_and",
                prompt="What are the two printed messages in the logic lesson?",
                expected_answer="go empty",
                choices=("go empty", "empty go", "blocked empty"),
                hint="The first condition is true and the second also becomes true.",
                explanation="and requires both sides; or accepts either side.",
            ),
        )
    if module_id == "collections":
        return (
            PracticeTask(
                id="collections-length",
                kind="predict_output",
                concept_id="py_fn_len",
                prompt="After appending 150, what is len(cv_scores)?",
                expected_answer="2",
                hint="The list starts with one value and append adds one more.",
                explanation="len counts the number of list items.",
            ),
            PracticeTask(
                id="collections-get",
                kind="predict_output",
                concept_id="py_dict_get",
                prompt="What value does cv_profile.get('best') read?",
                expected_answer="150",
                hint="The dictionary stores best as 150.",
                explanation="dict.get reads a value by key.",
            ),
        )
    if module_id == "tuples-and-sets":
        return (
            PracticeTask(
                id="tuples-fixed-record",
                kind="concept_reasoning",
                concept_id="py_fn_tuple",
                prompt="Which collection is designed for a fixed, ordered record?",
                expected_answer="tuple",
                choices=("tuple", "set", "dict"),
                hint="Its order is stable, but its items cannot be replaced in place.",
                explanation="A tuple is an ordered, immutable sequence that works well for stable records.",
            ),
            PracticeTask(
                id="sets-unique-count",
                kind="predict_output",
                concept_id="py_fn_set",
                prompt='How many values remain in set(["red", "blue", "red"])?',
                expected_answer="2",
                choices=("2", "3", "1"),
                hint="A set keeps only one copy of each equal value.",
                explanation="The repeated red value is removed, leaving red and blue.",
            ),
        )
    if module_id == "files-and-context":
        return (
            PracticeTask(
                id="files-write-mode",
                kind="concept_reasoning",
                concept_id="py_fn_open",
                prompt="Which open mode creates a text file or replaces its existing contents?",
                expected_answer="w",
                choices=("w", "r", "a"),
                hint="This mode begins a fresh write operation.",
                explanation="Mode w opens a file for writing and truncates existing contents.",
            ),
            PracticeTask(
                id="files-context-cleanup",
                kind="concept_reasoning",
                concept_id="py_kw_with",
                prompt="What does with guarantee when the file block ends?",
                expected_answer="the file is closed",
                choices=("the file is closed", "the file is deleted", "the text is printed"),
                hint="Think about resource cleanup, including when an error occurs.",
                explanation="The context manager closes the file automatically when control leaves the with block.",
            ),
        )
    if module_id == "objects":
        return (
            PracticeTask(
                id="objects-output",
                kind="predict_output",
                concept_id="py_kw_class",
                prompt="What name prints from the object lesson?",
                expected_answer="Ada",
                hint="The object is created with CvLearner('Ada', 10).",
                explanation="The class constructor stores the provided field value.",
            ),
        )
    return (
        PracticeTask(
            id="errors-cleanup",
            kind="predict_output",
            concept_id="py_kw_finally",
            prompt="Which cleanup message always prints at the end?",
            expected_answer="cleanup",
            hint="finally runs after the attempt whether or not an exception happened.",
            explanation="finally is for cleanup behavior.",
        ),
    )


# ---------------------------------------------------------------- code tasks
#
# One "write the code yourself" exercise per module: the student edits a
# starter program (in their personal syntax) until it prints the goal output.
# Evaluation is behavioral — compile, run, compare stdout — via the
# /practice/run route, not string matching. Each spec also carries a hidden
# reference solution so tests can PROVE every exercise is solvable for any
# theme dictionary.

_CODE_TASK_SPECS: dict[str, dict[str, Any]] = {
    "signals-and-values": {
        "id": "signals-code",
        "concept_id": "py_fn_print",
        "prompt": 'Complete the program so it prints "hello" and then the number 12 on its own line.',
        "expected_stdout": "hello\n12\n",
        "hint": "Add one more output line below the first one, printing 12.",
        "explanation": "Each print call writes one line of output.",
        "starter": lambda t: (
            f'{t["py_fn_print"]}("hello")\n'
            "# TODO: add one more line that prints the number 12\n"
        ),
        "solution": lambda t: (
            f'{t["py_fn_print"]}("hello")\n'
            f'{t["py_fn_print"]}(12)\n'
        ),
    },
    "strings-and-text": {
        "id": "strings-code",
        "concept_id": "py_str_replace",
        "prompt": 'Complete the text pipeline so it prints exactly "CODEVERSE PYTHON".',
        "expected_stdout": "CODEVERSE PYTHON\n",
        "hint": "Trim the edges, replace the comma with a space, then convert the result to uppercase.",
        "explanation": "String methods can be chained because each method returns a new string.",
        "starter": lambda t: (
            'cv_text = "  codeverse,python  "\n'
            f'cv_clean = cv_text.{t["py_str_strip"]}()  # TODO: replace the comma and uppercase the result\n'
            f'{t["py_fn_print"]}(cv_clean)\n'
        ),
        "solution": lambda t: (
            'cv_text = "  codeverse,python  "\n'
            f'cv_clean = cv_text.{t["py_str_strip"]}().{t["py_str_replace"]}(",", " ").{t["py_str_upper"]}()\n'
            f'{t["py_fn_print"]}(cv_clean)\n'
        ),
    },
    "numbers-and-conversion": {
        "id": "numbers-and-conversion-code",
        "concept_id": "py_fn_int",
        "prompt": 'Use integer conversion so adding 9 prints exactly "30" instead of "30.0".',
        "expected_stdout": "30\n",
        "hint": "Replace the decimal conversion token with your whole-number conversion token.",
        "explanation": "int converts compatible numeric text into an integer that participates in numeric addition.",
        "starter": lambda t: (
            f'cv_value = {t["py_fn_float"]}("21")  # TODO: convert to a whole number instead\n'
            f'{t["py_fn_print"]}(cv_value + 9)\n'
        ),
        "solution": lambda t: (
            f'cv_value = {t["py_fn_int"]}("21")\n'
            f'{t["py_fn_print"]}(cv_value + 9)\n'
        ),
    },
    "imports-and-library": {
        "id": "imports-and-library-code",
        "concept_id": "py_kw_from",
        "prompt": 'Import sqrt instead of floor so the program prints exactly "9.0".',
        "expected_stdout": "9.0\n",
        "hint": "Keep the alias cv_calculate, but select sqrt from math.",
        "explanation": "A from-import can swap the selected standard-library tool while preserving a useful local alias.",
        "starter": lambda t: (
            f'{t["py_kw_from"]} math {t["py_kw_import"]} floor {t["py_kw_as"]} cv_calculate\n'
            f'{t["py_fn_print"]}(cv_calculate(81))\n'
        ),
        "solution": lambda t: (
            f'{t["py_kw_from"]} math {t["py_kw_import"]} sqrt {t["py_kw_as"]} cv_calculate\n'
            f'{t["py_fn_print"]}(cv_calculate(81))\n'
        ),
    },
    "choices": {
        "id": "choices-code",
        "concept_id": "py_kw_elif",
        "prompt": 'Change cv_score so the program prints exactly "keep practicing".',
        "expected_stdout": "keep practicing\n",
        "hint": "The middle branch needs a score of at least 50 but below 80.",
        "explanation": "elif runs only when the first condition fails and its own condition passes.",
        "starter": lambda t: (
            "cv_score = 30  # TODO: change this value\n"
            f'{t["py_kw_if"]} cv_score >= 80:\n'
            f'    {t["py_fn_print"]}("mastered")\n'
            f'{t["py_kw_elif"]} cv_score >= 50:\n'
            f'    {t["py_fn_print"]}("keep practicing")\n'
            f'{t["py_kw_else"]}:\n'
            f'    {t["py_fn_print"]}("start small")\n'
        ),
        "solution": lambda t: (
            "cv_score = 75\n"
            f'{t["py_kw_if"]} cv_score >= 80:\n'
            f'    {t["py_fn_print"]}("mastered")\n'
            f'{t["py_kw_elif"]} cv_score >= 50:\n'
            f'    {t["py_fn_print"]}("keep practicing")\n'
            f'{t["py_kw_else"]}:\n'
            f'    {t["py_fn_print"]}("start small")\n'
        ),
    },
    "routes": {
        "id": "routes-code",
        "concept_id": "py_fn_range",
        "prompt": "Adjust the range so the program prints the numbers 1 through 5.",
        "expected_stdout": "1\n2\n3\n4\n5\n",
        "hint": "range stops one number BEFORE its second value.",
        "explanation": "range(1, 6) produces 1, 2, 3, 4, 5 — the stop value is excluded.",
        "starter": lambda t: (
            f'{t["py_kw_for"]} cv_step {t["py_kw_in"]} {t["py_fn_range"]}(1, 3):  # TODO: reach 5\n'
            f'    {t["py_fn_print"]}(cv_step)\n'
        ),
        "solution": lambda t: (
            f'{t["py_kw_for"]} cv_step {t["py_kw_in"]} {t["py_fn_range"]}(1, 6):\n'
            f'    {t["py_fn_print"]}(cv_step)\n'
        ),
    },
    "loop-control": {
        "id": "loop-control-code",
        "concept_id": "py_kw_continue",
        "prompt": "Skip the number 2 so the program prints 1, 3, 4, 5 — one per line.",
        "expected_stdout": "1\n3\n4\n5\n",
        "hint": "Inside the loop, check for 2 and use your skip-forward token before printing.",
        "explanation": "continue jumps to the next loop turn without running the lines below it.",
        "starter": lambda t: (
            "cv_step = 0\n"
            f'{t["py_kw_while"]} cv_step < 5:\n'
            "    cv_step = cv_step + 1\n"
            "    # TODO: skip printing when cv_step == 2\n"
            f'    {t["py_fn_print"]}(cv_step)\n'
        ),
        "solution": lambda t: (
            "cv_step = 0\n"
            f'{t["py_kw_while"]} cv_step < 5:\n'
            "    cv_step = cv_step + 1\n"
            f'    {t["py_kw_if"]} cv_step == 2:\n'
            f'        {t["py_kw_continue"]}\n'
            f'    {t["py_fn_print"]}(cv_step)\n'
        ),
    },
    "tools": {
        "id": "tools-code",
        "concept_id": "py_kw_return",
        "prompt": "Fix the function so cv_double(8) returns 16.",
        "expected_stdout": "16\n",
        "hint": "Multiply the input by 2 before returning it.",
        "explanation": "return sends the computed value back to the caller.",
        "starter": lambda t: (
            f'{t["py_kw_def"]} cv_double(cv_value):\n'
            f'    {t["py_kw_return"]} cv_value  # TODO: double it\n'
            f'{t["py_fn_print"]}(cv_double(8))\n'
        ),
        "solution": lambda t: (
            f'{t["py_kw_def"]} cv_double(cv_value):\n'
            f'    {t["py_kw_return"]} cv_value * 2\n'
            f'{t["py_fn_print"]}(cv_double(8))\n'
        ),
    },
    "logic": {
        "id": "logic-code",
        "concept_id": "py_kw_and",
        "prompt": 'Flip one flag so the gate opens and the program prints "go".',
        "expected_stdout": "go\n",
        "hint": "The gate needs cv_ready to be true while cv_blocked stays false.",
        "explanation": "and requires both sides to pass; not flips a boolean.",
        "starter": lambda t: (
            f'cv_ready = {t["py_kw_false"]}  # TODO: flip this flag\n'
            f'cv_blocked = {t["py_kw_false"]}\n'
            f'{t["py_kw_if"]} cv_ready {t["py_kw_and"]} {t["py_kw_not"]} cv_blocked:\n'
            f'    {t["py_fn_print"]}("go")\n'
        ),
        "solution": lambda t: (
            f'cv_ready = {t["py_kw_true"]}\n'
            f'cv_blocked = {t["py_kw_false"]}\n'
            f'{t["py_kw_if"]} cv_ready {t["py_kw_and"]} {t["py_kw_not"]} cv_blocked:\n'
            f'    {t["py_fn_print"]}("go")\n'
        ),
    },
    "collections": {
        "id": "collections-code",
        "concept_id": "py_list_append",
        "prompt": "Append 150 to the list so the printed length becomes 2.",
        "expected_stdout": "2\n",
        "hint": "Use your add-to-list token on cv_scores before measuring the length.",
        "explanation": "append adds one item to the end of the list.",
        "starter": lambda t: (
            f'cv_scores = {t["py_fn_list"]}([100])\n'
            "# TODO: append 150 to cv_scores\n"
            f'{t["py_fn_print"]}({t["py_fn_len"]}(cv_scores))\n'
        ),
        "solution": lambda t: (
            f'cv_scores = {t["py_fn_list"]}([100])\n'
            f'cv_scores.{t["py_list_append"]}(150)\n'
            f'{t["py_fn_print"]}({t["py_fn_len"]}(cv_scores))\n'
        ),
    },
    "tuples-and-sets": {
        "id": "tuples-and-sets-code",
        "concept_id": "py_set_add",
        "prompt": 'Add "green" to the unique tags so the program prints 3 and then True.',
        "expected_stdout": "3\nTrue\n",
        "hint": "Use your add-to-set token on cv_tags before the two output lines.",
        "explanation": "set.add inserts a new unique value; membership then confirms that it is present.",
        "starter": lambda t: (
            f'cv_tags = {t["py_fn_set"]}(["red", "blue", "red"])\n'
            '# TODO: add "green" to cv_tags\n'
            f'{t["py_fn_print"]}({t["py_fn_len"]}(cv_tags))\n'
            f'{t["py_fn_print"]}("green" {t["py_kw_in"]} cv_tags)\n'
        ),
        "solution": lambda t: (
            f'cv_tags = {t["py_fn_set"]}(["red", "blue", "red"])\n'
            f'cv_tags.{t["py_set_add"]}("green")\n'
            f'{t["py_fn_print"]}({t["py_fn_len"]}(cv_tags))\n'
            f'{t["py_fn_print"]}("green" {t["py_kw_in"]} cv_tags)\n'
        ),
    },
    "files-and-context": {
        "id": "files-and-context-code",
        "concept_id": "py_file_read",
        "prompt": 'Read the saved file into cv_message so the program prints exactly "saved".',
        "expected_stdout": "saved\n",
        "hint": "Inside the read context, call your read-text token on cv_file and assign the result to cv_message.",
        "explanation": "Opening with r provides a readable file object; read returns its stored text.",
        "starter": lambda t: (
            f'{t["py_kw_with"]} {t["py_fn_open"]}("cv_practice_note.txt", "w") {t["py_kw_as"]} cv_file:\n'
            f'    cv_file.{t["py_file_write"]}("saved")\n'
            f'{t["py_kw_with"]} {t["py_fn_open"]}("cv_practice_note.txt", "r") {t["py_kw_as"]} cv_file:\n'
            '    cv_message = ""  # TODO: read from cv_file\n'
            f'    {t["py_fn_print"]}(cv_message)\n'
        ),
        "solution": lambda t: (
            f'{t["py_kw_with"]} {t["py_fn_open"]}("cv_practice_note.txt", "w") {t["py_kw_as"]} cv_file:\n'
            f'    cv_file.{t["py_file_write"]}("saved")\n'
            f'{t["py_kw_with"]} {t["py_fn_open"]}("cv_practice_note.txt", "r") {t["py_kw_as"]} cv_file:\n'
            f'    cv_message = cv_file.{t["py_file_read"]}()\n'
            f'    {t["py_fn_print"]}(cv_message)\n'
        ),
    },
    "errors": {
        "id": "errors-code",
        "concept_id": "py_kw_finally",
        "prompt": 'Fix the cleanup step so the program prints "attempt" and then "cleanup".',
        "expected_stdout": "attempt\ncleanup\n",
        "hint": "The finally block always runs — change what it prints.",
        "explanation": "finally runs after try/except no matter what happened.",
        "starter": lambda t: (
            f'{t["py_kw_try"]}:\n'
            f'    {t["py_fn_print"]}("attempt")\n'
            f'{t["py_kw_except"]} Exception:\n'
            f'    {t["py_fn_print"]}("handled")\n'
            f'{t["py_kw_finally"]}:\n'
            f'    {t["py_fn_print"]}("todo")  # TODO: print "cleanup" instead\n'
        ),
        "solution": lambda t: (
            f'{t["py_kw_try"]}:\n'
            f'    {t["py_fn_print"]}("attempt")\n'
            f'{t["py_kw_except"]} Exception:\n'
            f'    {t["py_fn_print"]}("handled")\n'
            f'{t["py_kw_finally"]}:\n'
            f'    {t["py_fn_print"]}("cleanup")\n'
        ),
    },
    "objects": {
        "id": "objects-code",
        "concept_id": "py_kw_class",
        "prompt": 'Print the tool\'s name so the program outputs "hammer".',
        "expected_stdout": "hammer\n",
        "hint": "Read the name attribute from cv_tool with a dot.",
        "explanation": "Objects carry their data as attributes you can read with a dot.",
        "starter": lambda t: (
            f'{t["py_kw_class"]} CvTool:\n'
            '    name = "starter"\n\n'
            'cv_tool = CvTool("hammer")\n'
            "# TODO: print cv_tool.name\n"
        ),
        "solution": lambda t: (
            f'{t["py_kw_class"]} CvTool:\n'
            '    name = "starter"\n\n'
            'cv_tool = CvTool("hammer")\n'
            f'{t["py_fn_print"]}(cv_tool.name)\n'
        ),
    },
}


# ------------------------------------------------------------ bridge capstone
#
# The graduation exercise: the learner rewrites a program they've been reading
# in their PERSONAL syntax back into standard, real Python — proving the
# personal layer was a scaffold they can now remove. Evaluation is behavioral
# AND anti-cheating: the submission must run as plain Python, print the goal
# output, and NOT contain any of the learner's personal tokens (which would
# mean they pasted the personal version instead of truly translating).

#: concepts the capstone program exercises, in the order they appear.
_BRIDGE_CONCEPTS: tuple[str, ...] = (
    "py_kw_def",
    "py_kw_for",
    "py_kw_in",
    "py_kw_if",
    "py_kw_return",
    "py_fn_print",
)


@dataclass(frozen=True)
class BridgeChallenge:
    prompt: str
    #: the same program written in the learner's personal syntax (what they
    #: translate FROM).
    personal_reference: str
    expected_stdout: str
    #: real Python keywords the learner should use (a hint, not the solution).
    real_keywords: tuple[str, ...]
    #: personal tokens that must NOT appear in a real-Python answer.
    forbidden_tokens: tuple[str, ...]


def _bridge_program(tokens: dict[str, str]) -> str:
    """The capstone program body, rendered with whatever tokens are given
    (personal tokens -> personal reference; real keywords -> solution)."""
    return (
        f'{tokens["py_kw_def"]} cv_bonus(cv_levels):\n'
        "    cv_total = 0\n"
        f'    {tokens["py_kw_for"]} cv_level {tokens["py_kw_in"]} cv_levels:\n'
        f'        {tokens["py_kw_if"]} cv_level >= 3:\n'
        "            cv_total = cv_total + cv_level\n"
        f'    {tokens["py_kw_return"]} cv_total\n\n'
        f'{tokens["py_fn_print"]}(cv_bonus([1, 2, 3, 4]))\n'
    )


_BRIDGE_EXPECTED_STDOUT = "7\n"


def build_bridge_challenge(dictionary: Any) -> BridgeChallenge:
    personal_tokens = {cid: _token(dictionary, cid) for cid in _FALLBACK_TOKENS}
    real_tokens = {cid: _CONCEPT_COPY[cid][0] for cid in _BRIDGE_CONCEPTS}

    forbidden = tuple(
        personal_tokens[cid]
        for cid in _BRIDGE_CONCEPTS
        if personal_tokens[cid] != real_tokens[cid]
    )
    return BridgeChallenge(
        prompt=(
            "Rewrite this program in real, standard Python. Use the actual "
            "Python keywords (def, for, in, if, return, print) instead of your "
            "personal tokens — it should print the same result."
        ),
        personal_reference=_code_header(dictionary) + _bridge_program(personal_tokens),
        expected_stdout=_BRIDGE_EXPECTED_STDOUT,
        real_keywords=tuple(real_tokens[cid] for cid in _BRIDGE_CONCEPTS),
        forbidden_tokens=forbidden,
    )


def bridge_reference_solution(dictionary: Any) -> str:
    """Hidden real-Python solution — used by tests to prove the capstone is
    solvable; never sent to the learner."""
    real_tokens = {cid: _CONCEPT_COPY[cid][0] for cid in _BRIDGE_CONCEPTS}
    return _bridge_program(real_tokens)


def bridge_expected_stdout() -> str:
    return _BRIDGE_EXPECTED_STDOUT


def code_task_expected_stdout(task_id: str) -> str | None:
    for spec in _CODE_TASK_SPECS.values():
        if spec["id"] == task_id:
            return str(spec["expected_stdout"])
    return None


def code_task_module_id(task_id: str) -> str | None:
    """Which learning module a write_code task belongs to (for progress)."""
    for module_id, spec in _CODE_TASK_SPECS.items():
        if spec["id"] == task_id:
            return module_id
    return None


def code_task_reference_solution(dictionary: Any, task_id: str) -> str | None:
    """Hidden, per-theme reference solution — used by tests to prove every
    code exercise is actually solvable, never shown to the student."""
    for spec in _CODE_TASK_SPECS.values():
        if spec["id"] == task_id:
            tokens = {cid: _token(dictionary, cid) for cid in _FALLBACK_TOKENS}
            return _code_header(dictionary) + spec["solution"](tokens)
    return None


def _code_task(dictionary: Any, module_id: str) -> PracticeTask | None:
    spec = _CODE_TASK_SPECS.get(module_id)
    if spec is None:
        return None
    tokens = {cid: _token(dictionary, cid) for cid in _FALLBACK_TOKENS}
    return PracticeTask(
        id=str(spec["id"]),
        kind="write_code",
        concept_id=str(spec["concept_id"]),
        prompt=str(spec["prompt"]),
        expected_answer=str(spec["expected_stdout"]),
        starter_source=_code_header(dictionary) + spec["starter"](tokens),
        hint=str(spec["hint"]),
        explanation=str(spec["explanation"]),
    )


def _code_header(dictionary: Any) -> str:
    theme_name = _header_value(_theme_name(dictionary))
    return f"@theme: {theme_name}\n@language: python\n@version: 1\n---\n"


_TASK_ANSWERS: dict[str, tuple[str, ...]] = {
    "signals-output": ("Personal Python ready",),
    "signals-translate": ("print",),
    "signals-number-expression": ("8", "eight"),
    "signals-variable-update": ("9", "nine"),
    "signals-multiple-values": ("score: 12",),
    "strings-clean": ("whitespace at both ends",),
    "strings-translate": ("upper",),
    "numbers-int-truncation": ("3", "three"),
    "numbers-absolute-value": ("8", "eight"),
    "imports-module-access": ("cv_math.sqrt",),
    "imports-from-purpose": ("mean",),
    "choices-branch": ("keep practicing",),
    "choices-order": ("if",),
    "routes-count": ("3", "three"),
    "routes-translate": ("for",),
    "loop-control-output": ("1 3", "1\n3", "1, 3"),
    "tools-return": ("150",),
    "tools-translate": ("def",),
    "logic-output": ("go empty", "go\nempty"),
    "collections-length": ("2", "two"),
    "collections-get": ("150",),
    "tuples-fixed-record": ("tuple",),
    "sets-unique-count": ("2", "two"),
    "files-write-mode": ("w", "write", "write mode"),
    "files-context-cleanup": ("the file is closed", "file is closed", "closed", "closes the file"),
    "objects-output": ("Ada", "ada"),
    "errors-cleanup": ("cleanup",),
}

_TASK_MODULES: dict[str, str] = {
    "signals-output": "signals-and-values",
    "signals-translate": "signals-and-values",
    "signals-number-expression": "signals-and-values",
    "signals-variable-update": "signals-and-values",
    "signals-multiple-values": "signals-and-values",
    "strings-clean": "strings-and-text",
    "strings-translate": "strings-and-text",
    "numbers-int-truncation": "numbers-and-conversion",
    "numbers-absolute-value": "numbers-and-conversion",
    "imports-module-access": "imports-and-library",
    "imports-from-purpose": "imports-and-library",
    "choices-branch": "choices",
    "choices-order": "choices",
    "routes-count": "routes",
    "routes-translate": "routes",
    "loop-control-output": "loop-control",
    "tools-return": "tools",
    "tools-translate": "tools",
    "logic-output": "logic",
    "collections-length": "collections",
    "collections-get": "collections",
    "tuples-fixed-record": "tuples-and-sets",
    "sets-unique-count": "tuples-and-sets",
    "files-write-mode": "files-and-context",
    "files-context-cleanup": "files-and-context",
    "objects-output": "objects",
    "errors-cleanup": "errors",
}


def _bridge_steps(concepts: tuple[LearningConcept, ...]) -> tuple[str, ...]:
    steps: list[str] = []
    for concept in concepts:
        steps.append(f"Personal: {concept.personal_token} -> Python: {concept.python_concept}")
    return tuple(steps)


def _lesson_sections(module_id: str, dictionary: Any) -> tuple[LessonSection, ...]:
    if module_id == "strings-and-text":
        output = _token(dictionary, "py_fn_print")
        convert = _token(dictionary, "py_fn_str")
        strip = _token(dictionary, "py_str_strip")
        replace = _token(dictionary, "py_str_replace")
        upper = _token(dictionary, "py_str_upper")
        lower = _token(dictionary, "py_str_lower")
        split = _token(dictionary, "py_str_split")
        return (
            LessonSection(
                section_id="strings-values-and-conversion",
                title="Build text values deliberately",
                objective="Create strings and convert non-text values before combining them.",
                explanation=(
                    "Strings are ordered sequences of characters. Python will not silently join a number to text, "
                    "so explicit conversion makes the intended representation clear."
                ),
                key_points=(
                    "Quotes create string literals.",
                    "str converts a value to its text representation.",
                    "The plus operator joins strings only when both sides are text.",
                ),
                personal_example=f'cv_year = {convert}(2026)\n{output}("CodeVerse " + cv_year)',
                real_python_example='cv_year = str(2026)\nprint("CodeVerse " + cv_year)',
                expected_output="CodeVerse 2026\n",
            ),
            LessonSection(
                section_id="strings-trim-boundaries",
                title="Trim accidental boundary whitespace",
                objective="Remove whitespace at the beginning and end without damaging spacing inside the text.",
                explanation=(
                    "User input and file lines often carry invisible spaces or newline characters. strip cleans the "
                    "outer boundaries while preserving meaningful spaces between words."
                ),
                key_points=(
                    "strip removes leading and trailing whitespace.",
                    "Internal spaces remain unchanged.",
                    "The method returns a new string.",
                ),
                personal_example=f'cv_name = "  Ada Lovelace  ".{strip}()\n{output}(cv_name)',
                real_python_example='cv_name = "  Ada Lovelace  ".strip()\nprint(cv_name)',
                expected_output="Ada Lovelace\n",
            ),
            LessonSection(
                section_id="strings-replace-without-mutation",
                title="Replace text without mutating the original",
                objective="Create a revised string and preserve the source value for comparison.",
                explanation=(
                    "Strings are immutable: methods such as replace do not edit the existing object. They return a "
                    "new value that must be assigned or used directly."
                ),
                key_points=(
                    "replace returns a new string.",
                    "The original variable keeps its previous value.",
                    "Assign the returned string when the change should persist.",
                ),
                personal_example=(
                    f'cv_original = "red,blue"\ncv_clean = cv_original.{replace}(",", "-")\n'
                    f'{output}(cv_original)\n{output}(cv_clean)'
                ),
                real_python_example=(
                    'cv_original = "red,blue"\ncv_clean = cv_original.replace(",", "-")\n'
                    'print(cv_original)\nprint(cv_clean)'
                ),
                expected_output="red,blue\nred-blue\n",
            ),
            LessonSection(
                section_id="strings-normalize-case",
                title="Normalize letter case for comparison",
                objective="Produce consistent uppercase and lowercase representations.",
                explanation=(
                    "Case normalization is useful when values come from people or external systems with inconsistent "
                    "capitalization. The original text remains available."
                ),
                key_points=(
                    "upper creates an uppercase string.",
                    "lower creates a lowercase string.",
                    "Normalization makes later comparisons predictable.",
                ),
                personal_example=f'cv_tag = "PyThOn"\n{output}(cv_tag.{upper}())\n{output}(cv_tag.{lower}())',
                real_python_example='cv_tag = "PyThOn"\nprint(cv_tag.upper())\nprint(cv_tag.lower())',
                expected_output="PYTHON\npython\n",
            ),
            LessonSection(
                section_id="strings-split-structure",
                title="Turn one string into structured pieces",
                objective="Split text into a list that can later be counted, indexed, or looped over.",
                explanation=(
                    "split changes the shape of the data: the result is a list of strings, not another single string. "
                    "Without an argument, consecutive whitespace acts as the separator."
                ),
                key_points=(
                    "split returns a list of strings.",
                    "Whitespace splitting ignores repeated boundary spacing.",
                    "A separator argument can split formats such as comma-separated text.",
                ),
                personal_example=f'cv_words = "learn real python".{split}()\n{output}(cv_words)',
                real_python_example='cv_words = "learn real python".split()\nprint(cv_words)',
                expected_output="['learn', 'real', 'python']\n",
            ),
        )

    if module_id != "signals-and-values":
        return ()

    output = _token(dictionary, "py_fn_print")
    return (
        LessonSection(
            section_id="signals-visible-output",
            title="Make program state visible",
            objective="Use output as evidence of what the program actually did.",
            explanation=(
                "A program normally works invisibly. Python print turns a value into observable output, "
                "which makes it the first debugging and learning tool to reach for."
            ),
            key_points=(
                "Each call writes its arguments and then starts a new line.",
                "Text literals need quotes; numeric literals do not.",
                "The personal token changes the cue, not Python's output behavior.",
            ),
            personal_example=f'{output}("Personal Python ready")',
            real_python_example='print("Personal Python ready")',
            expected_output="Personal Python ready\n",
        ),
        LessonSection(
            section_id="signals-values-and-types",
            title="Distinguish text from numbers",
            objective="Recognize that values which look alike can behave differently.",
            explanation=(
                "The text \"7\" and the integer 7 display similarly, but only the integer participates "
                "in arithmetic. Quotes are therefore part of the program's meaning."
            ),
            key_points=(
                "Quoted digits are strings.",
                "Unquoted digits are numeric values.",
                "Expressions are evaluated before their result is printed.",
            ),
            personal_example=f'{output}("7")\n{output}(7 + 1)',
            real_python_example='print("7")\nprint(7 + 1)',
            expected_output="7\n8\n",
        ),
        LessonSection(
            section_id="signals-named-values",
            title="Observe variables changing",
            objective="Assign a value to a name and inspect the latest value stored there.",
            explanation=(
                "A variable is a name that refers to a value. Reassignment changes what that name refers "
                "to, and output lets you verify the change in order."
            ),
            key_points=(
                "Assignment uses one equals sign.",
                "Reading a variable uses its name without quotes.",
                "Statements run from top to bottom unless control flow changes the order.",
            ),
            personal_example=f'cv_score = 7\n{output}(cv_score)\ncv_score = 9\n{output}(cv_score)',
            real_python_example='cv_score = 7\nprint(cv_score)\ncv_score = 9\nprint(cv_score)',
            expected_output="7\n9\n",
        ),
        LessonSection(
            section_id="signals-debug-labels",
            title="Label debugging output",
            objective="Print context beside a value so output remains understandable.",
            explanation=(
                "Bare numbers quickly become ambiguous. Passing a short label and a value to print creates "
                "readable evidence without changing the value itself."
            ),
            key_points=(
                "A print call can accept multiple comma-separated arguments.",
                "Python inserts a space between those arguments by default.",
                "Useful labels make later debugging faster.",
            ),
            personal_example=f'cv_score = 12\n{output}("score:", cv_score)',
            real_python_example='cv_score = 12\nprint("score:", cv_score)',
            expected_output="score: 12\n",
        ),
    )


def _lesson_steps(module_id: str, concepts: tuple[LearningConcept, ...]) -> tuple[str, ...]:
    names = ", ".join(concept.python_concept for concept in concepts)
    return (
        f"Recognize the personal token(s) for {names}.",
        "Read the Personal Python source before looking at the real output.",
        "Predict the output, then compare it with the compiled Python result.",
        "Name the real Python concept without relying on the personal token.",
    )


def _misconception_checks(module_id: str) -> tuple[str, ...]:
    checks = {
        "choices": (
            "else is not checked first; it only runs after earlier conditions fail.",
            "elif is not a separate if chain; it belongs to the same decision path.",
        ),
        "routes": (
            "range stop values are excluded.",
            "A for loop changes the loop variable automatically on each turn.",
        ),
        "loop-control": (
            "continue does not stop the loop; break stops the loop.",
            "while needs a changing condition or it can run forever.",
        ),
        "tools": (
            "print shows a value; return gives a value back to the caller.",
            "A function definition does not run until the function is called.",
        ),
        "collections": (
            "list positions are ordered; dict values are found by key.",
            "append changes the list; it does not create a visible output by itself.",
        ),
        "tuples-and-sets": (
            "A tuple keeps order but cannot be changed in place; a set is mutable but does not promise display order.",
            "Sets remove duplicate values, so their length can be smaller than the input sequence.",
            "discard is safe when a value is absent; remove would raise KeyError.",
        ),
        "files-and-context": (
            "open returns a file object; it does not read the file by itself.",
            "Mode w replaces existing contents, while mode a appends to them.",
            "with closes the file automatically, including when the block exits because of an error.",
        ),
        "strings-and-text": (
            "String methods return new strings; they do not change the original value in place.",
            "strip removes whitespace at the edges, not spaces between words.",
            "split returns a list of strings, not one modified string.",
        ),
        "numbers-and-conversion": (
            "int truncates a decimal value toward zero; it does not round to the nearest integer.",
            "Converting numeric text changes its type; the original string itself is not modified.",
            "round controls displayed precision but floating-point values can still have representation limits.",
        ),
        "imports-and-library": (
            "importing a module does not run one of its tools automatically.",
            "A module alias changes the local name, not the original package or its API.",
            "from-import selects named members; it does not copy an entire library into the project.",
        ),
        "errors": (
            "try is not for hiding errors; it is for handling risky code deliberately.",
            "finally runs even when no exception happens.",
        ),
        "objects": (
            "class defines the shape; an object is a created instance of that shape.",
            "Methods can read and change object state through self.",
        ),
        "logic": (
            "and needs both sides to be true.",
            "or can pass when only one side is true.",
        ),
    }
    return checks.get(
        module_id,
        ("Output is evidence; always compare your prediction with what the program prints.",),
    )


def _success_criteria(module_id: str) -> tuple[str, ...]:
    if module_id == "signals-and-values":
        return (
            "Distinguish quoted text from numeric values.",
            "Predict output in top-to-bottom execution order.",
            "Use a variable and observe its latest assigned value.",
            "Write and run labeled output with your personal print token.",
            "Score at least 70% across knowledge and code checks.",
        )
    return (
        "Explain each personal token as a real Python concept.",
        "Predict the lesson output before running it.",
        "Solve at least 70% of the module practice tasks.",
    )


def _real_python_preview(module_id: str) -> str:
    previews = {
        "signals-and-values": 'print("Personal Python ready")\ncv_score = 7\nprint(cv_score)\n',
        "strings-and-text": (
            'cv_message = "  codeverse, python  "\n'
            'cv_clean = cv_message.strip().replace(",", "").upper()\n'
            "print(cv_clean)\n"
            "cv_words = cv_clean.lower().split()\n"
            "print(cv_words)\n"
            "print(str(2026))\n"
        ),
        "numbers-and-conversion": (
            'cv_price = float("12.5")\n'
            'cv_count = int("3")\n'
            'print(round(cv_price * cv_count, 1))\n'
            'print(abs(-8))\n'
            'print(pow(2, 3))\n'
        ),
        "imports-and-library": (
            'import math as cv_math\n'
            'print(cv_math.sqrt(81))\n'
            'from statistics import mean as cv_mean\n'
            'print(cv_mean([2, 4, 6]))\n'
        ),
        "choices": (
            "cv_score = 75\n"
            "if cv_score >= 80:\n"
            '    print("mastered")\n'
            "elif cv_score >= 50:\n"
            '    print("keep practicing")\n'
            "else:\n"
            '    print("start small")\n'
        ),
        "routes": 'for cv_step in range(1, 4):\n    print(cv_step)\n',
        "loop-control": (
            "cv_step = 0\n"
            "while cv_step < 5:\n"
            "    cv_step = cv_step + 1\n"
            "    if cv_step == 2:\n"
            "        continue\n"
            "    if cv_step == 4:\n"
            "        break\n"
            "    print(cv_step)\n"
        ),
        "tools": "def cv_reward(cv_base):\n    return cv_base + 50\nprint(cv_reward(100))\n",
        "logic": (
            "cv_ready = True\n"
            "cv_blocked = False\n"
            "cv_value = None\n"
            "if cv_ready and not cv_blocked:\n"
            '    print("go")\n'
            "if cv_value is None or cv_blocked:\n"
            '    print("empty")\n'
        ),
        "collections": (
            "cv_scores = list([100])\n"
            "cv_scores.append(150)\n"
            'cv_profile = dict({"best": 150})\n'
            "print(cv_scores)\n"
            'print(cv_profile.get("best"))\n'
            "print(len(cv_scores))\n"
        ),
        "tuples-and-sets": (
            'cv_route = tuple(["dock", "market"])\n'
            'cv_tags = set(["red", "blue", "red"])\n'
            'cv_tags.add("green")\n'
            'cv_tags.discard("blue")\n'
            'cv_backup = set(["yellow"])\n'
            'cv_all = cv_tags.union(cv_backup)\n'
            'print(cv_route)\n'
            'print(len(cv_all))\n'
            'print("red" in cv_all)\n'
        ),
        "files-and-context": (
            'with open("cv_lesson_note.txt", "w") as cv_file:\n'
            '    cv_file.write("Python files stay safe")\n'
            'with open("cv_lesson_note.txt", "r") as cv_file:\n'
            '    cv_note = cv_file.read()\n'
            '    print(cv_note)\n'
        ),
        "objects": (
            "class CvLearner:\n"
            '    def __init__(self, name="student", points=0):\n'
            "        self.name = name\n"
            "        self.points = points\n"
            "    def add_points(self, amount):\n"
            "        self.points = self.points + amount\n"
            "        return self.points\n"
            'cv_user = CvLearner("Ada", 10)\n'
            "cv_user.add_points(5)\n"
            "print(cv_user.name)\n"
            "print(cv_user.points)\n"
        ),
        "errors": (
            "try:\n"
            '    print("attempt")\n'
            "except Exception:\n"
            '    print("handled")\n'
            "finally:\n"
            '    print("cleanup")\n'
        ),
    }
    return previews[module_id]


def _expected_stdout(module_id: str) -> str:
    outputs = {
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
    }
    return outputs[module_id]


def _prioritized_blueprints(diagnosis: LearnerDiagnosis) -> tuple[dict[str, Any], ...]:
    pain = set(diagnosis.pain_points)
    weight = {
        "choices": 0 if "conditionals" in pain else 2,
        "routes": 0 if "loops" in pain else 3,
        "tools": 0 if "functions" in pain else 4,
        "collections": 1 if "collections" in pain else 5,
        "tuples-and-sets": 2 if "collections" in pain else 6,
        "files-and-context": 2 if "files" in pain else 7,
        "errors": 2 if "errors" in pain else 6,
        "signals-and-values": -1,
        "strings-and-text": 1,
        "numbers-and-conversion": 1 if "numbers" in pain else 2,
        "imports-and-library": 2 if "imports" in pain else 7,
    }
    return tuple(sorted(_MODULE_BLUEPRINTS, key=lambda item: (weight.get(str(item["module_id"]), 9), str(item["module_id"]))))


def _token(dictionary: Any, concept_id: str) -> str:
    mappings = getattr(dictionary, "mappings", {})
    if concept_id in mappings and str(mappings[concept_id]).strip():
        return str(mappings[concept_id]).strip()
    try:
        return str(dictionary.token_for(concept_id)).strip()
    except Exception:  # noqa: BLE001 - accepts both dictionary implementations.
        return _FALLBACK_TOKENS[concept_id]


def _theme_name(dictionary: Any) -> str:
    return str(getattr(dictionary, "theme", "Personal Python") or "Personal Python")


def _matches(text: str, rules: tuple[tuple[str, tuple[str, ...]], ...]) -> tuple[str, ...]:
    found: list[str] = []
    tokens = set(re.findall(r"[a-z0-9çğıöşü]+", text))
    for label, needles in rules:
        if any(_needle_matches(text, tokens, needle) for needle in needles):
            found.append(label)
    return tuple(found)


def _needle_matches(text: str, tokens: set[str], needle: str) -> bool:
    folded = _fold(needle)
    if " " in folded:
        return folded in text
    return folded in tokens


def _level_from_text(text: str) -> str:
    if any(word in text for word in ("advanced", "ileri", "professional", "senior")):
        return "advanced"
    if any(word in text for word in ("intermediate", "orta", "biraz biliyorum")):
        return "intermediate"
    return "beginner"


def _recommended_start(pain_points: tuple[str, ...], level: str) -> str:
    if "conditionals" in pain_points:
        return "choices"
    if "loops" in pain_points:
        return "routes"
    if "functions" in pain_points:
        return "tools"
    if "numbers" in pain_points:
        return "numbers-and-conversion"
    if "imports" in pain_points:
        return "imports-and-library"
    if "files" in pain_points:
        return "files-and-context"
    if level == "advanced":
        return "collections"
    return "signals-and-values"


def _preferred_examples(interests: tuple[str, ...]) -> tuple[str, ...]:
    if "games" in interests:
        return ("scores", "missions", "routes")
    if "sports" in interests:
        return ("scores", "laps", "strategy")
    if "science" in interests:
        return ("measurements", "signals", "experiments")
    return ("small programs", "visible output", "step-by-step changes")


def _evidence(
    prompt: str,
    answers: dict[str, str],
    interests: tuple[str, ...],
    pain_points: tuple[str, ...],
) -> list[str]:
    evidence = [
        f"Detected interests: {', '.join(interests)}.",
        f"Detected learning friction: {', '.join(pain_points)}.",
    ]
    if answers:
        evidence.append(f"Used {len(answers)} clarifying answer(s) to refine the path.")
    if len(prompt) > 120:
        evidence.append("Long-form prompt gives enough context for personalization.")
    return evidence


def _fold(text: str) -> str:
    return text.casefold().replace("ı", "i")


def _normalize_answer(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def _header_value(value: str) -> str:
    compact = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    return compact[:120] or "Personal Python"
