"""add_control_assignment

Revision ID: b1714efabb4e
Revises: 604c9ae89643
Create Date: 2026-04-07 17:10:04.211882

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1714efabb4e'
down_revision: Union[str, Sequence[str], None] = '604c9ae89643'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "control_assignment",
        sa.Column("id",             sa.UUID(),     primary_key=True),
        sa.Column("application_id", sa.UUID(),     sa.ForeignKey("application.id"), nullable=False),
        sa.Column("control_id",     sa.UUID(),     sa.ForeignKey("control.id"),     nullable=False),
        sa.Column("status",         sa.String(),   nullable=False, server_default="pending"),
        sa.Column("assigned_at",    sa.DateTime(), nullable=False),
        sa.UniqueConstraint("application_id", "control_id", name="uq_control_assignment"),
    )


def downgrade() -> None:
    op.drop_table("control_assignment")
