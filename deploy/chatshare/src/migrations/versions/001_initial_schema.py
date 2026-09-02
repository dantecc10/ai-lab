"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chats",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("messages", sa.Text, nullable=False, server_default="[]"),
        sa.Column("metadata", sa.Text, server_default="{}"),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("current_version", sa.Integer, server_default="1"),
        sa.Column("is_deleted", sa.Boolean, server_default="0"),
        sa.Column("is_dirty", sa.Boolean, server_default="1"),
        sa.Column("remote_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("last_synced_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "chat_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("chat_id", sa.String(36), sa.ForeignKey("chats.id"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("messages", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("is_current", sa.Boolean, server_default="0"),
    )

    op.create_table(
        "chat_branches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("chat_id", sa.String(36), sa.ForeignKey("chats.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("source_branch_id", sa.String(36), sa.ForeignKey("chat_branches.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "access_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("chat_id", sa.String(36), sa.ForeignKey("chats.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("max_views", sa.Integer, nullable=True),
        sa.Column("view_count", sa.Integer, server_default="0"),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("is_revoked", sa.Boolean, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "sync_queue",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("operation", sa.String(10), nullable=False),
        sa.Column("table_name", sa.String(50), nullable=False),
        sa.Column("record_id", sa.String(36), nullable=False),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("attempt_count", sa.Integer, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("sync_queue")
    op.drop_table("access_tokens")
    op.drop_table("chat_branches")
    op.drop_table("chat_versions")
    op.drop_table("chats")
