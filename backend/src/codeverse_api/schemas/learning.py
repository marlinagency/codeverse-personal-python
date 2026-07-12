from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class LearningDiagnoseRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    clarifying_answers: dict[str, str] | None = None


class LearnerDiagnosisOut(BaseModel):
    level: str
    learner_summary: str
    interests: list[str]
    goals: list[str]
    pain_points: list[str]
    preferred_examples: list[str]
    recommended_start: str
    confidence_score: int
    evidence: list[str]


class LearningConceptOut(BaseModel):
    concept_id: str
    python_concept: str
    personal_token: str
    title: str
    mental_model: str
    real_python: str


class PracticeTaskOut(BaseModel):
    """Deliberately omits ``expected_answer``: the student must attempt the
    task first; the check endpoint reveals the answer after the attempt."""

    id: str
    kind: str
    concept_id: str
    prompt: str
    choices: list[str]
    starter_source: str | None = None
    hint: str = ""
    explanation: str = ""
    syntax_mode: str = "personal"


class LessonSectionOut(BaseModel):
    section_id: str
    title: str
    objective: str
    explanation: str
    key_points: list[str]
    personal_example: str
    real_python_example: str
    expected_output: str


class LearningModuleOut(BaseModel):
    module_id: str
    title: str
    goal: str
    why_it_matters: str
    concepts: list[LearningConceptOut]
    bridge_steps: list[str]
    lesson_steps: list[str]
    lesson_sections: list[LessonSectionOut]
    misconception_checks: list[str]
    success_criteria: list[str]
    source_content: str
    real_python_preview: str
    expected_stdout: str
    practice_tasks: list[PracticeTaskOut]
    order: int
    scaffold_stage: str
    personal_support_percent: int
    practice_syntax: str
    generated_code: str | None = None
    stdout: str | None = None
    compile_error: str | None = None


class LearningPathOut(BaseModel):
    theme_dictionary_id: uuid.UUID
    title: str
    diagnosis: LearnerDiagnosisOut
    modules: list[LearningModuleOut]
    proof_points: list[str]


class PracticeCheckRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=80)
    answer: str = Field(min_length=1, max_length=500)


class PracticeRunRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=80)
    source_content: str = Field(min_length=1, max_length=20000)


class PracticeRunOut(BaseModel):
    correct: bool
    status: str  # success | compile_error | runtime_error | timeout | sandbox_error
    stdout: str | None = None
    stderr: str | None = None
    expected_stdout: str
    feedback: str
    compile_error: str | None = None


class PracticeGradeRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


class PracticeEvaluationOut(BaseModel):
    correct: bool
    score: int
    feedback: str
    expected_answer: str
    next_step: str


class ModuleMasteryOut(BaseModel):
    module_id: str
    score: int
    passed: bool
    correct: int
    total: int
    feedback: str


class MasteryReportOut(BaseModel):
    overall_score: int
    passed: bool
    modules: list[ModuleMasteryOut]
    strengths: list[str]
    next_steps: list[str]


class ProgressProofOut(BaseModel):
    theme_dictionary_id: uuid.UUID
    headline: str
    total_modules: int
    total_concepts: int
    runnable_programs: int
    bridge_modes: list[str]
    concept_coverage: dict[str, list[str]]


class BridgeChallengeOut(BaseModel):
    theme_dictionary_id: uuid.UUID
    prompt: str
    personal_reference: str
    expected_stdout: str
    real_keywords: list[str]


class BridgeCheckRequest(BaseModel):
    source_content: str = Field(min_length=1, max_length=20000)


class BridgeCheckOut(BaseModel):
    passed: bool
    status: str  # graduated | wrong_output | used_personal_tokens | runtime_error
    stdout: str | None = None
    stderr: str | None = None
    expected_stdout: str
    used_personal_tokens: list[str]
    feedback: str


class ModuleProgressOut(BaseModel):
    module_id: str
    best_score: int
    passed: bool


class LearningProgressOut(BaseModel):
    theme_dictionary_id: uuid.UUID
    completed_count: int
    modules: list[ModuleProgressOut]


class AssessmentQuestionOut(BaseModel):
    id: str
    concept: str
    prompt: str
    choices: list[str]


class AssessmentSubmitRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


class AssessmentConceptScoreOut(BaseModel):
    concept: str
    correct: int
    total: int
    score: int


class AssessmentResultOut(BaseModel):
    phase: str
    score: int
    correct: int
    total: int
    concept_scores: list[AssessmentConceptScoreOut]
    feedback: list[str]
    baseline_locked: bool


class LearningEvidenceOut(BaseModel):
    theme_dictionary_id: uuid.UUID
    questions: list[AssessmentQuestionOut]
    pre_score: int | None
    post_score: int | None
    gain: int | None
    concept_gain: dict[str, int]
    readiness: str
