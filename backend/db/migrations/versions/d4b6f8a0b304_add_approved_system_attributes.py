"""add_approved_system_attributes

Revision ID: d4b6f8a0b304
Revises: c3a5e7f9a203
Create Date: 2026-04-09 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4b6f8a0b304"
down_revision: Union[str, Sequence[str], None] = "c3a5e7f9a203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    attribute_source = sa.Enum(
        "otel_metric",
        "application_field",
        "calculated",
        name="attribute_source",
    )
    attribute_data_type = sa.Enum(
        "float",
        "integer",
        "ratio",
        "percentage",
        "boolean",
        "string",
        name="attribute_data_type",
    )

    op.create_table(
        "approved_system_attributes",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("attribute_name", sa.String(), nullable=False),
        sa.Column("source", attribute_source, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data_type", attribute_data_type, nullable=False),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("example_value", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("added_by", sa.String(), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("attribute_name", name="uq_approved_system_attributes_name"),
    )
    op.create_index(
        "ix_approved_system_attributes_source",
        "approved_system_attributes",
        ["source"],
        unique=False,
    )
    op.create_index(
        "ix_approved_system_attributes_is_active",
        "approved_system_attributes",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_approved_system_attributes_is_active", table_name="approved_system_attributes")
    op.drop_index("ix_approved_system_attributes_source", table_name="approved_system_attributes")
    op.drop_table("approved_system_attributes")
    op.execute("DROP TYPE IF EXISTS attribute_data_type")
    op.execute("DROP TYPE IF EXISTS attribute_source")
