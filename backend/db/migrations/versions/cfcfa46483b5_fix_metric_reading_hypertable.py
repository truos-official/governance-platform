"""fix_metric_reading_hypertable

Revision ID: cfcfa46483b5
Revises: e41e5a46df95
Create Date: 2026-04-03 19:08:01.083170

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'cfcfa46483b5'
down_revision: Union[str, Sequence[str], None] = 'e41e5a46df95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Change collected_at to TIMESTAMPTZ
    op.alter_column('metric_reading', 'collected_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=False)
    # Change metric_name from VARCHAR to Text
    op.alter_column('metric_reading', 'metric_name',
               existing_type=sa.VARCHAR(),
               type_=sa.Text(),
               existing_nullable=False)
    # Rebuild primary key as composite (id, collected_at) — required by TimescaleDB
    op.drop_constraint('metric_reading_pkey', 'metric_reading', type_='primary')
    op.create_primary_key('metric_reading_pkey', 'metric_reading', ['id', 'collected_at'])


def downgrade() -> None:
    """Downgrade schema."""
    # Restore single-column primary key
    op.drop_constraint('metric_reading_pkey', 'metric_reading', type_='primary')
    op.create_primary_key('metric_reading_pkey', 'metric_reading', ['id'])
    op.alter_column('metric_reading', 'metric_name',
               existing_type=sa.Text(),
               type_=sa.VARCHAR(),
               existing_nullable=False)
    op.alter_column('metric_reading', 'collected_at',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=False)
