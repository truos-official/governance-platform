"""add_app_interpretation

Revision ID: b2f4c6d8e102
Revises: a1d3e5f7b901
Create Date: 2026-04-09 12:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2f4c6d8e102"
down_revision: Union[str, Sequence[str], None] = "a1d3e5f7b901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_interpretation",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("application_id", sa.UUID(), sa.ForeignKey("application.id"), nullable=False),
        sa.Column("requirement_id", sa.UUID(), sa.ForeignKey("requirement.id"), nullable=False),
        sa.Column("control_id", sa.UUID(), sa.ForeignKey("control.id"), nullable=False),
        sa.Column("interpretation_text", sa.Text(), nullable=True),
        sa.Column("threshold_override", sa.JSON(), nullable=True),
        sa.Column("set_by", sa.String(), nullable=False),
        sa.Column("set_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "application_id",
            "requirement_id",
            "control_id",
            name="uq_app_interpretation_scope",
        ),
    )
    op.create_index(
        "ix_app_interpretation_application_id",
        "app_interpretation",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        "ix_app_interpretation_requirement_id",
        "app_interpretation",
        ["requirement_id"],
        unique=False,
    )
    op.create_index(
        "ix_app_interpretation_control_id",
        "app_interpretation",
        ["control_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_app_interpretation_control_id", table_name="app_interpretation")
    op.drop_index("ix_app_interpretation_requirement_id", table_name="app_interpretation")
    op.drop_index("ix_app_interpretation_application_id", table_name="app_interpretation")
    op.drop_table("app_interpretation")
