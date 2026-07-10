"""initial schema: users, theme_dictionaries, projects, project_files, execution_runs

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "theme_dictionaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("theme_name", sa.Text(), nullable=False),
        sa.Column("mappings", postgresql.JSONB(), nullable=False),
        sa.Column("rationale", postgresql.JSONB(), nullable=True),
        sa.Column("llm_provider", sa.String(64), nullable=False),
        sa.Column("llm_model", sa.String(200), nullable=False),
        sa.Column("raw_model_output", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id", "theme_name", "version", name="uq_theme_user_name_version"
        ),
    )
    op.create_index(
        "ix_theme_dictionaries_user_active",
        "theme_dictionaries",
        ["user_id", "is_active"],
    )

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "theme_dictionary_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("theme_dictionaries.id"),
            nullable=False,
        ),
        sa.Column("target_language", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_language IN ('python', 'sql')", name="ck_project_language"
        ),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    op.create_table(
        "project_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("source_content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "filename", name="uq_project_filename"),
    )
    op.create_index("ix_project_files_project_id", "project_files", ["project_id"])

    op.create_table(
        "execution_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("project_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("generated_code", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("stdout", sa.Text(), nullable=True),
        sa.Column("stderr_raw", sa.Text(), nullable=True),
        sa.Column("error_message_themed", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('success','runtime_error','parse_error','codegen_error',"
            "'timeout','sandbox_error')",
            name="ck_execution_status",
        ),
    )
    op.create_index(
        "ix_execution_runs_file_created",
        "execution_runs",
        ["project_file_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("execution_runs")
    op.drop_table("project_files")
    op.drop_table("projects")
    op.drop_table("theme_dictionaries")
    op.drop_table("users")
