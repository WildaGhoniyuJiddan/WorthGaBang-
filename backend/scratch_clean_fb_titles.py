"""Script to clean emdash and ufffc search prefixes from RawListing table and fix misclassified categories."""
import sys
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from app.db import SessionLocal
from app.models import RawListing
from app.services.parsing import detect_category, strip_query_prefix
from sqlalchemy import select

def clean_database():
    session = SessionLocal()
    try:
        print("Querying FB listings to clean...", flush=True)
        rows = session.scalars(select(RawListing).where(RawListing.source.in_(('facebook', 'facebook_marketplace')))).all()
        print(f"Total FB listings in DB: {len(rows)}", flush=True)

        updated_titles = 0
        updated_categories = 0
        BATCH_SIZE = 500

        for i, r in enumerate(rows):
            original_title = r.raw_title or ""
            cleaned_title = strip_query_prefix(original_title)

            changed = False
            if cleaned_title != original_title:
                r.raw_title = cleaned_title
                updated_titles += 1
                changed = True

            # Recalculate category using cleaned title
            new_cat = detect_category(cleaned_title, r.raw_spec_text or "")
            if r.category != new_cat:
                r.category = new_cat
                updated_categories += 1
                changed = True

            if changed and (i + 1) % BATCH_SIZE == 0:
                session.commit()
                print(f"Processed {i + 1}/{len(rows)}: {updated_titles} titles cleaned, {updated_categories} categories updated", flush=True)

        session.commit()
        print(f"DONE! Total titles cleaned: {updated_titles}, Total categories updated: {updated_categories}", flush=True)
    finally:
        session.close()

if __name__ == "__main__":
    clean_database()
