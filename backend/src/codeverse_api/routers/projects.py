from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from codeverse_api.dependencies import get_db
from codeverse_api.repositories.project_repository import ProjectRepository
from codeverse_api.repositories.theme_repository import ThemeRepository
from codeverse_api.schemas.project import (
    ProjectCreateRequest,
    ProjectFileOut,
    ProjectFileUpsertRequest,
    ProjectOut,
)
from codeverse_api.security.auth import get_current_user_id

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProjectOut:
    theme_row = ThemeRepository(db).get(body.theme_dictionary_id)
    if theme_row is None or theme_row.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="theme dictionary not found"
        )

    project = ProjectRepository(db).create(
        user_id, body.name, body.theme_dictionary_id, body.target_language
    )
    db.commit()
    return ProjectOut.model_validate(project)


@router.get("", response_model=list[ProjectOut])
def list_projects(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[ProjectOut]:
    projects = ProjectRepository(db).list_for_user(user_id)
    return [ProjectOut.model_validate(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProjectOut:
    project = _get_owned_project(db, project_id, user_id)
    return ProjectOut.model_validate(project)


@router.put("/{project_id}/files", response_model=ProjectFileOut)
def upsert_file(
    project_id: uuid.UUID,
    body: ProjectFileUpsertRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProjectFileOut:
    _get_owned_project(db, project_id, user_id)
    file = ProjectRepository(db).upsert_file(project_id, body.filename, body.source_content)
    db.commit()
    return ProjectFileOut.model_validate(file)


@router.get("/{project_id}/files", response_model=list[ProjectFileOut])
def list_files(
    project_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[ProjectFileOut]:
    _get_owned_project(db, project_id, user_id)
    files = ProjectRepository(db).list_files(project_id)
    return [ProjectFileOut.model_validate(f) for f in files]


def _get_owned_project(db: Session, project_id: uuid.UUID, user_id: uuid.UUID):
    project = ProjectRepository(db).get(project_id)
    if project is None or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project
