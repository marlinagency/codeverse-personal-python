from __future__ import annotations

from collections import Counter
from dataclasses import replace
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from codeverse_api.config import Settings, get_settings
from codeverse_api.dependencies import (
    build_amd_provider,
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
    ThemeDictionaryQualityOut,
    ThemeGenerateRequest,
    ThemeRegenerateRequest,
)
from codeverse_api.security.auth import get_current_user_id
from codeverse_core.cvl.pipeline import CompilationError, CompilationPipeline
from codeverse_core.data.taxonomy_loader import load_taxonomy
from codeverse_core.personal_python import build_personal_python_lesson
from codeverse_core.theme_mapping.clarifying_questions import generate_clarifying_questions
from codeverse_core.theme_mapping.generator import TaxonomyThemeDictionaryGenerator
from codeverse_core.theme_mapping.llm_provider import LLMProvider, LLMProviderError
from codeverse_core.theme_mapping.quality import assess_dictionary_quality
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
    settings: Settings = Depends(get_settings),
) -> ThemeDictionaryOut:
    # Curated chips route to the AMD-hosted model (fine-tuned on these exact
    # prompts). The primary provider is the fallback: if AMD is unreachable or
    # returns something invalid, we transparently retry with it so the site
    # never breaks for the visitor.
    active_generator = generator
    active_provider = provider
    if body.use_amd and settings.amd_enabled:
        active_provider = build_amd_provider(settings)
        active_generator = TaxonomyThemeDictionaryGenerator(active_provider)  # type: ignore

    def _run(gen: TaxonomyThemeDictionaryGenerator):
        return gen.generate_profile_seeded(
            body.theme,
            output_language=body.output_language or "en",
            languages=("python",),
            clarifying_answers=body.clarifying_answers,
        )

    try:
        dictionary = _run(active_generator)
    except (ThemeDictionaryValidationError, TaxonomyGenerationError, LLMProviderError) as exc:
        if active_generator is generator:
            # already the primary provider — surface the real error
            if isinstance(exc, LLMProviderError):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "message": "the LLM provider did not return a valid theme output",
                        "problems": [str(exc)],
                    },
                ) from exc
            problems = getattr(exc, "problems", [str(exc)])
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "theme dictionary could not be generated", "problems": problems},
            ) from exc
        # AMD path failed — fall back to the primary provider
        active_generator = generator
        active_provider = provider
        try:
            dictionary = _run(active_generator)
        except (ThemeDictionaryValidationError, TaxonomyGenerationError) as exc2:
            problems = getattr(exc2, "problems", [str(exc2)])
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "theme dictionary could not be generated", "problems": problems},
            ) from exc2
        except LLMProviderError as exc2:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "the LLM provider did not return a valid theme output",
                    "problems": [str(exc2)],
                },
            ) from exc2

    model_name = getattr(active_provider, "model", active_provider.provider_name)
    repo = ThemeRepository(db)
    raw_output = dictionary.profile.raw_model_output if getattr(dictionary, "profile", None) else ""
    row = repo.save(user_id, dictionary, raw_output, active_provider.provider_name, model_name)
    db.commit()
    return ThemeDictionaryOut.model_validate(row)


@router.post(
    "/{theme_dictionary_id}/regenerate",
    response_model=ThemeDictionaryOut,
    status_code=status.HTTP_201_CREATED,
)
def regenerate_theme(
    theme_dictionary_id: uuid.UUID,
    body: ThemeRegenerateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    generator: TaxonomyThemeDictionaryGenerator = Depends(get_theme_generator),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ThemeDictionaryOut:
    repo = ThemeRepository(db)
    previous = repo.get(theme_dictionary_id)
    if previous is None or previous.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="theme dictionary not found")

    prompt = body.theme.strip() if body.theme else previous.theme_name
    try:
        generated = generator.generate_profile_seeded(
            prompt,
            output_language="en",
            languages=("python",),
            clarifying_answers=body.clarifying_answers,
        )
    except (ThemeDictionaryValidationError, TaxonomyGenerationError) as exc:
        problems = getattr(exc, "problems", [str(exc)])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "theme dictionary could not be regenerated", "problems": problems},
        ) from exc
    except LLMProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "the LLM provider did not return a valid theme output", "problems": [str(exc)]},
        ) from exc

    # Keep one version chain even when the model slightly reformats the label.
    generated = replace(generated, theme=previous.theme_name)
    raw_output = generated.profile.raw_model_output if generated.profile else ""
    model_name = getattr(provider, "model", provider.provider_name)
    row = repo.save(
        user_id,
        generated,
        raw_output,
        provider.provider_name,
        model_name,
    )
    repo.deactivate(previous)
    db.commit()
    return ThemeDictionaryOut.model_validate(row)


@router.post("/questions", response_model=ClarifyingQuestionsOut)
def get_clarifying_questions(
    body: ClarifyingQuestionsRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    provider: LLMProvider = Depends(get_llm_provider),
    settings: Settings = Depends(get_settings),
) -> ClarifyingQuestionsOut:
    active_provider = provider
    if body.use_amd and settings.amd_enabled:
        active_provider = build_amd_provider(settings)

    try:
        questions = generate_clarifying_questions(active_provider, body.theme)
    except (TaxonomyGenerationError, LLMProviderError) as exc:
        if active_provider is not provider:
            # AMD failed — retry with the primary provider
            try:
                questions = generate_clarifying_questions(provider, body.theme)
            except TaxonomyGenerationError as exc2:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "message": "clarifying questions could not be generated",
                        "problems": [str(exc2)],
                    },
                ) from exc2
            except LLMProviderError as exc2:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "message": "the LLM provider did not return valid clarifying questions",
                        "problems": [str(exc2)],
                    },
                ) from exc2
            return _questions_out(questions)
        raise _questions_error(exc)

    return _questions_out(questions)


def _questions_out(questions) -> ClarifyingQuestionsOut:
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


def _questions_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LLMProviderError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "the LLM provider did not return valid clarifying questions",
                "problems": [str(exc)],
            },
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"message": "clarifying questions could not be generated", "problems": [str(exc)]},
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
    quality = assess_dictionary_quality(row.mappings, row.rationale)
    return ThemeDictionaryCatalogOut(
        theme_dictionary_id=theme_dictionary_id,
        theme_name=row.theme_name,
        total=len(entries),
        category_counts=dict(sorted(category_counts.items())),
        tier_counts=dict(sorted(tier_counts.items())),
        quality=ThemeDictionaryQualityOut(
            overall_score=quality.overall_score,
            grade=quality.grade,
            brevity_score=quality.brevity_score,
            uniqueness_score=quality.uniqueness_score,
            diversity_score=quality.diversity_score,
            semantic_score=quality.semantic_score,
            max_token_length=quality.max_token_length,
            max_token_parts=quality.max_token_parts,
            dominant_root_share=quality.dominant_root_share,
            upgrade_recommended=quality.upgrade_recommended,
            issues=list(quality.issues),
        ),
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
