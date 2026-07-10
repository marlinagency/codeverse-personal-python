from __future__ import annotations

import contextlib
import io
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from codeverse_api.dependencies import get_compilation_pipeline, get_db, get_sandbox_runner
from codeverse_api.repositories.progress_repository import ProgressRepository
from codeverse_api.repositories.theme_repository import ThemeRepository
from codeverse_api.routers.execute import run_local_python_demo
from codeverse_api.schemas.learning import (
    BridgeChallengeOut,
    BridgeCheckOut,
    BridgeCheckRequest,
    LearnerDiagnosisOut,
    LearningConceptOut,
    LearningDiagnoseRequest,
    LearningModuleOut,
    LearningPathOut,
    LearningProgressOut,
    MasteryReportOut,
    ModuleMasteryOut,
    ModuleProgressOut,
    PracticeCheckRequest,
    PracticeEvaluationOut,
    PracticeGradeRequest,
    PracticeRunOut,
    PracticeRunRequest,
    PracticeTaskOut,
    ProgressProofOut,
)
from codeverse_api.security.auth import get_current_user_id
from codeverse_core.cvl.pipeline import CompilationError, CompilationPipeline
from codeverse_core.personal_python import (
    LearnerDiagnosis,
    LearningConcept,
    LearningModule,
    LearningPath,
    PracticeTask,
    bridge_expected_stdout,
    build_bridge_challenge,
    build_learning_module,
    build_learning_path,
    build_progress_proof,
    code_task_expected_stdout,
    code_task_module_id,
    diagnose_learning_prompt,
    evaluate_practice_answer,
    grade_practice_answers,
)
from codeverse_sandbox.docker_runner import DockerSandboxError, DockerSandboxRunner
from codeverse_sandbox.limits import SandboxLimits

router = APIRouter(prefix="/learning", tags=["learning"])


@router.post("/diagnose", response_model=LearnerDiagnosisOut)
def diagnose_learner(
    body: LearningDiagnoseRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> LearnerDiagnosisOut:
    _ = user_id
    return _diagnosis_out(diagnose_learning_prompt(body.prompt, body.clarifying_answers))


@router.get("/{theme_dictionary_id}/path", response_model=LearningPathOut)
def get_learning_path(
    theme_dictionary_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> LearningPathOut:
    dictionary = _load_dictionary(db, user_id, theme_dictionary_id)
    path = build_learning_path(dictionary)
    return _path_out(theme_dictionary_id, path)


@router.get("/{theme_dictionary_id}/lessons/{module_id}", response_model=LearningModuleOut)
def get_learning_lesson(
    theme_dictionary_id: uuid.UUID,
    module_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    pipeline: CompilationPipeline = Depends(get_compilation_pipeline),
) -> LearningModuleOut:
    dictionary = _load_dictionary(db, user_id, theme_dictionary_id)
    try:
        module = build_learning_module(dictionary, module_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="learning module not found") from exc
    return _module_out(module, pipeline=pipeline, dictionary=dictionary, include_runtime=True)


@router.post("/{theme_dictionary_id}/practice/check", response_model=PracticeEvaluationOut)
def check_practice_answer(
    theme_dictionary_id: uuid.UUID,
    body: PracticeCheckRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> PracticeEvaluationOut:
    _load_dictionary(db, user_id, theme_dictionary_id)
    result = evaluate_practice_answer(body.task_id, body.answer)
    return PracticeEvaluationOut(
        correct=result.correct,
        score=result.score,
        feedback=result.feedback,
        expected_answer=result.expected_answer,
        next_step=result.next_step,
    )


@router.post("/{theme_dictionary_id}/practice/run", response_model=PracticeRunOut)
def run_practice_code(
    theme_dictionary_id: uuid.UUID,
    body: PracticeRunRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    pipeline: CompilationPipeline = Depends(get_compilation_pipeline),
    sandbox: DockerSandboxRunner | None = Depends(get_sandbox_runner),
) -> PracticeRunOut:
    """Behavioral check for write_code exercises: compile the student's
    Personal Python source with THEIR dictionary, actually run it, and
    compare stdout against the task's goal output."""
    dictionary = _load_dictionary(db, user_id, theme_dictionary_id)
    expected = code_task_expected_stdout(body.task_id)
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown code practice task"
        )

    try:
        compiled = pipeline.compile(body.source_content, dictionary)
    except CompilationError as exc:
        first = exc.diagnostics[0]
        message = first.themed_message or first.message
        return PracticeRunOut(
            correct=False,
            status="compile_error",
            expected_stdout=expected,
            feedback=f"Your code didn't compile yet: {message}",
            compile_error=f"line {first.line}: {first.message}",
        )

    limits = SandboxLimits()
    run: dict[str, object]
    if sandbox is not None:
        try:
            result = sandbox.run(
                language="python",
                source_code=compiled.codegen.source_code,
                limits=limits,
            )
            run = {"status": result.status, "stdout": result.stdout, "stderr_raw": result.stderr or None}
        except DockerSandboxError:
            run = run_local_python_demo("python", compiled.codegen.source_code, limits)
    else:
        run = run_local_python_demo("python", compiled.codegen.source_code, limits)

    stdout = str(run.get("stdout") or "")
    if run.get("status") != "success":
        return PracticeRunOut(
            correct=False,
            status=str(run.get("status") or "runtime_error"),
            stdout=stdout or None,
            stderr=str(run.get("stderr_raw") or "") or None,
            expected_stdout=expected,
            feedback="Your code compiled but crashed while running. Read the error, fix it, and run again.",
        )

    correct = _normalize_stdout(stdout) == _normalize_stdout(expected)
    if correct:
        module_id = code_task_module_id(body.task_id)
        if module_id is not None:
            # A working code exercise proves mastery of the module — record it.
            ProgressRepository(db).record_score(user_id, theme_dictionary_id, module_id, 100)
            db.commit()

    return PracticeRunOut(
        correct=correct,
        status="success",
        stdout=stdout,
        expected_stdout=expected,
        feedback=(
            "Exactly right — your program prints the goal output."
            if correct
            else "It runs, but the output doesn't match the goal yet. Compare the two outputs line by line."
        ),
    )


def _normalize_stdout(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


@router.post("/{theme_dictionary_id}/practice/grade", response_model=MasteryReportOut)
def grade_practice_session(
    theme_dictionary_id: uuid.UUID,
    body: PracticeGradeRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> MasteryReportOut:
    _load_dictionary(db, user_id, theme_dictionary_id)
    report = grade_practice_answers(body.answers)

    progress = ProgressRepository(db)
    for module in report.modules:
        if module.module_id != "unknown":
            progress.record_score(user_id, theme_dictionary_id, module.module_id, module.score)
    db.commit()

    return MasteryReportOut(
        overall_score=report.overall_score,
        passed=report.passed,
        modules=[
            ModuleMasteryOut(
                module_id=module.module_id,
                score=module.score,
                passed=module.passed,
                correct=module.correct,
                total=module.total,
                feedback=module.feedback,
            )
            for module in report.modules
        ],
        strengths=list(report.strengths),
        next_steps=list(report.next_steps),
    )


@router.get("/{theme_dictionary_id}/progress", response_model=LearningProgressOut)
def get_learning_progress(
    theme_dictionary_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> LearningProgressOut:
    _load_dictionary(db, user_id, theme_dictionary_id)
    rows = ProgressRepository(db).list_for_theme(user_id, theme_dictionary_id)
    return LearningProgressOut(
        theme_dictionary_id=theme_dictionary_id,
        completed_count=sum(1 for row in rows if row.passed),
        modules=[
            ModuleProgressOut(module_id=row.module_id, best_score=row.best_score, passed=row.passed)
            for row in rows
        ],
    )


@router.get("/{theme_dictionary_id}/bridge", response_model=BridgeChallengeOut)
def get_bridge_challenge(
    theme_dictionary_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> BridgeChallengeOut:
    """The graduation capstone: rewrite a personal-syntax program in real
    Python. The solution is never sent — only the personal reference to
    translate FROM, the goal output, and the real keywords to use."""
    dictionary = _load_dictionary(db, user_id, theme_dictionary_id)
    challenge = build_bridge_challenge(dictionary)
    return BridgeChallengeOut(
        theme_dictionary_id=theme_dictionary_id,
        prompt=challenge.prompt,
        personal_reference=challenge.personal_reference,
        expected_stdout=challenge.expected_stdout,
        real_keywords=list(challenge.real_keywords),
    )


@router.post("/{theme_dictionary_id}/bridge/check", response_model=BridgeCheckOut)
def check_bridge_submission(
    theme_dictionary_id: uuid.UUID,
    body: BridgeCheckRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    sandbox: DockerSandboxRunner | None = Depends(get_sandbox_runner),
) -> BridgeCheckOut:
    """Graduation check: the submission must run as PLAIN Python (not compiled
    through the theme dictionary), print the goal output, and contain none of
    the learner's personal tokens — proving they truly rewrote it in real
    Python rather than pasting the personal version."""
    dictionary = _load_dictionary(db, user_id, theme_dictionary_id)
    challenge = build_bridge_challenge(dictionary)
    expected = bridge_expected_stdout()
    source = body.source_content

    # Anti-cheat first: a clear "you still used your personal tokens" message
    # beats a raw SyntaxError (personal tokens aren't valid Python anyway).
    used = [
        token
        for token in challenge.forbidden_tokens
        if re.search(rf"\b{re.escape(token)}\b", source)
    ]
    if used:
        return BridgeCheckOut(
            passed=False,
            status="used_personal_tokens",
            expected_stdout=expected,
            used_personal_tokens=used,
            feedback=(
                "This still uses your personal tokens ("
                + ", ".join(sorted(set(used))[:4])
                + "). Rewrite it with real Python keywords: "
                + ", ".join(challenge.real_keywords)
                + "."
            ),
        )

    limits = SandboxLimits()
    if sandbox is not None:
        try:
            result = sandbox.run(language="python", source_code=source, limits=limits)
            run = {"status": result.status, "stdout": result.stdout, "stderr_raw": result.stderr or None}
        except DockerSandboxError:
            run = run_local_python_demo("python", source, limits)
    else:
        run = run_local_python_demo("python", source, limits)

    stdout = str(run.get("stdout") or "")
    if run.get("status") != "success":
        return BridgeCheckOut(
            passed=False,
            status="runtime_error",
            stdout=stdout or None,
            stderr=str(run.get("stderr_raw") or "") or None,
            expected_stdout=expected,
            used_personal_tokens=[],
            feedback="Your real Python didn't run cleanly yet. Read the error, fix the syntax, and try again.",
        )

    if _normalize_stdout(stdout) != _normalize_stdout(expected):
        return BridgeCheckOut(
            passed=False,
            status="wrong_output",
            stdout=stdout,
            expected_stdout=expected,
            used_personal_tokens=[],
            feedback="It runs as real Python, but the output doesn't match the goal yet. Compare them line by line.",
        )

    # Graduated: record it as a special progress milestone.
    ProgressRepository(db).record_score(user_id, theme_dictionary_id, "graduation", 100)
    db.commit()
    return BridgeCheckOut(
        passed=True,
        status="graduated",
        stdout=stdout,
        expected_stdout=expected,
        used_personal_tokens=[],
        feedback="Graduated! You just wrote real, standard Python without the personal layer — the scaffold worked.",
    )


@router.get("/{theme_dictionary_id}/proof", response_model=ProgressProofOut)
def get_progress_proof(
    theme_dictionary_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProgressProofOut:
    dictionary = _load_dictionary(db, user_id, theme_dictionary_id)
    proof = build_progress_proof(dictionary)
    return ProgressProofOut(
        theme_dictionary_id=theme_dictionary_id,
        headline=proof.headline,
        total_modules=proof.total_modules,
        total_concepts=proof.total_concepts,
        runnable_programs=proof.runnable_programs,
        bridge_modes=list(proof.bridge_modes),
        concept_coverage=proof.concept_coverage,
    )


def _load_dictionary(db: Session, user_id: uuid.UUID, theme_dictionary_id: uuid.UUID):
    row = ThemeRepository(db).get(theme_dictionary_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="theme dictionary not found")
    return ThemeRepository.to_domain(row)


def _path_out(theme_dictionary_id: uuid.UUID, path: LearningPath) -> LearningPathOut:
    return LearningPathOut(
        theme_dictionary_id=theme_dictionary_id,
        title=path.title,
        diagnosis=_diagnosis_out(path.diagnosis),
        modules=[_module_out(module) for module in path.modules],
        proof_points=list(path.proof_points),
    )


def _diagnosis_out(diagnosis: LearnerDiagnosis) -> LearnerDiagnosisOut:
    return LearnerDiagnosisOut(
        level=diagnosis.level,
        learner_summary=diagnosis.learner_summary,
        interests=list(diagnosis.interests),
        goals=list(diagnosis.goals),
        pain_points=list(diagnosis.pain_points),
        preferred_examples=list(diagnosis.preferred_examples),
        recommended_start=diagnosis.recommended_start,
        confidence_score=diagnosis.confidence_score,
        evidence=list(diagnosis.evidence),
    )


def _module_out(
    module: LearningModule,
    *,
    pipeline: CompilationPipeline | None = None,
    dictionary=None,
    include_runtime: bool = False,
) -> LearningModuleOut:
    generated_code: str | None = None
    stdout: str | None = None
    compile_error: str | None = None
    if include_runtime and pipeline is not None and dictionary is not None:
        try:
            compiled = pipeline.compile(module.source_content, dictionary)
            generated_code = compiled.codegen.source_code
            stdout = _run_python(generated_code)
        except CompilationError as exc:
            first = exc.diagnostics[0]
            compile_error = f"{first.stage}:{first.line}:{first.col} {first.message}"

    return LearningModuleOut(
        module_id=module.module_id,
        title=module.title,
        goal=module.goal,
        why_it_matters=module.why_it_matters,
        concepts=[_concept_out(concept) for concept in module.concepts],
        bridge_steps=list(module.bridge_steps),
        lesson_steps=list(module.lesson_steps),
        misconception_checks=list(module.misconception_checks),
        success_criteria=list(module.success_criteria),
        source_content=module.source_content,
        real_python_preview=module.real_python_preview,
        expected_stdout=module.expected_stdout,
        practice_tasks=[_task_out(task) for task in module.practice_tasks],
        order=module.order,
        generated_code=generated_code,
        stdout=stdout,
        compile_error=compile_error,
    )


def _concept_out(concept: LearningConcept) -> LearningConceptOut:
    return LearningConceptOut(
        concept_id=concept.concept_id,
        python_concept=concept.python_concept,
        personal_token=concept.personal_token,
        title=concept.title,
        mental_model=concept.mental_model,
        real_python=concept.real_python,
    )


def _task_out(task: PracticeTask) -> PracticeTaskOut:
    return PracticeTaskOut(
        id=task.id,
        kind=task.kind,
        concept_id=task.concept_id,
        prompt=task.prompt,
        choices=list(task.choices),
        starter_source=task.starter_source,
        hint=task.hint,
        explanation=task.explanation,
    )


def _run_python(source_code: str) -> str:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exec(source_code, {})  # noqa: S102 - deterministic lesson code generated by backend.
    return stdout.getvalue()
