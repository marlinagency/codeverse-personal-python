"""Anthropic Messages API provider."""

from __future__ import annotations

import json

import httpx

from codeverse_core.concepts import UniversalConcept
from codeverse_core.theme_mapping import prompt_templates
from codeverse_core.theme_mapping.llm_provider import (
    LLMProvider,
    LLMProviderError,
    ThemeMappingRequest,
    ThemeMappingResponse,
    error_mapping_json,
)

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-5",
        timeout_seconds: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        return self._model

    def generate_theme_mapping(self, request: ThemeMappingRequest) -> ThemeMappingResponse:
        messages = prompt_templates.build_messages(request)
        raw = self.chat(messages, temperature=0.8, max_tokens=2048)
        try:
            mappings, rationale = prompt_templates.parse_mapping_output(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMProviderError(f"unparseable model output: {exc}") from exc
        return ThemeMappingResponse(
            mappings=mappings,
            rationale=rationale,
            raw_model_output=raw,
            model=self._model,
        )

    def translate_error_message(
        self,
        canonical_message: str,
        theme: str,
        mappings: dict[UniversalConcept | str, str],
    ) -> str:
        messages = prompt_templates.build_error_translation_messages(
            canonical_message, theme, error_mapping_json(mappings)
        )
        return self.chat(messages, temperature=0.3, max_tokens=300).strip()

    def chat(
        self, messages: list[dict[str, str]], *, temperature: float, max_tokens: int
    ) -> str:
        """Raw message-completion call, public so higher-scale callers (e.g.
        the taxonomy batch generator, Adım 8) aren't limited to the two fixed
        capabilities on :class:`LLMProvider`."""
        # Anthropic separates the system prompt from the message list.
        system = ""
        chat_messages: list[dict[str, str]] = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                chat_messages.append(m)
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    _API_URL,
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": _API_VERSION,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "system": system,
                        "messages": chat_messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"anthropic request failed: {exc}") from exc
        try:
            return "".join(
                block["text"] for block in data["content"] if block.get("type") == "text"
            )
        except (KeyError, TypeError) as exc:
            raise LLMProviderError("anthropic returned unexpected shape") from exc
