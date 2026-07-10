"""Clarifying-questions wizard: one LLM call that turns a free-text theme
into ~7 multiple-choice questions specific to that world, so the answers can
ground the real theme-profile call (``taxonomy_generator.generate_theme_profile``)
with richer, user-confirmed detail before the vocabulary is generated.

This follows the same "LLM is the brain" contract as the theme profile: the
questions and their emoji icons are invented fresh per theme, never drawn
from a curated per-theme table — a beekeeping prompt gets beekeeping
questions, a Witcher prompt gets Witcher questions, with no special-casing.

Icons are a single emoji string today (``ClarifyingOption.icon``). Fireworks
image generation (``flux-1-schnell-fp8``) returned 401 Unauthorized on this
account (image workflows aren't enabled/billed), so AI-generated icon images
aren't available yet; ``icon`` is named generically so swapping it to hold an
image URL later is a one-field change, not a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass

from codeverse_core.theme_mapping.json_extraction import extract_json_object
from codeverse_core.theme_mapping.taxonomy_generator import TaxonomyGenerationError

#: guaranteed not to appear in THEME_PROFILE_SYSTEM_PROMPT or
#: CATEGORY_MAPPING_SYSTEM_PROMPT (see taxonomy_prompts.py) — lets
#: FakeProvider.chat() route this prompt unambiguously without relying on
#: the shared "Theme:" line every one of these prompts also contains.
CLARIFYING_QUESTIONS_MARKER = "multiple-choice clarifying wizard"


@dataclass(frozen=True)
class ClarifyingOption:
    label: str
    #: single emoji today; same field will hold an image URL once AI-icon
    #: generation is available — no rename needed at that point.
    icon: str


@dataclass(frozen=True)
class ClarifyingQuestion:
    id: str
    question: str
    options: tuple[ClarifyingOption, ...]


CLARIFYING_QUESTIONS_SYSTEM_PROMPT = """\
You are CodeVerse's onboarding guide. A user just described a theme for their
personalized Python learning experience — a single word ("Valorant") or a
whole sentence ("I'm a beekeeper and I spend my days with hives and honey
harvests"). Before generating their personal vocabulary, design a short
multiple-choice clarifying wizard: 7 questions that dig into the SPECIFIC
world the user just described, so their answers sharpen and confirm the
theme before generation.

Rules:
- Every question must be concretely about the user's own theme — never
  generic programming questions, never generic "what's your skill level"
  filler. A beekeeping prompt gets beekeeping questions; a Witcher prompt
  gets Witcher questions.
- Exactly 7 questions.
- Each question has 3 to 4 short answer options (a few words each).
- Each option gets one single emoji that visually represents it.
- Vary what the questions probe: favorite objects/roles/actions in that
  world, tone preference, what part of the world excites the learner most,
  what usually confuses them about code, etc. — do not ask 7 variations of
  the same question.
- Keep question and option text short — this renders as compact UI cards.

Respond with ONLY a JSON object:
{"questions": [
  {"id": "q1", "question": "...", "options": [
    {"label": "...", "icon": "🐝"}, {"label": "...", "icon": "🍯"}
  ]},
  ... exactly 7 items ...
]}
"""

_FEW_SHOT_USER = "Theme: Valorant"
_FEW_SHOT_ASSISTANT = """\
{"questions": [
  {"id": "q1", "question": "Which role do you main?", "options": [
    {"label": "Duelist", "icon": "🔫"}, {"label": "Controller", "icon": "💨"},
    {"label": "Sentinel", "icon": "🛡️"}, {"label": "Initiator", "icon": "🎯"}
  ]},
  {"id": "q2", "question": "What's most satisfying in a round?", "options": [
    {"label": "A clean clutch", "icon": "🏆"}, {"label": "A perfect smoke lineup", "icon": "💭"},
    {"label": "An entry frag", "icon": "⚡"}
  ]},
  {"id": "q3", "question": "What tone fits you best?", "options": [
    {"label": "Tactical and calm", "icon": "🧊"}, {"label": "Loud and hype", "icon": "🔥"}
  ]},
  {"id": "q4", "question": "Which map feeling do you like most?", "options": [
    {"label": "Tight site executes", "icon": "💥"}, {"label": "Long-range angles", "icon": "🔭"},
    {"label": "Rotation mind games", "icon": "🔄"}
  ]},
  {"id": "q5", "question": "What part of coding confuses you most right now?", "options": [
    {"label": "Loops", "icon": "🔁"}, {"label": "Functions", "icon": "🧩"},
    {"label": "Conditionals", "icon": "❓"}, {"label": "Not sure yet", "icon": "🤔"}
  ]},
  {"id": "q6", "question": "What do you want your code's \\"voice\\" to sound like?", "options": [
    {"label": "Team callouts", "icon": "📢"}, {"label": "Calm briefings", "icon": "🎙️"}
  ]},
  {"id": "q7", "question": "What's the ultimate win condition for you?", "options": [
    {"label": "Ace the round", "icon": "🏅"}, {"label": "Defuse under pressure", "icon": "💣"},
    {"label": "Outsmart the enemy economy", "icon": "💰"}
  ]}
]}\
"""


def build_clarifying_questions_messages(theme: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": CLARIFYING_QUESTIONS_SYSTEM_PROMPT},
        {"role": "user", "content": _FEW_SHOT_USER},
        {"role": "assistant", "content": _FEW_SHOT_ASSISTANT},
        {"role": "user", "content": f"Theme: {theme}"},
    ]


def parse_clarifying_questions_output(raw: str) -> list[ClarifyingQuestion]:
    data = extract_json_object(raw)
    questions = data.get("questions")
    if not isinstance(questions, list) or not (5 <= len(questions) <= 8):
        raise ValueError("expected 5-8 clarifying questions in 'questions'")

    result: list[ClarifyingQuestion] = []
    for index, item in enumerate(questions):
        if not isinstance(item, dict):
            raise ValueError(f"question {index} is not an object")
        question_text = str(item.get("question", "")).strip()
        if not question_text:
            raise ValueError(f"question {index} has no 'question' text")

        raw_options = item.get("options")
        if not isinstance(raw_options, list) or not (2 <= len(raw_options) <= 5):
            raise ValueError(f"question {index} needs 2-5 options")

        options: list[ClarifyingOption] = []
        for opt in raw_options:
            if not isinstance(opt, dict):
                raise ValueError(f"question {index} has a malformed option")
            label = str(opt.get("label", "")).strip()
            if not label:
                raise ValueError(f"question {index} has an option with no label")
            icon = str(opt.get("icon", "")).strip()
            options.append(ClarifyingOption(label=label, icon=icon))

        result.append(
            ClarifyingQuestion(
                id=str(item.get("id") or f"q{index + 1}").strip(),
                question=question_text,
                options=tuple(options),
            )
        )
    return result


def generate_clarifying_questions(
    provider,
    theme: str,
    max_attempts: int = 3,
) -> list[ClarifyingQuestion]:
    """Retries on parse/validation failure, same pattern as
    ``taxonomy_generator.generate_theme_profile`` — a plain retry is enough
    since there's no corrective feedback loop to run against."""
    last_error: Exception | None = None
    for _attempt in range(1, max_attempts + 1):
        raw = provider.chat(
            build_clarifying_questions_messages(theme),
            temperature=0.7,
            max_tokens=2048,
        )
        try:
            return parse_clarifying_questions_output(raw)
        except Exception as exc:  # noqa: BLE001 - any parse/shape failure retries
            last_error = exc

    raise TaxonomyGenerationError(
        f"'{theme}' için netleştirme soruları {max_attempts} denemede üretilemedi: {last_error}"
    )
