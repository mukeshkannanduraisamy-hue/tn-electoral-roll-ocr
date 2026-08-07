"""Per-voter deletion flag and reason.

A Special Intensive Revision roll marks removed electors with a DELETED stamp
and a reason code. The extractor already reads both, but the voters table had
nowhere to keep them, so the status was dropped between extraction and storage
and the app could not distinguish a struck-off elector from an active one.

Revision ID: c7d8e9f0a1b2
Revises: 59f6a10e6e33
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c7d8e9f0a1b2"
down_revision = "59f6a10e6e33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default so the columns are non-null on rows that predate them,
    # matching the model's Python-side defaults (the convention this schema
    # already uses for is_supplement / verified).
    op.add_column(
        "voters",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "voters",
        sa.Column("deletion_reason", sa.String(64), nullable=False, server_default=""),
    )
    op.create_index("ix_voters_is_deleted", "voters", ["is_deleted"])


def downgrade() -> None:
    op.drop_index("ix_voters_is_deleted", table_name="voters")
    op.drop_column("voters", "deletion_reason")
    op.drop_column("voters", "is_deleted")
