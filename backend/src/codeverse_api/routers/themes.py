from __future__ import annotations

from collections import Counter
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
    ThemeDictionaryCatalogOut,
    ThemeDictionaryEntryOut,
    ThemeDictionaryOut,
    ThemeGenerateRequest,
)
from codeverse_api.security.auth import get_current_user_id
from codeverse_core.cvl.pipeline import CompilationError, CompilationPipeline
from codeverse_core.data.taxonomy_loader import load_taxonomy
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


@router.get("/{theme_dictionary_id}/dictionary", response_model=ThemeDictionaryCatalogOut)
def get_theme_dictionary_catalog(
    theme_dictionary_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ThemeDictionaryCatalogOut:
    """Return every Python mapping enriched with canonical taxonomy metadata.

    The normal theme response is optimized for compilation. This catalog is
    optimized for learning: it tells the UI what each personal token maps to,
    where it belongs, and whether it is guaranteed to run in the sandbox.
    """
    row = ThemeRepository(db).get(theme_dictionary_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="theme dictionary not found")

    taxonomy = {concept.concept_id: concept for concept in load_taxonomy("python")}
    entries: list[ThemeDictionaryEntryOut] = []
    for concept_id, personal_token in row.mappings.items():
        if not concept_id.startswith("py_"):
            continue
        concept = taxonomy.get(concept_id)
        if concept is None:
            fallback_name = concept_id.removeprefix("py_").replace("_", " ").title()
            entries.append(
                ThemeDictionaryEntryOut(
                    concept_id=concept_id,
                    personal_token=str(personal_token),
                    python_name=fallback_name,
                    real_syntax=fallback_name,
                    category="additional_python",
                    tier="core",
                    description="A named Python concept available in this personal dictionary.",
                    rationale=(row.rationale or {}).get(concept_id),
                    sandbox_safe=True,
                )
            )
            continue
        entries.append(
            ThemeDictionaryEntryOut(
                concept_id=concept_id,
                personal_token=str(personal_token),
                python_name=concept.title,
                real_syntax=concept.real_syntax,
                category=concept.category,
                tier=concept.tier,
                description=concept.description,
                rationale=(row.rationale or {}).get(concept_id),
                sandbox_safe=concept.is_sandbox_safe,
            )
        )

    tier_order = {"core": 0, "builtin": 1, "method": 2, "type": 3, "exception": 4, "library": 5}
    entries.sort(key=lambda entry: (entry.category, tier_order.get(entry.tier, 9), entry.python_name.casefold()))
    category_counts = Counter(entry.category for entry in entries)
    tier_counts = Counter(entry.tier for entry in entries)
    return ThemeDictionaryCatalogOut(
        theme_dictionary_id=theme_dictionary_id,
        theme_name=row.theme_name,
        total=len(entries),
        category_counts=dict(sorted(category_counts.items())),
        tier_counts=dict(sorted(tier_counts.items())),
        entries=entries,
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
