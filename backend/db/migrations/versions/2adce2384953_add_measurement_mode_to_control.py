"""add_measurement_mode_to_control

Revision ID: 2adce2384953
Revises: 8be69ee43014
Create Date: 2026-04-05 23:45:29.343914

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2adce2384953'
down_revision: Union[str, Sequence[str], None] = '8be69ee43014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    measurement_mode_enum = sa.Enum(
        'system_calculated', 'hybrid', 'manual',
        name='measurement_mode',
    )
    measurement_mode_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'control',
        sa.Column('measurement_mode', measurement_mode_enum, nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('control', 'measurement_mode')
    op.execute('DROP TYPE IF EXISTS measurement_mode')
