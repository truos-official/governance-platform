"""extend_application_requirement

Revision ID: a1d3e5f7b901
Revises: f2a1b6cd9e77
Create Date: 2026-04-09 12:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1d3e5f7b901"
down_revision: Union[str, Sequence[str], None] = "f2a1b6cd9e77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "application_requirement",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "application_requirement",
        sa.Column("added_by", sa.String(), nullable=True),
    )
    op.add_column(
        "application_requirement",
        sa.Column("added_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.execute(
        """
        UPDATE application_requirement
        SET added_at = COALESCE(selected_at, added_at)
        """
    )


def downgrade() -> None:
    op.drop_column("application_requirement", "added_at")
    op.drop_column("application_requirement", "added_by")
    op.drop_column("application_requirement", "is_default")
