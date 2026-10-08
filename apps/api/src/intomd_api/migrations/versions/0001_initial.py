"""Initial schema: jobs and api_keys (docs/spec/part1.md section 7.1).

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("input_kind", sa.String(32), nullable=False),
        sa.Column("input_display", sa.Text(), nullable=False),
        sa.Column("input_url", sa.Text(), nullable=True),
        sa.Column("input_size", sa.Integer(), nullable=True),
        sa.Column("input_sha256", sa.String(64), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("content_hash", sa.String(128), nullable=True),
        sa.Column("mime", sa.String(255), nullable=True),
        sa.Column("declared_mime", sa.String(255), nullable=True),
        sa.Column("converter_id", sa.String(128), nullable=True),
        sa.Column("profile", sa.String(32), nullable=False),
        sa.Column("options_json", sa.Text(), nullable=False),
        sa.Column("queue", sa.String(32), nullable=False),
        sa.Column("rq_job_id", sa.String(64), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("stage_message", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("needs_action", sa.Text(), nullable=True),
        sa.Column("blob_input", sa.Text(), nullable=True),
        sa.Column("blob_ir", sa.Text(), nullable=True),
        sa.Column("blob_result_prefix", sa.Text(), nullable=True),
        sa.Column("api_key_id", sa.String(64), nullable=True),
        sa.Column("client_ip_hash", sa.String(64), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=True),
        sa.Column("warnings_count", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("claim_token_hash", sa.String(64), nullable=True),
        sa.Column("claim_node_id", sa.String(128), nullable=True),
        sa.Column("claim_expires_at", TS, nullable=True),
        sa.Column("claim_attempts", sa.Integer(), nullable=False),
    )
    for col in (
        "state",
        "expires_at",
        "input_sha256",
        "idempotency_key",
        "api_key_id",
        "client_ip_hash",
        "claim_token_hash",
    ):
        op.create_index(f"ix_jobs_{col}", "jobs", [col])
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("revoked_at", TS, nullable=True),
        sa.Column("expires_at", TS, nullable=True),
        sa.Column("unlimited", sa.Boolean(), nullable=False),
        sa.Column("requests_per_minute", sa.Integer(), nullable=False),
        sa.Column("requests_per_day", sa.Integer(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("max_upload_bytes", sa.Integer(), nullable=False),
        sa.Column("max_audio_seconds", sa.Integer(), nullable=False),
        sa.Column("allowed_families", sa.Text(), nullable=False),
        sa.Column("residential_allowed", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("api_keys")
    op.drop_table("jobs")
