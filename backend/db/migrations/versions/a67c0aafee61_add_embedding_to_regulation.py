"""add_embedding_to_regulation

Revision ID: a67c0aafee61
Revises: 2adce2384953
Create Date: 2026-04-06 12:18:31.191213

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'a67c0aafee61'
down_revision: Union[str, Sequence[str], None] = '2adce2384953'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("regulation",
        sa.Column("embedding", Vector(3072), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("regulation", "embedding")
