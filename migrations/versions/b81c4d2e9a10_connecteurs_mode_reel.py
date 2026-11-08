"""v1.3 mode réel des connecteurs : environnement, correspondance, délai, coupe-circuit

Revision ID: b81c4d2e9a10
Revises: f7895d3f3004
Create Date: 2026-11-08 07:10:00
"""
from alembic import op
import sqlalchemy as sa

revision = "b81c4d2e9a10"
down_revision = "f7895d3f3004"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("connector") as b:
        b.add_column(sa.Column("environment", sa.String(10), nullable=False, server_default="recette"))
        b.add_column(sa.Column("mapping", sa.Text(), nullable=True))
        b.add_column(sa.Column("timeout_s", sa.Integer(), nullable=False, server_default="5"))
        b.add_column(sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"))
        b.add_column(sa.Column("open_until", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("last_ok_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("last_error", sa.String(160), nullable=True))


def downgrade():
    with op.batch_alter_table("connector") as b:
        for col in ("last_error", "last_ok_at", "open_until", "fail_count", "timeout_s", "mapping", "environment"):
            b.drop_column(col)
