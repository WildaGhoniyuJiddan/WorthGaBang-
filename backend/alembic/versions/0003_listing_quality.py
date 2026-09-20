"""Add listing quality columns: description, seller, store signals.

Revision ID: 0003_listing_quality
Revises: 0002_backfill_listing_condition
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_listing_quality"
down_revision = "0002_backfill_listing_condition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Deskripsi produk — dipakai untuk mendeteksi kondisi asli ("like new",
    # "pemakaian 1 tahun") dan menolak listing "ex mining".
    op.add_column("raw_listings", sa.Column("description", sa.Text(), nullable=True))
    # Identitas & aktivitas toko, dipakai memisahkan tokopedia_baru vs
    # tokopedia_bekas dan mendeteksi toko yang sudah tidak aktif.
    op.add_column("raw_listings", sa.Column("seller", sa.String(length=255), nullable=True))
    op.add_column("raw_listings", sa.Column("is_official_store", sa.Boolean(), nullable=True))
    op.add_column("raw_listings", sa.Column("sold_count", sa.Integer(), nullable=True))
    op.add_column("raw_listings", sa.Column("rating", sa.Float(), nullable=True))
    op.add_column("raw_listings", sa.Column("condition_source", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_listings", "condition_source")
    op.drop_column("raw_listings", "rating")
    op.drop_column("raw_listings", "sold_count")
    op.drop_column("raw_listings", "is_official_store")
    op.drop_column("raw_listings", "seller")
    op.drop_column("raw_listings", "description")
