"""add_measure_formula

Revision ID: e5c7a9b1c405
Revises: d4b6f8a0b304
Create Date: 2026-04-09 12:33:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5c7a9b1c405"
down_revision: Union[str, Sequence[str], None] = "d4b6f8a0b304"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "measure_formula",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "control_metric_definition_id",
            sa.UUID(),
            sa.ForeignKey("control_metric_definition.id"),
            nullable=False,
        ),
        sa.Column("field_picker", sa.String(), nullable=False),
        sa.Column("operator", sa.String(), nullable=False),
        sa.Column("window", sa.String(), nullable=False),
        sa.Column("aggregation", sa.String(), nullable=False),
        sa.Column("expression_preview", sa.Text(), nullable=False),
        sa.Column("interpretation_template", sa.Text(), nullable=False),
        sa.Column("interpretation_generated", sa.Text(), nullable=True),
        sa.Column("interpretation_approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_measure_formula_control_metric_definition_id",
        "measure_formula",
        ["control_metric_definition_id"],
        unique=False,
    )
    op.create_index(
        "ix_measure_formula_field_picker",
        "measure_formula",
        ["field_picker"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_measure_formula_field_picker", table_name="measure_formula")
    op.drop_index(
        "ix_measure_formula_control_metric_definition_id",
        table_name="measure_formula",
    )
    op.drop_table("measure_formula")
