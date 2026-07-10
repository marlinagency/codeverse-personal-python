from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from codeverse_api.db.models import ExecutionRun


class ExecutionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        project_file_id: uuid.UUID,
        user_id: uuid.UUID,
        generated_code: str,
        status: str,
        stdout: str | None = None,
        stderr_raw: str | None = None,
        error_message_themed: str | None = None,
        duration_ms: int | None = None,
        started_at: datetime | None = None,
    ) -> ExecutionRun:
        run = ExecutionRun(
            project_file_id=project_file_id,
            user_id=user_id,
            generated_code=generated_code,
            status=status,
            stdout=stdout,
            stderr_raw=stderr_raw,
            error_message_themed=error_message_themed,
            duration_ms=duration_ms,
            started_at=started_at or datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        self._db.add(run)
        self._db.flush()
        return run

    def list_for_file(self, project_file_id: uuid.UUID, limit: int = 50) -> list[ExecutionRun]:
        return list(
            self._db.execute(
                select(ExecutionRun)
                .where(ExecutionRun.project_file_id == project_file_id)
                .order_by(ExecutionRun.created_at.desc())
                .limit(limit)
            ).scalars()
        )
