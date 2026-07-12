from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from codeverse_api.dependencies import get_compilation_pipeline, get_db
from codeverse_api.repositories.project_repository import ProjectRepository
from codeverse_api.repositories.theme_repository import ThemeRepository
from codeverse_api.schemas.execution import (
    CompileRequest,
    CompileResult,
    DiagnosticOut,
    TokenReplacementOut,
    TranslationTraceLineOut,
)
from codeverse_api.security.auth import get_current_user_id
from codeverse_core.cvl.pipeline import CompilationError, CompilationPipeline
from codeverse_core.cvl.translation_trace import TranslationTraceLine, build_translation_trace
from codeverse_core.theme_mapping.dictionary import ThemeDictionary

router = APIRouter(tags=["compile"])


def trace_out(trace: tuple[TranslationTraceLine, ...]) -> list[TranslationTraceLineOut]:
    return [
        TranslationTraceLineOut(
            line=item.line,
            personal_source=item.personal_source,
            python_source=item.python_source,
            replacements=[
                TokenReplacementOut(
                    personal_token=replacement.personal_token,
                    python_token=replacement.python_token,
                    col=replacement.col,
                )
                for replacement in item.replacements
            ],
        )
        for item in trace
    ]


def diagnostic_out(
    diagnostic,
    trace: tuple[TranslationTraceLine, ...],
) -> DiagnosticOut:
    trace_line = next((item for item in trace if item.line == diagnostic.line), None)
    replacement = None
    if trace_line is not None:
        replacement = next(
            (
                item
                for item in trace_line.replacements
                if item.col <= diagnostic.col <= item.col + len(item.personal_token)
            ),
            None,
        )
    return DiagnosticOut(
        message=diagnostic.message,
        themed_message=diagnostic.themed_message,
        line=diagnostic.line,
        col=diagnostic.col,
        severity=diagnostic.severity,
        stage=diagnostic.stage,
        personal_source=trace_line.personal_source if trace_line else None,
        python_source=trace_line.python_source if trace_line else None,
        personal_token=replacement.personal_token if replacement else None,
        python_token=replacement.python_token if replacement else None,
    )


def resolve_source_and_dictionary(
    db: Session,
    user_id: uuid.UUID,
    body: CompileRequest,
) -> tuple[str, ThemeDictionary]:
    """Either load a saved project file, or compile ad-hoc unsaved content."""
    if body.project_file_id is not None:
        file = ProjectRepository(db).get_file(body.project_file_id)
        if file is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
        project = ProjectRepository(db).get(file.project_id)
        if project is None or project.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
        theme_row = ThemeRepository(db).get(project.theme_dictionary_id)
        if theme_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="theme dictionary not found"
            )
        return file.source_content, ThemeRepository.to_domain(theme_row)

    if body.source_content is None or body.theme_dictionary_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="either 'project_file_id' or 'source_content' + 'theme_dictionary_id' is required",
        )
    theme_row = ThemeRepository(db).get(body.theme_dictionary_id)
    if theme_row is None or theme_row.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="theme dictionary not found")
    return body.source_content, ThemeRepository.to_domain(theme_row)


@router.post("/compile", response_model=CompileResult)
def compile_source(
    body: CompileRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    pipeline: CompilationPipeline = Depends(get_compilation_pipeline),
) -> CompileResult:
    source, dictionary = resolve_source_and_dictionary(db, user_id, body)
    trace = build_translation_trace(source, dictionary)

    try:
        result = pipeline.compile(source, dictionary)
    except CompilationError as exc:
        first = exc.diagnostics[0]
        return CompileResult(
            success=False,
            error=diagnostic_out(first, trace),
            translation_trace=trace_out(trace),
        )

    return CompileResult(
        success=True,
        generated_code=result.codegen.source_code,
        target_language=result.codegen.target_language,
        warnings=[
            diagnostic_out(w, trace)
            for w in result.warnings
        ],
        translation_trace=trace_out(trace),
    )
