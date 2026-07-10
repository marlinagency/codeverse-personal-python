"""add module progress tracking

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-09 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "module_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "theme_dictionary_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("theme_dictionaries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("module_id", sa.String(64), nullable=False),
        sa.Column("best_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "theme_dictionary_id",
            "module_id",
            name="uq_module_progress",
        ),
    )
    op.create_index(
        "ix_module_progress_user_theme",
        "module_progress",
        ["user_id", "theme_dictionary_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_module_progress_user_theme", table_name="module_progress")
    op.drop_table("module_progress")
