"""Deterministic real-Python assessments for measurable learning evidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssessmentQuestion:
    id: str
    concept: str
    prompt: str
    choices: tuple[str, ...]
    correct_answer: str
    explanation: str


@dataclass(frozen=True)
class ConceptScore:
    concept: str
    correct: int
    total: int
    score: int


@dataclass(frozen=True)
class AssessmentResult:
    score: int
    correct: int
    total: int
    concept_scores: tuple[ConceptScore, ...]
    feedback: tuple[str, ...]


_QUESTIONS = (
    AssessmentQuestion(
        "values-output",
        "values",
        'What does this print?\n\nx = 4\nx = x + 3\nprint(x)',
        ("3", "4", "7", "x + 3"),
        "7",
        "Assignment updates x before print reads its current value.",
    ),
    AssessmentQuestion(
        "conditions-branch",
        "conditions",
        'What does this print?\n\nscore = 8\nif score >= 10:\n    print("A")\nelif score >= 5:\n    print("B")\nelse:\n    print("C")',
        ("A", "B", "C", "A and B"),
        "B",
        "Python runs the first true branch and skips the remaining branches.",
    ),
    AssessmentQuestion(
        "loops-range",
        "loops",
        "Which values are printed?\n\nfor i in range(1, 4):\n    print(i)",
        ("0, 1, 2, 3", "1, 2, 3", "1, 2, 3, 4", "4 only"),
        "1, 2, 3",
        "range includes its start and excludes its stop value.",
    ),
    AssessmentQuestion(
        "functions-return",
        "functions",
        "What is stored in result?\n\ndef double(value):\n    return value * 2\n\nresult = double(6)",
        ("6", "8", "12", "None"),
        "12",
        "return sends the calculated value back to the caller.",
    ),
    AssessmentQuestion(
        "collections-list",
        "collections",
        "What does len(items) return?\n\nitems = [2, 4]\nitems.append(6)",
        ("2", "3", "6", "[2, 4, 6]"),
        "3",
        "append adds one item, so the list contains three elements.",
    ),
    AssessmentQuestion(
        "errors-finally",
        "errors",
        "Which block runs whether or not an exception occurs?",
        ("try", "except", "finally", "raise"),
        "finally",
        "finally is reserved for cleanup that must run in both success and failure paths.",
    ),
    AssessmentQuestion(
        "files-context",
        "files",
        'Why is with open("notes.txt") as file: useful?',
        (
            "It automatically closes the file",
            "It converts the file to a list",
            "It prevents all file errors",
            "It makes the file read-only",
        ),
        "It automatically closes the file",
        "The context manager closes the file when the with block ends.",
    ),
    AssessmentQuestion(
        "objects-instance",
        "objects",
        "What does self refer to inside an instance method?",
        ("The class name", "The current object", "Every object", "The parent class"),
        "The current object",
        "self is the instance receiving the method call.",
    ),
)


def assessment_questions() -> tuple[AssessmentQuestion, ...]:
    return _QUESTIONS


def grade_assessment(answers: dict[str, str]) -> AssessmentResult:
    concept_scores: list[ConceptScore] = []
    feedback: list[str] = []
    correct_count = 0

    for question in _QUESTIONS:
        answer = answers.get(question.id, "").strip()
        correct = answer == question.correct_answer
        correct_count += int(correct)
        concept_scores.append(
            ConceptScore(
                concept=question.concept,
                correct=int(correct),
                total=1,
                score=100 if correct else 0,
            )
        )
        feedback.append(
            f"{question.concept}: "
            + ("Correct. " if correct else f"Review this. The answer is {question.correct_answer}. ")
            + question.explanation
        )

    total = len(_QUESTIONS)
    return AssessmentResult(
        score=round(correct_count / total * 100),
        correct=correct_count,
        total=total,
        concept_scores=tuple(concept_scores),
        feedback=tuple(feedback),
    )
