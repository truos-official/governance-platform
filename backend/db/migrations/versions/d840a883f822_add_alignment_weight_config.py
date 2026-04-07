"""add_alignment_weight_config

Revision ID: d840a883f822
Revises: b1714efabb4e
Create Date: 2026-04-07 21:35:33.779305

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd840a883f822'
down_revision: Union[str, Sequence[str], None] = 'b1714efabb4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alignment_weight_config",
        sa.Column("id",                 sa.UUID(),     primary_key=True),
        sa.Column("peer_adoption_rate", sa.Float(),    nullable=False),
        sa.Column("regulatory_density", sa.Float(),    nullable=False),
        sa.Column("trend_velocity",     sa.Float(),    nullable=False),
        sa.Column("set_by",             sa.String(),   nullable=False),
        sa.Column("set_at",             sa.DateTime(), nullable=False),
        sa.Column("reason",             sa.Text(),     nullable=True),
        sa.Column("is_active",          sa.Boolean(),  nullable=False, server_default="true"),
    )
    op.execute("""
        INSERT INTO alignment_weight_config
            (id, peer_adoption_rate, regulatory_density, trend_velocity,
             set_by, set_at, reason, is_active)
        VALUES
            (gen_random_uuid(), 0.50, 0.30, 0.20,
             'system', NOW(), 'System default per specification', true)
    """)


def downgrade() -> None:
    op.drop_table("alignment_weight_config")
