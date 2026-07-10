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


class ClarifyingQuestionsRequest(BaseModel):
    theme: str = Field(min_length=1, max_length=2000)


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
