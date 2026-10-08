"""P1-T10: per-job warning codes (JobOut.warnings, deferred by D-0017).

Revision ID: 0003_job_warning_codes
Revises: 0002_phase0_close
Create Date: 2026-10-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_job_warning_codes"
down_revision = "0002_phase0_close"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("warning_codes", sa.Text(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("warning_codes")
