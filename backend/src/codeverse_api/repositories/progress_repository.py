from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from codeverse_api.db.models import ModuleProgress

_PASS_THRESHOLD = 70


class ProgressRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def record_score(
        self,
        user_id: uuid.UUID,
        theme_dictionary_id: uuid.UUID,
        module_id: str,
        score: int,
    ) -> ModuleProgress:
        """Upsert one module's progress, keeping the BEST score ever reached.

        A weaker retry never lowers a module already mastered — progress only
        moves forward. Crossing the pass threshold stamps ``completed_at`` once.
        """
        row = self._db.execute(
            select(ModuleProgress).where(
                ModuleProgress.user_id == user_id,
                ModuleProgress.theme_dictionary_id == theme_dictionary_id,
                ModuleProgress.module_id == module_id,
            )
        ).scalars().first()

        now = datetime.now(timezone.utc)
        if row is None:
            row = ModuleProgress(
                user_id=user_id,
                theme_dictionary_id=theme_dictionary_id,
                module_id=module_id,
                best_score=score,
                passed=score >= _PASS_THRESHOLD,
                completed_at=now if score >= _PASS_THRESHOLD else None,
            )
            self._db.add(row)
        else:
            if score > row.best_score:
                row.best_score = score
            if score >= _PASS_THRESHOLD and not row.passed:
                row.passed = True
                row.completed_at = now
        self._db.flush()
        return row

    def list_for_theme(
        self,
        user_id: uuid.UUID,
        theme_dictionary_id: uuid.UUID,
    ) -> list[ModuleProgress]:
        return list(
            self._db.execute(
                select(ModuleProgress).where(
                    ModuleProgress.user_id == user_id,
                    ModuleProgress.theme_dictionary_id == theme_dictionary_id,
                )
            ).scalars()
        )
