from __future__ import annotations

from codeverse_core.theme_mapping.providers.openai_compatible import (
    OpenAICompatibleProvider,
)


class _Response:
    status_code = 200
    text = "ok"

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "id": "chatcmpl-cv-proof123",
            "model": "codeverse-student",
            "usage": {"prompt_tokens": 25, "completion_tokens": 10},
            "choices": [
                {
                    "message": {"content": '{"clean_theme":"Chess","motifs":["board"]}'},
                    "finish_reason": "stop",
                }
            ]
        }


class _Client:
    def __init__(self, captured: dict) -> None:
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def post(self, url, *, headers, json):
        self._captured.update(url=url, headers=headers, payload=json)
        return _Response()


def test_provider_caps_generation_budget_and_logs_proof(monkeypatch, caplog):
    captured: dict = {}
    monkeypatch.setattr(
        "codeverse_core.theme_mapping.providers.openai_compatible.httpx.Client",
        lambda **_kwargs: _Client(captured),
    )
    provider = OpenAICompatibleProvider(
        base_url="http://student.test/v1",
        api_key="unused",
        model="codeverse-student",
        max_tokens_cap=160,
    )

    with caplog.at_level("INFO"):
        provider.chat(
            [{"role": "user", "content": "Build a profile"}],
            temperature=0.7,
            max_tokens=2048,
        )

    assert captured["payload"]["max_tokens"] == 160
    assert "response_format" not in captured["payload"]
    assert "response_id=chatcmpl-cv-proof123" in caplog.text
    assert "response_model=codeverse-student" in caplog.text
    assert "output_sha256=" in caplog.text
