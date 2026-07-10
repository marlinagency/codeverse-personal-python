"""Prompt construction for theme-mapping generation.

Design notes:

* The theme input is FREE TEXT of any length. The prompt explicitly
  instructs the model to first distill the theme into key motifs, then
  derive one token per concept from those motifs — so "Valorant" and
  "someone who loves and knows black holes in space" both work.
* Few-shot examples cover both a one-word theme and a sentence-length
  theme, in two output languages, to anchor the output format.
* Output tokens must be single identifiers; the DSL constraint is stated
  in the prompt AND enforced afterwards by the validator (belt and braces —
  on validation failure the generator retries with corrective feedback).
"""

from __future__ import annotations

import json

from codeverse_core.concepts import UniversalConcept
from codeverse_core.theme_mapping.llm_provider import ThemeMappingRequest

_CONCEPT_DESCRIPTIONS: dict[UniversalConcept, str] = {
    UniversalConcept.FUNCTION_DEF: "defines a reusable function/ability",
    UniversalConcept.RETURN: "returns a value from a function",
    UniversalConcept.IF: "conditional: do something only when a condition holds",
    UniversalConcept.ELIF: "otherwise-if: next conditional branch",
    UniversalConcept.ELSE: "fallback branch when no condition matched",
    UniversalConcept.FOR: "iterate over each element of a collection",
    UniversalConcept.IN: "connects the loop variable to the collection ('for x IN xs')",
    UniversalConcept.WHILE: "repeat as long as a condition holds",
    UniversalConcept.BREAK: "exit the current loop immediately",
    UniversalConcept.CONTINUE: "skip to the next loop iteration",
    UniversalConcept.CLASS_DEF: "defines a class / blueprint for objects",
    UniversalConcept.IMPORT: "bring in an external module/library",
    UniversalConcept.TRY: "start a protected block that may fail",
    UniversalConcept.EXCEPT: "handle an error raised in the protected block",
    UniversalConcept.FINALLY: "cleanup block that always runs",
    UniversalConcept.AND: "logical AND",
    UniversalConcept.OR: "logical OR",
    UniversalConcept.NOT: "logical NOT",
    UniversalConcept.TRUE: "boolean true literal",
    UniversalConcept.FALSE: "boolean false literal",
    UniversalConcept.NONE: "null / no-value literal",
    UniversalConcept.PRINT: "print/output a value",
    UniversalConcept.RANGE: "produce a sequence of numbers 0..n-1",
    UniversalConcept.LEN: "length/size of a collection",
    UniversalConcept.LIST_APPEND: "add an element to the end of a list",
    UniversalConcept.LIST_REMOVE: "remove an element from a list",
    UniversalConcept.CONTAINS: "check whether a collection contains a value/key",
    UniversalConcept.DICT_GET: "read a value from a map by key",
    UniversalConcept.DICT_SET: "write a value into a map under a key",
    UniversalConcept.DICT_KEYS: "all keys of a map",
    UniversalConcept.DICT_VALUES: "all values of a map",
    UniversalConcept.DICT_DELETE: "delete a key from a map",
}

SYSTEM_PROMPT = """\
You are CodeVerse's theme-vocabulary designer. You receive a user's theme —
which may be a single word ("Valorant") or a whole sentence describing an
interest ("someone who loves and deeply knows black holes in space") — and a
list of universal programming concepts.

Work in two steps:
1. Distill the theme into its 5-8 most evocative motifs (objects, actions,
   places, jargon of that world).
2. Map EVERY concept to exactly one token derived from those motifs.

Hard rules for every token:
- A single identifier: letters (any language), digits, underscores; must not
  start with a digit; NO spaces, NO punctuation. Multi-word ideas use
  snake_case (e.g. "olay_ufku").
- All tokens must be mutually distinct (case-insensitively).
- Never reuse real programming keywords (if, def, class, for, while, return,
  try, select, import, ...).
- Tokens must be semantically intuitive: a person who loves this theme should
  guess the meaning. Related concepts should feel related (if/elif/else should
  read as a family).
- Match the requested output language if one is given; otherwise use the
  language the theme itself is written in.

Respond with ONLY a JSON object, no prose, of the shape:
{"mappings": {"<concept_key>": "<token>", ...},
 "rationale": {"<concept_key>": "<one short line why>", ...}}
The "rationale" values must be brief. Include every concept key exactly once.
"""

_FEW_SHOT_USER = """\
Theme: Valorant
Output language: tr
Concepts:
- function_def: defines a reusable function/ability
- if: conditional: do something only when a condition holds
- return: returns a value from a function
"""

_FEW_SHOT_ASSISTANT = json.dumps(
    {
        "mappings": {
            "function_def": "yetenek",
            "if": "tetiklendiğinde",
            "return": "geri_gönder",
        },
        "rationale": {
            "function_def": "Ajanların yetenekleri = çağrılabilir beceriler",
            "if": "Yetenekler bir koşul tetiklendiğinde devreye girer",
            "return": "Sonucu takıma geri bildirmek",
        },
    },
    ensure_ascii=False,
)

_FEW_SHOT_USER_2 = """\
Theme: someone who loves and deeply knows black holes in space
Output language: en
Concepts:
- function_def: defines a reusable function/ability
- while: repeat as long as a condition holds
- except: handle an error raised in the protected block
"""

_FEW_SHOT_ASSISTANT_2 = json.dumps(
    {
        "mappings": {
            "function_def": "singularity",
            "while": "orbit_while",
            "except": "hawking_catch",
        },
        "rationale": {
            "function_def": "A singularity concentrates behavior into one point",
            "while": "Matter keeps orbiting while gravity holds",
            "except": "Hawking radiation is what escapes when things go wrong",
        },
    },
    ensure_ascii=False,
)


def build_messages(request: ThemeMappingRequest) -> list[dict[str, str]]:
    """OpenAI-style chat messages (system/user/assistant dicts)."""
    concept_lines = "\n".join(
        f"- {c.key}: {_CONCEPT_DESCRIPTIONS[c]}" for c in request.concepts
    )
    user_parts = [f"Theme: {request.theme}"]
    if request.output_language:
        user_parts.append(f"Output language: {request.output_language}")
    user_parts.append(f"Concepts:\n{concept_lines}")
    if request.existing_mappings:
        existing = {c.key: t for c, t in request.existing_mappings.items()}
        user_parts.append(
            "Keep these existing tokens unchanged unless they violate a rule:\n"
            + json.dumps(existing, ensure_ascii=False)
        )
    if request.correction_feedback:
        user_parts.append(
            "Your previous attempt was rejected by the validator. Fix exactly "
            f"these problems and try again:\n{request.correction_feedback}"
        )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _FEW_SHOT_USER},
        {"role": "assistant", "content": _FEW_SHOT_ASSISTANT},
        {"role": "user", "content": _FEW_SHOT_USER_2},
        {"role": "assistant", "content": _FEW_SHOT_ASSISTANT_2},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


ERROR_TRANSLATION_SYSTEM_PROMPT = """\
You translate technical error messages into a user's personal theme
vocabulary. Keep the message SHORT, actionable, and faithful to the technical
cause. Weave in the user's themed keywords where they correspond to the
constructs involved. Answer with the translated message only, no preamble.
"""


def build_error_translation_messages(
    canonical_message: str,
    theme: str,
    mappings_json: str,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": ERROR_TRANSLATION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Theme: {theme}\n"
                f"Themed keyword mapping (concept -> token): {mappings_json}\n"
                f"Technical error: {canonical_message}\n"
                "Translate:"
            ),
        },
    ]


def parse_mapping_output(raw: str) -> tuple[dict[str, str], dict[str, str]]:
    """Extract (mappings, rationale) from model output.

    Tolerates markdown fences and leading/trailing prose around the JSON.
    Raises ValueError when no usable JSON object is found.
    """
    text = raw.strip()
    if text.startswith("```"):
        first_nl = text.index("\n")
        text = text[first_nl + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("model output contains no JSON object")
    data = json.loads(text[start : end + 1])
    mappings = data.get("mappings")
    if not isinstance(mappings, dict):
        raise ValueError("model output JSON has no 'mappings' object")
    rationale = data.get("rationale") or {}
    if not isinstance(rationale, dict):
        rationale = {}
    return (
        {str(k): str(v) for k, v in mappings.items()},
        {str(k): str(v) for k, v in rationale.items()},
    )
