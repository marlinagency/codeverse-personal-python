from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CompileRequest(BaseModel):
    """Compile-only: run the pipeline, do NOT execute the result.

    Either ``project_file_id`` (compile a saved file) or ``source_content``
    + ``theme_dictionary_id`` (compile ad-hoc, unsaved content) must be given.
    """

    project_file_id: uuid.UUID | None = None
    source_content: str | None = None
    theme_dictionary_id: uuid.UUID | None = None


class DiagnosticOut(BaseModel):
    message: str
    themed_message: str | None = None
    line: int
    col: int
    severity: str
    stage: str
    personal_source: str | None = None
    python_source: str | None = None
    personal_token: str | None = None
    python_token: str | None = None


class TokenReplacementOut(BaseModel):
    personal_token: str
    python_token: str
    col: int


class TranslationTraceLineOut(BaseModel):
    line: int
    personal_source: str
    python_source: str
    replacements: list[TokenReplacementOut] = Field(default_factory=list)


class CompileResult(BaseModel):
    success: bool
    generated_code: str | None = None
    target_language: str | None = None
    warnings: list[DiagnosticOut] = Field(default_factory=list)
    error: DiagnosticOut | None = None
    translation_trace: list[TranslationTraceLineOut] = Field(default_factory=list)


class ExecuteRequest(CompileRequest):
    pass


class ExecutionRunOut(BaseModel):
    id: uuid.UUID
    status: str
    stdout: str | None = None
    stderr_raw: str | None = None
    error_message_themed: str | None = None
    duration_ms: int | None = None
    generated_code: str | None = None
    diagnostic_error: DiagnosticOut | None = None
    translation_trace: list[TranslationTraceLineOut] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}
