"""Mobile API tables (WorthBang Android): users, refresh_tokens, wishlist,
price alerts, stores, feedback; extend analysis_logs for per-user history.

Revision ID: 0004_mobile_api
Revises: 0003_listing_quality
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_mobile_api"
down_revision = "0003_listing_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)

    op.create_table(
        "wishlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="pc"),
        sa.Column("target_price", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_wishlist_items_user_id", "wishlist_items", ["user_id"])
    op.create_index("ix_wishlist_user_created", "wishlist_items", ["user_id", "created_at"])

    op.create_table(
        "price_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="pc"),
        sa.Column("component_type", sa.String(length=32), nullable=True),
        sa.Column("target_price", sa.Integer(), nullable=False),
        sa.Column("condition", sa.String(length=16), nullable=False, server_default="any"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_price_alerts_user_id", "price_alerts", ["user_id"])
    op.create_index("ix_alerts_user_active", "price_alerts", ["user_id", "is_active"])

    op.create_table(
        "stores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=False, server_default="Jakarta"),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("prices_json", sa.Text(), nullable=True),
    )
    op.create_index("ix_stores_city", "stores", ["city"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("kesan", sa.Text(), nullable=True),
        sa.Column("saran", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_feedback_user_id", "feedback", ["user_id"])

    # Per-user history attribution on the existing analysis log (nullable, no FK:
    # SQLite can't ALTER constraints, and the join is never needed server-side).
    op.add_column("analysis_logs", sa.Column("user_id", sa.Integer(), nullable=True))
    op.add_column("analysis_logs", sa.Column("input_price", sa.Integer(), nullable=True))
    op.add_column("analysis_logs", sa.Column("verdict", sa.String(length=32), nullable=True))
    op.create_index("ix_analysis_logs_user_id", "analysis_logs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_analysis_logs_user_id", table_name="analysis_logs")
    op.drop_column("analysis_logs", "verdict")
    op.drop_column("analysis_logs", "input_price")
    op.drop_column("analysis_logs", "user_id")
    op.drop_index("ix_feedback_user_id", table_name="feedback")
    op.drop_table("feedback")
    op.drop_index("ix_stores_city", table_name="stores")
    op.drop_table("stores")
    op.drop_index("ix_alerts_user_active", table_name="price_alerts")
    op.drop_index("ix_price_alerts_user_id", table_name="price_alerts")
    op.drop_table("price_alerts")
    op.drop_index("ix_wishlist_user_created", table_name="wishlist_items")
    op.drop_index("ix_wishlist_items_user_id", table_name="wishlist_items")
    op.drop_table("wishlist_items")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
