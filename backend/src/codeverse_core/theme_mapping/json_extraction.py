"""Lenient JSON extraction from raw LLM chat output.

Shared by every module that parses a JSON object out of a model's free-form
response (theme profiles, category batches, clarifying questions, ...):
strips markdown code fences, tolerates leading prose before the opening
brace, and recovers from a truncated/trailing-garbage tail by scanning for
the last plausible closing brace.
"""

from __future__ import annotations

import json


def extract_json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        first_nl = text.index("\n")
        text = text[first_nl + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start = text.find("{")
    if start == -1:
        raise ValueError("model output has no JSON object")
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        end = text.rfind("}")
        if end <= start:
            raise ValueError("model output has no JSON object") from None
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("model output has no JSON object")
    return data
