"""SQLAlchemy ORM models — see docs/ (plan §7) for the schema rationale."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    JSON,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from codeverse_api.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    theme_dictionaries: Mapped[list["ThemeDictionaryRow"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ThemeDictionaryRow(Base):
    __tablename__ = "theme_dictionaries"
    __table_args__ = (
        UniqueConstraint("user_id", "theme_name", "version", name="uq_theme_user_name_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    theme_name: Mapped[str] = mapped_column(Text, nullable=False)
    mappings: Mapped[dict] = mapped_column(JSON, nullable=False)
    rationale: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    llm_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(200), nullable=False)
    raw_model_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User] = relationship(back_populates="theme_dictionaries")
    projects: Mapped[list["Project"]] = relationship(back_populates="theme_dictionary")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    theme_dictionary_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("theme_dictionaries.id"), nullable=False
    )
    target_language: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    __table_args__ = (
        CheckConstraint("target_language IN ('python', 'sql')", name="ck_project_language"),
    )

    user: Mapped[User] = relationship(back_populates="projects")
    theme_dictionary: Mapped[ThemeDictionaryRow] = relationship(back_populates="projects")
    files: Mapped[list["ProjectFile"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectFile(Base):
    __tablename__ = "project_files"
    __table_args__ = (UniqueConstraint("project_id", "filename", name="uq_project_filename"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    project: Mapped[Project] = relationship(back_populates="files")
    execution_runs: Mapped[list["ExecutionRun"]] = relationship(
        back_populates="project_file", cascade="all, delete-orphan"
    )


class ModuleProgress(Base):
    """Per-learner mastery of one learning module for one theme dictionary.

    One row per (user, theme_dictionary, module_id). ``best_score`` keeps the
    highest score the learner has reached so progress never regresses on a
    weaker retry; ``passed`` and ``completed_at`` mark mastery (score >= 70).
    """

    __tablename__ = "module_progress"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "theme_dictionary_id", "module_id", name="uq_module_progress"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    theme_dictionary_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("theme_dictionaries.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[str] = mapped_column(String(64), nullable=False)
    best_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class ExecutionRun(Base):
    __tablename__ = "execution_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('success','runtime_error','parse_error','codegen_error',"
            "'timeout','sandbox_error')",
            name="ck_execution_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("project_files.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    generated_code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message_themed: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project_file: Mapped[ProjectFile] = relationship(back_populates="execution_runs")
