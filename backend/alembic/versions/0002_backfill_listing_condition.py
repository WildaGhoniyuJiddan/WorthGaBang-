"""Backfill legacy listings as new when no second-hand marker exists.

Revision ID: 0002_backfill_listing_condition
"""
from alembic import op


revision = "0002_backfill_listing_condition"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Before condition filtering existed, a missing marker meant the listing
    # was a normal/new listing. Make that explicit for the new PC UI filter.
    op.execute("UPDATE raw_listings SET condition = 'new' WHERE condition IS NULL")
    op.execute("UPDATE laptop_units SET condition = 'new' WHERE condition IS NULL")


def downgrade() -> None:
    # The original NULL-vs-new distinction was not persisted, so keep the
    # explicit value on downgrade rather than destroying user data.
    pass

