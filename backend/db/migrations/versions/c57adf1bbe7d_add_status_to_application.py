"""add_status_to_application

Revision ID: c57adf1bbe7d
Revises: d840a883f822
Create Date: 2026-04-07 23:13:39.318668

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c57adf1bbe7d'
down_revision: Union[str, Sequence[str], None] = 'd840a883f822'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("application",
        sa.Column("status", sa.String(), nullable=False, server_default="active")
        # active | suspended | disconnected
    )


def downgrade() -> None:
    op.drop_column("application", "status")
