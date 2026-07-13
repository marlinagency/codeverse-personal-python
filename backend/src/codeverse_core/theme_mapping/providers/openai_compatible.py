"""Generic OpenAI-compatible chat-completions provider.

Backs any endpoint speaking the OpenAI chat API: OpenAI itself, Fireworks AI,
vLLM, LM Studio, ... Configure with base_url + api_key + model.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time

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

logger = logging.getLogger("uvicorn.error")


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
        provider_label: str = "openai_compatible",
        max_tokens_cap: int | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._label = provider_label
        self._max_tokens_cap = max_tokens_cap

    @property
    def provider_name(self) -> str:
        return self._label

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
            mappings={k: v for k, v in mappings.items()},  # keyed by concept key (str)
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
        """Raw chat-completion call, public so higher-scale callers (e.g. the
        taxonomy batch generator, Adım 8) aren't limited to the two fixed
        capabilities on :class:`LLMProvider`."""
        started_at = time.perf_counter()
        try:
            with httpx.Client(timeout=self._timeout) as client:
                effective_max_tokens = (
                    min(max_tokens, self._max_tokens_cap)
                    if self._max_tokens_cap is not None
                    else max_tokens
                )
                payload = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": effective_max_tokens,
                }
                if effective_max_tokens > 1000:
                    payload["response_format"] = {"type": "json_object"}
                resp = self._post_chat(client, payload)
                if resp.status_code == 400 and "response_format" in resp.text:
                    payload.pop("response_format", None)
                    resp = self._post_chat(client, payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"{self._label} request failed: {exc}") from exc
        content = self._extract_content(data)
        elapsed_ms = round((time.perf_counter() - started_at) * 1000)
        response_id = str(data.get("id", "unknown")) if isinstance(data, dict) else "unknown"
        response_model = (
            str(data.get("model", "unknown")) if isinstance(data, dict) else "unknown"
        )
        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        logger.info(
            "LLM_INFERENCE_PROOF provider=%s requested_model=%s response_model=%s "
            "response_id=%s latency_ms=%d prompt_tokens=%s completion_tokens=%s "
            "output_sha256=%s",
            self._label,
            self._model,
            response_model,
            response_id,
            elapsed_ms,
            usage.get("prompt_tokens", "unknown") if isinstance(usage, dict) else "unknown",
            usage.get("completion_tokens", "unknown") if isinstance(usage, dict) else "unknown",
            hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
        )
        return content

    def _post_chat(
        self, client: httpx.Client, payload: dict[str, object]
    ) -> httpx.Response:
        return client.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    def _extract_content(self, data: object) -> str:
        try:
            choice = data["choices"][0]  # type: ignore[index]
            message = choice.get("message", {})
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
            text = choice.get("text")
            if isinstance(text, str) and text.strip():
                return text
            finish_reason = choice.get("finish_reason", "unknown")
            message_keys = ", ".join(sorted(message.keys())) if isinstance(message, dict) else ""
            raise LLMProviderError(
                f"{self._label} returned no message content "
                f"(finish_reason={finish_reason}, message_keys=[{message_keys}])"
            )
        except LLMProviderError:
            raise
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LLMProviderError(
                f"{self._label} returned unexpected response shape"
            ) from exc
