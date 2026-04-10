"""add_control_lifecycle_tag

Revision ID: c3a5e7f9a203
Revises: b2f4c6d8e102
Create Date: 2026-04-09 12:27:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3a5e7f9a203"
down_revision: Union[str, Sequence[str], None] = "b2f4c6d8e102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "control_lifecycle_tag",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("control_id", sa.UUID(), sa.ForeignKey("control.id"), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("suggested_by", sa.String(), nullable=False, server_default=sa.text("'llm'")),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("control_id", "tag", name="uq_control_lifecycle_tag"),
    )
    op.create_index(
        "ix_control_lifecycle_tag_control_id",
        "control_lifecycle_tag",
        ["control_id"],
        unique=False,
    )
    op.create_index(
        "ix_control_lifecycle_tag_approved",
        "control_lifecycle_tag",
        ["approved"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_control_lifecycle_tag_approved", table_name="control_lifecycle_tag")
    op.drop_index("ix_control_lifecycle_tag_control_id", table_name="control_lifecycle_tag")
    op.drop_table("control_lifecycle_tag")
