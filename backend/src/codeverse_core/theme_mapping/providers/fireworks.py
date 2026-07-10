"""Fireworks AI provider — the product spec's primary LLM target.

Fireworks exposes an OpenAI-compatible chat API, so this is a thin,
pre-configured specialization of OpenAICompatibleProvider kept as its own
class for clarity and config separation.

Model choice (Taksonomi Planı Adım 8): the plan's intended production model
is Gemma 4 (``accounts/fireworks/models/gemma-4-31b-it``). Verified live
against this account on 2026-07-03 — Gemma 4 has NO serverless tier on
Fireworks; it requires an on-demand GPU deployment (~$40/hr) and returns
404 "Model not found, inaccessible, and/or not deployed" otherwise. Re-check
before switching: ``GET /v1/models`` lists every model actually enabled on
the account without cost.

Until Gemma 4 is deployed, ``glm-5p2`` is the working default — serverless
(no deployment step, pay-per-token) and, in a live head-to-head against
``gpt-oss-120b`` on the real theme-profile + clarifying-questions tasks,
equal quality (both 4/4 valid JSON, full family fill) but ~33% faster
(7-8s vs ~11s/call). ``gpt-oss-120b`` remains a proven fallback. Swap
``DEFAULT_MODEL`` (or set ``CODEVERSE_FIREWORKS_MODEL``); all candidates are
OpenAI-compatible chat models so no code changes are needed.
"""

from __future__ import annotations

from codeverse_core.theme_mapping.providers.openai_compatible import (
    OpenAICompatibleProvider,
)

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"

#: intended production model per the product spec — currently undeployed
#: (no serverless tier); kept as a named constant so the substitution is
#: easy to find and reverse.
INTENDED_PRODUCTION_MODEL = "accounts/fireworks/models/gemma-4-31b-it"

#: working default — serverless, no deployment cost. Chosen over gpt-oss-120b
#: after a live head-to-head on the real theme-profile + clarifying-questions
#: tasks: identical quality (both 4/4 valid JSON, full family fill, relevant
#: motifs) but glm-5p2 is ~33% faster (7-8s vs ~11s per call), a real UX win
#: on the user-facing generation step. Reverse by swapping this constant back.
DEFAULT_MODEL = "accounts/fireworks/models/glm-5p2"


class FireworksProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 60.0,
    ) -> None:
        super().__init__(
            base_url=FIREWORKS_BASE_URL,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            provider_label="fireworks",
        )
