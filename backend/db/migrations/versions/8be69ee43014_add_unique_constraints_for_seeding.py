"""add_unique_constraints_for_seeding

Revision ID: 8be69ee43014
Revises: cfcfa46483b5
Create Date: 2026-04-05 23:44:00.997118

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8be69ee43014'
down_revision: Union[str, Sequence[str], None] = 'cfcfa46483b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index('metric_reading_collected_at_idx', table_name='metric_reading')
    op.create_unique_constraint('uq_requirement_code', 'requirement', ['code'])
    op.create_unique_constraint(
        'uq_control_metric_definition_control_metric',
        'control_metric_definition',
        ['control_id', 'metric_name'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_control_metric_definition_control_metric', 'control_metric_definition', type_='unique')
    op.drop_constraint('uq_requirement_code', 'requirement', type_='unique')
    op.create_index('metric_reading_collected_at_idx', 'metric_reading', [sa.text('collected_at DESC')], unique=False)
