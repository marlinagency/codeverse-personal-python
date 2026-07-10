from __future__ import annotations

import json

import pytest

from codeverse_core.theme_mapping.clarifying_questions import (
    build_clarifying_questions_messages,
    generate_clarifying_questions,
    parse_clarifying_questions_output,
)
from codeverse_core.theme_mapping.taxonomy_generator import TaxonomyGenerationError


class _StubProvider:
    """Chat-capable stub: returns queued raw responses in order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    @property
    def provider_name(self) -> str:
        return "stub"

    def chat(self, messages, *, temperature, max_tokens) -> str:
        self.calls.append(messages)
        return self._responses.pop(0)


def _valid_questions_json(count: int = 7) -> str:
    return json.dumps(
        {
            "questions": [
                {
                    "id": f"q{i}",
                    "question": f"Question {i}?",
                    "options": [
                        {"label": "Option A", "icon": "🎯"},
                        {"label": "Option B", "icon": "✨"},
                    ],
                }
                for i in range(1, count + 1)
            ]
        }
    )


def test_build_clarifying_questions_messages_shape():
    msgs = build_clarifying_questions_messages("I love beekeeping")
    assert msgs[0]["role"] == "system"
    assert "multiple-choice clarifying wizard" in msgs[0]["content"]
    assert msgs[-1]["content"] == "Theme: I love beekeeping"


def test_parse_clarifying_questions_output_happy_path():
    questions = parse_clarifying_questions_output(_valid_questions_json())
    assert len(questions) == 7
    assert questions[0].question == "Question 1?"
    assert questions[0].options[0].label == "Option A"
    assert questions[0].options[0].icon == "🎯"


def test_parse_clarifying_questions_output_tolerates_5_to_8_count():
    assert len(parse_clarifying_questions_output(_valid_questions_json(5))) == 5
    assert len(parse_clarifying_questions_output(_valid_questions_json(8))) == 8


def test_parse_clarifying_questions_output_rejects_too_few():
    with pytest.raises(ValueError, match="5-8"):
        parse_clarifying_questions_output(_valid_questions_json(3))


def test_parse_clarifying_questions_output_rejects_missing_questions_key():
    with pytest.raises(ValueError, match="5-8"):
        parse_clarifying_questions_output('{"foo": "bar"}')


def test_parse_clarifying_questions_output_rejects_option_without_label():
    raw = json.dumps(
        {
            "questions": [
                {"id": "q1", "question": "X?", "options": [{"icon": "🎯"}]}
                for _ in range(7)
            ]
        }
    )
    with pytest.raises(ValueError):
        parse_clarifying_questions_output(raw)


def test_generate_clarifying_questions_success_first_try():
    provider = _StubProvider([_valid_questions_json()])
    questions = generate_clarifying_questions(provider, "witcher")
    assert len(questions) == 7
    assert len(provider.calls) == 1


def test_generate_clarifying_questions_retries_on_bad_json_then_succeeds():
    provider = _StubProvider(["not json at all", _valid_questions_json()])
    questions = generate_clarifying_questions(provider, "witcher", max_attempts=3)
    assert len(questions) == 7
    assert len(provider.calls) == 2


def test_generate_clarifying_questions_raises_after_max_attempts():
    provider = _StubProvider(["junk", "junk", "junk"])
    with pytest.raises(TaxonomyGenerationError, match="netleştirme soruları"):
        generate_clarifying_questions(provider, "witcher", max_attempts=3)
    assert len(provider.calls) == 3
