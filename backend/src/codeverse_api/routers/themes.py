from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from codeverse_api.dependencies import (
    get_compilation_pipeline,
    get_db,
    get_llm_provider,
    get_theme_generator,
)
from codeverse_api.repositories.theme_repository import ThemeRepository
from codeverse_api.schemas.theme import (
    ClarifyingOptionOut,
    ClarifyingQuestionOut,
    ClarifyingQuestionsOut,
    ClarifyingQuestionsRequest,
    PersonalPythonLessonOut,
    ThemeDictionaryOut,
    ThemeGenerateRequest,
)
from codeverse_api.security.auth import get_current_user_id
from codeverse_core.cvl.pipeline import CompilationError, CompilationPipeline
from codeverse_core.personal_python import build_personal_python_lesson
from codeverse_core.theme_mapping.clarifying_questions import generate_clarifying_questions
from codeverse_core.theme_mapping.generator import TaxonomyThemeDictionaryGenerator
from codeverse_core.theme_mapping.llm_provider import LLMProvider, LLMProviderError
from codeverse_core.theme_mapping.taxonomy_generator import TaxonomyGenerationError
from codeverse_core.theme_mapping.validator import ThemeDictionaryValidationError

router = APIRouter(prefix="/themes", tags=["themes"])


@router.post("/generate", response_model=ThemeDictionaryOut, status_code=status.HTTP_201_CREATED)
def generate_theme(
    body: ThemeGenerateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    generator: TaxonomyThemeDictionaryGenerator = Depends(get_theme_generator),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ThemeDictionaryOut:
    try:
        dictionary = generator.generate_profile_seeded(
            body.theme,
            output_language=body.output_language or "en",
            languages=("python",),
            clarifying_answers=body.clarifying_answers,
        )
    except (ThemeDictionaryValidationError, TaxonomyGenerationError) as exc:
        problems = getattr(exc, "problems", [str(exc)])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "theme dictionary could not be generated", "problems": problems},
        ) from exc
    except LLMProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "the LLM provider did not return a valid theme output",
                "problems": [str(exc)],
            },
        ) from exc

    model_name = getattr(provider, "model", provider.provider_name)
    repo = ThemeRepository(db)
    raw_output = dictionary.profile.raw_model_output if getattr(dictionary, "profile", None) else ""
    row = repo.save(user_id, dictionary, raw_output, provider.provider_name, model_name)
    db.commit()
    return ThemeDictionaryOut.model_validate(row)


@router.post("/questions", response_model=ClarifyingQuestionsOut)
def get_clarifying_questions(
    body: ClarifyingQuestionsRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ClarifyingQuestionsOut:
    try:
        questions = generate_clarifying_questions(provider, body.theme)
    except TaxonomyGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "clarifying questions could not be generated", "problems": [str(exc)]},
        ) from exc
    except LLMProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "the LLM provider did not return valid clarifying questions",
                "problems": [str(exc)],
            },
        ) from exc

    return ClarifyingQuestionsOut(
        questions=[
            ClarifyingQuestionOut(
                id=q.id,
                question=q.question,
                options=[ClarifyingOptionOut(label=o.label, icon=o.icon) for o in q.options],
            )
            for q in questions
        ]
    )


@router.get("", response_model=list[ThemeDictionaryOut])
def list_themes(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[ThemeDictionaryOut]:
    rows = ThemeRepository(db).list_for_user(user_id)
    return [ThemeDictionaryOut.model_validate(r) for r in rows]


@router.get("/{theme_dictionary_id}/lesson", response_model=PersonalPythonLessonOut)
def get_personal_python_lesson(
    theme_dictionary_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    pipeline: CompilationPipeline = Depends(get_compilation_pipeline),
) -> PersonalPythonLessonOut:
    row = ThemeRepository(db).get(theme_dictionary_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="theme dictionary not found")

    dictionary = ThemeRepository.to_domain(row)
    lesson = build_personal_python_lesson(dictionary)
    try:
        compiled = pipeline.compile(lesson.source_content, dictionary)
    except CompilationError as exc:
        problems = [f"{d.stage}:{d.line}:{d.col} {d.message}" for d in exc.diagnostics]
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Personal Python lesson could not be compiled",
                "problems": problems,
            },
        ) from exc

    return PersonalPythonLessonOut(
        theme_dictionary_id=theme_dictionary_id,
        theme_name=lesson.theme_name,
        source_content=lesson.source_content,
        generated_code=compiled.codegen.source_code,
        target_language=compiled.codegen.target_language,
        used_concepts=lesson.used_concepts,
        focus=list(lesson.focus),
    )


@router.get("/{theme_dictionary_id}", response_model=ThemeDictionaryOut)
def get_theme(
    theme_dictionary_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ThemeDictionaryOut:
    row = ThemeRepository(db).get(theme_dictionary_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="theme dictionary not found")
    return ThemeDictionaryOut.model_validate(row)
