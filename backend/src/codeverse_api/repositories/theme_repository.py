from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from codeverse_api.db.models import ThemeDictionaryRow
from codeverse_core.theme_mapping.dictionary import ThemeDictionary
from codeverse_core.theme_mapping.generator import TaxonomyThemeDictionary


class ThemeRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def save(
        self,
        user_id: uuid.UUID,
        dictionary: ThemeDictionary | TaxonomyThemeDictionary,
        raw_model_output: str,
        provider_name: str,
        model_name: str,
    ) -> ThemeDictionaryRow:
        existing_max = self._db.execute(
            select(ThemeDictionaryRow.version)
            .where(
                ThemeDictionaryRow.user_id == user_id,
                ThemeDictionaryRow.theme_name == dictionary.theme,
            )
            .order_by(ThemeDictionaryRow.version.desc())
        ).scalars().first()
        next_version = (existing_max or 0) + 1

        # Universal dictionary keys are UniversalConcept objects; taxonomy ones are strings
        raw_rationale = dictionary.rationale or {}
        rationale_json = {
            (getattr(k, "key", k)): v for k, v in raw_rationale.items()
        }

        row = ThemeDictionaryRow(
            user_id=user_id,
            theme_name=dictionary.theme,
            mappings=dictionary.to_json_mappings(),
            rationale=rationale_json or None,
            llm_provider=provider_name,
            llm_model=model_name,
            raw_model_output=raw_model_output,
            version=next_version,
            is_active=True,
        )
        self._db.add(row)
        self._db.flush()
        return row

    def get(self, theme_dictionary_id: uuid.UUID) -> ThemeDictionaryRow | None:
        return self._db.get(ThemeDictionaryRow, theme_dictionary_id)

    def list_for_user(self, user_id: uuid.UUID) -> list[ThemeDictionaryRow]:
        return list(
            self._db.execute(
                select(ThemeDictionaryRow)
                .where(ThemeDictionaryRow.user_id == user_id, ThemeDictionaryRow.is_active)
                .order_by(ThemeDictionaryRow.created_at.desc())
            ).scalars()
        )

    @staticmethod
    def to_domain(row: ThemeDictionaryRow) -> ThemeDictionary | TaxonomyThemeDictionary:
        # Check if this represents an expanded taxonomy dictionary
        from codeverse_core.concepts import UniversalConcept

        def is_universal_key(key: str) -> bool:
            try:
                UniversalConcept.from_key(key)
            except ValueError:
                return False
            return True

        is_taxonomy = any(not is_universal_key(k) for k in row.mappings)
        
        if is_taxonomy:
            return TaxonomyThemeDictionary(
                theme=row.theme_name,
                mappings=row.mappings,
                rationale=row.rationale or {},
                provider_name=row.llm_provider,
                model=row.llm_model,
            )
        else:
            return ThemeDictionary.from_json_mappings(
                theme=row.theme_name,
                mappings=row.mappings,
                rationale=row.rationale,
            )
