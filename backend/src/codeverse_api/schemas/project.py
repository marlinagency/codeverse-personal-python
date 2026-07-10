from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    theme_dictionary_id: uuid.UUID
    target_language: str = Field(pattern="^(python|sql)$")


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    theme_dictionary_id: uuid.UUID
    target_language: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectFileUpsertRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    source_content: str


class ProjectFileOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    source_content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
