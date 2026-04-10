"""extend_curation_queue_item

Revision ID: f6d8b0c2d506
Revises: e5c7a9b1c405
Create Date: 2026-04-09 12:37:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6d8b0c2d506"
down_revision: Union[str, Sequence[str], None] = "e5c7a9b1c405"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE curation_status ADD VALUE IF NOT EXISTS 'NEEDS_REVISION'")

    op.add_column("curation_queue_item", sa.Column("control_id", sa.UUID(), nullable=True))
    op.add_column("curation_queue_item", sa.Column("item_type", sa.String(), nullable=True))
    op.add_column("curation_queue_item", sa.Column("proposed", sa.JSON(), nullable=True))
    op.add_column("curation_queue_item", sa.Column("justification", sa.Text(), nullable=True))
    op.add_column("curation_queue_item", sa.Column("parent_chain", sa.JSON(), nullable=True))
    op.add_column("curation_queue_item", sa.Column("proposed_by", sa.String(), nullable=True))
    op.add_column("curation_queue_item", sa.Column("proposed_at", sa.DateTime(), nullable=True))
    op.add_column("curation_queue_item", sa.Column("reviewed_by", sa.String(), nullable=True))
    op.add_column("curation_queue_item", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column("curation_queue_item", sa.Column("reviewer_notes", sa.Text(), nullable=True))
    op.add_column(
        "curation_queue_item",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )

    # Backfill temporal metadata from submitted_at when available.
    op.execute(
        """
        UPDATE curation_queue_item
        SET created_at = COALESCE(submitted_at, created_at),
            proposed_at = COALESCE(proposed_at, submitted_at, created_at)
        """
    )

    op.create_index(
        "ix_curation_queue_item_status",
        "curation_queue_item",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_curation_queue_item_item_type",
        "curation_queue_item",
        ["item_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_curation_queue_item_item_type", table_name="curation_queue_item")
    op.drop_index("ix_curation_queue_item_status", table_name="curation_queue_item")
    op.drop_column("curation_queue_item", "created_at")
    op.drop_column("curation_queue_item", "reviewer_notes")
    op.drop_column("curation_queue_item", "reviewed_at")
    op.drop_column("curation_queue_item", "reviewed_by")
    op.drop_column("curation_queue_item", "proposed_at")
    op.drop_column("curation_queue_item", "proposed_by")
    op.drop_column("curation_queue_item", "parent_chain")
    op.drop_column("curation_queue_item", "justification")
    op.drop_column("curation_queue_item", "proposed")
    op.drop_column("curation_queue_item", "item_type")
    op.drop_column("curation_queue_item", "control_id")
