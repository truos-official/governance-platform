"""add_tier_fields_to_application

Revision ID: 604c9ae89643
Revises: a67c0aafee61
Create Date: 2026-04-07 16:36:24.581730

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '604c9ae89643'
down_revision: Union[str, Sequence[str], None] = 'a67c0aafee61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("application", sa.Column("ai_system_type", sa.String(), nullable=False, server_default="GEN"))
    op.add_column("application", sa.Column("decision_type", sa.String(), nullable=False, server_default="advisory"))
    op.add_column("application", sa.Column("autonomy_level", sa.String(), nullable=False, server_default="human_in_the_loop"))
    op.add_column("application", sa.Column("population_breadth", sa.String(), nullable=False, server_default="local"))
    op.add_column("application", sa.Column("affected_populations", sa.String(), nullable=False, server_default="general"))
    op.add_column("application", sa.Column("consent_scope", sa.String(), nullable=False, server_default="tier_aggregate"))
    op.add_column("application", sa.Column("owner_email", sa.String(), nullable=True))
    op.add_column("application", sa.Column("current_tier", sa.String(), nullable=True))


def downgrade() -> None:
    for col in ["ai_system_type", "decision_type", "autonomy_level",
                "population_breadth", "affected_populations",
                "consent_scope", "owner_email", "current_tier"]:
        op.drop_column("application", col)
