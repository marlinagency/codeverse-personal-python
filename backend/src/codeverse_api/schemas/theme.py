from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ThemeGenerateRequest(BaseModel):
    #: free text — a name or a full sentence describing the interest
    theme: str = Field(min_length=1, max_length=2000)
    output_language: str | None = "en"
    #: question -> chosen option label, from the optional clarifying wizard
    clarifying_answers: dict[str, str] | None = None
    #: true when the theme came from a curated chip — route to the AMD-hosted
    #: model (which was fine-tuned on exactly these prompts). Free text stays False.
    use_amd: bool = False


class ThemeRegenerateRequest(BaseModel):
    #: optional replacement prompt; omitted means reuse the stored world label
    theme: str | None = Field(default=None, min_length=1, max_length=2000)
    clarifying_answers: dict[str, str] | None = None


class ClarifyingQuestionsRequest(BaseModel):
    theme: str = Field(min_length=1, max_length=2000)
    #: see ThemeGenerateRequest.use_amd
    use_amd: bool = False


class ClarifyingOptionOut(BaseModel):
    label: str
    icon: str


class ClarifyingQuestionOut(BaseModel):
    id: str
    question: str
    options: list[ClarifyingOptionOut]


class ClarifyingQuestionsOut(BaseModel):
    questions: list[ClarifyingQuestionOut]


class ThemeDictionaryOut(BaseModel):
    id: uuid.UUID
    theme_name: str
    mappings: dict[str, str]
    rationale: dict[str, str] | None = None
    llm_provider: str
    llm_model: str
    version: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PersonalPythonLessonOut(BaseModel):
    theme_dictionary_id: uuid.UUID
    theme_name: str
    source_content: str
    generated_code: str
    target_language: str = "python"
    used_concepts: dict[str, str]
    focus: list[str]


class ThemeDictionaryEntryOut(BaseModel):
    concept_id: str
    personal_token: str
    python_name: str
    real_syntax: str
    category: str
    tier: str
    description: str
    rationale: str | None = None
    sandbox_safe: bool


class ThemeDictionaryQualityOut(BaseModel):
    overall_score: int
    grade: str
    brevity_score: int
    uniqueness_score: int
    diversity_score: int
    semantic_score: int
    max_token_length: int
    max_token_parts: int
    dominant_root_share: float
    upgrade_recommended: bool
    issues: list[str]


class ThemeDictionaryCatalogOut(BaseModel):
    theme_dictionary_id: uuid.UUID
    theme_name: str
    total: int
    category_counts: dict[str, int]
    tier_counts: dict[str, int]
    quality: ThemeDictionaryQualityOut
    entries: list[ThemeDictionaryEntryOut]
