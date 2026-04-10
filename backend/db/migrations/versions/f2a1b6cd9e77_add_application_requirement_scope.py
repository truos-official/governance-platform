"""add_application_requirement_scope

Revision ID: f2a1b6cd9e77
Revises: c57adf1bbe7d
Create Date: 2026-04-08 23:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2a1b6cd9e77"
down_revision: Union[str, Sequence[str], None] = "c57adf1bbe7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "application_requirement",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("application_id", sa.UUID(), sa.ForeignKey("application.id"), nullable=False),
        sa.Column("requirement_id", sa.UUID(), sa.ForeignKey("requirement.id"), nullable=False),
        sa.Column("selected_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("application_id", "requirement_id", name="uq_application_requirement"),
    )
    op.create_index(
        "ix_application_requirement_application_id",
        "application_requirement",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_requirement_requirement_id",
        "application_requirement",
        ["requirement_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_application_requirement_requirement_id", table_name="application_requirement")
    op.drop_index("ix_application_requirement_application_id", table_name="application_requirement")
    op.drop_table("application_requirement")

