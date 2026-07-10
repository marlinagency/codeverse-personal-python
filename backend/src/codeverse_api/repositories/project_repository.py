from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from codeverse_api.db.models import Project, ProjectFile


class ProjectRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        user_id: uuid.UUID,
        name: str,
        theme_dictionary_id: uuid.UUID,
        target_language: str,
    ) -> Project:
        project = Project(
            user_id=user_id,
            name=name,
            theme_dictionary_id=theme_dictionary_id,
            target_language=target_language,
        )
        self._db.add(project)
        self._db.flush()
        return project

    def get(self, project_id: uuid.UUID) -> Project | None:
        return self._db.get(Project, project_id)

    def list_for_user(self, user_id: uuid.UUID) -> list[Project]:
        return list(
            self._db.execute(
                select(Project)
                .where(Project.user_id == user_id)
                .order_by(Project.updated_at.desc())
            ).scalars()
        )

    def upsert_file(
        self, project_id: uuid.UUID, filename: str, source_content: str
    ) -> ProjectFile:
        existing = self._db.execute(
            select(ProjectFile).where(
                ProjectFile.project_id == project_id, ProjectFile.filename == filename
            )
        ).scalars().first()
        if existing is not None:
            existing.source_content = source_content
            self._db.flush()
            return existing

        file = ProjectFile(
            project_id=project_id, filename=filename, source_content=source_content
        )
        self._db.add(file)
        self._db.flush()
        return file

    def get_file(self, file_id: uuid.UUID) -> ProjectFile | None:
        return self._db.get(ProjectFile, file_id)

    def list_files(self, project_id: uuid.UUID) -> list[ProjectFile]:
        return list(
            self._db.execute(
                select(ProjectFile).where(ProjectFile.project_id == project_id)
            ).scalars()
        )
