"""Phase 0 close (D-0017): job fetch depth and IR cache key, per-key page cap.

Revision ID: 0002_phase0_close
Revises: 0001_initial
Create Date: 2026-10-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_phase0_close"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("fetch_depth", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("ir_cache_key", sa.String(64), nullable=True))
    with op.batch_alter_table("api_keys") as batch:
        batch.add_column(sa.Column("max_pages", sa.Integer(), nullable=False, server_default="10000"))


def downgrade() -> None:
    with op.batch_alter_table("api_keys") as batch:
        batch.drop_column("max_pages")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("ir_cache_key")
        batch.drop_column("fetch_depth")
