"""Create HargaPas catalog and analysis tables.

Revision ID: 0001_initial
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("raw_title", sa.Text(), nullable=False),
        sa.Column("raw_price", sa.Integer(), nullable=True),
        sa.Column("raw_spec_text", sa.Text(), nullable=True),
        sa.Column("listing_url", sa.Text(), nullable=True),
        sa.Column("listing_hash", sa.String(length=64), nullable=False),
        sa.Column("condition", sa.String(length=32), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("listing_hash", name="uq_raw_listings_hash"),
    )
    op.create_index("ix_raw_listings_source", "raw_listings", ["source"])
    op.create_index("ix_raw_listings_category", "raw_listings", ["category"])
    op.create_index("ix_raw_listings_scraped_at", "raw_listings", ["scraped_at"])
    op.create_index("ix_raw_listings_source_category", "raw_listings", ["source", "category"])

    op.create_table(
        "pc_components",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("component_type", sa.String(length=32), nullable=False),
        sa.Column("brand", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("benchmark_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("component_type", "brand", "model", name="uq_pc_component_identity"),
    )
    op.create_index("ix_pc_components_component_type", "pc_components", ["component_type"])
    op.create_index("ix_pc_components_lookup", "pc_components", ["component_type", "brand", "model"])

    op.create_table(
        "laptop_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("raw_listing_id", sa.Integer(), sa.ForeignKey("raw_listings.id"), nullable=False),
        sa.Column("brand", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("cpu", sa.String(length=128), nullable=True),
        sa.Column("gpu", sa.String(length=128), nullable=True),
        sa.Column("ram_gb", sa.Integer(), nullable=True),
        sa.Column("storage_gb", sa.Integer(), nullable=True),
        sa.Column("screen_size", sa.Float(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("condition", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("listing_url", sa.Text(), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_laptop_units_raw_listing_id", "laptop_units", ["raw_listing_id"])
    op.create_index("ix_laptop_units_source", "laptop_units", ["source"])
    op.create_index("ix_laptop_units_specs", "laptop_units", ["brand", "cpu", "gpu", "ram_gb", "storage_gb"])
    op.create_index("ix_laptop_units_scraped_at", "laptop_units", ["scraped_at"])

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("schedule", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_scrape_runs_source", "scrape_runs", ["source"])
    op.create_index("ix_scrape_runs_status", "scrape_runs", ["status"])
    op.create_index("ix_scrape_runs_source_started", "scrape_runs", ["source", "started_at"])

    op.create_table(
        "analysis_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("input_query", sa.Text(), nullable=False),
        sa.Column("result_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_analysis_logs_mode", "analysis_logs", ["mode"])
    op.create_index("ix_analysis_logs_created_at", "analysis_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("analysis_logs")
    op.drop_table("scrape_runs")
    op.drop_table("laptop_units")
    op.drop_table("pc_components")
    op.drop_table("raw_listings")

