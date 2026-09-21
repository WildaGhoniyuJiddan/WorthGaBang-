"""Purge raw_listings yang ternyata lolos filter ex-mining (aturan baru),
lalu recompute agregat pc_components yang terdampak.
Egress hemat: hanya ambil baris berisi 'mining'/'cmp' (~ratusan), bukan semua.
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select, text

from app.config import get_settings
from app.db import SessionLocal
from app.models import PCComponent, RawListing
from app.services.listing_quality import assess_listing
from app.services.normalizer import normalize_listing


def main():
    db = SessionLocal()
    rows = db.execute(
        text(
            "SELECT id FROM raw_listings "
            "WHERE lower(raw_title) LIKE '%mining%' OR lower(COALESCE(description,'')) LIKE '%mining%' "
            "OR lower(raw_title) LIKE '%cmp%hx%' OR lower(COALESCE(description,'')) LIKE '%cmp%hx%'"
        )
    ).scalars().all()
    print(f"baris kandidat (mengandung mining/cmp-hx): {len(rows)}")

    to_delete = []
    affected_pc_ids = set()
    for rid in rows:
        raw = db.get(RawListing, rid)
        if raw is None:
            continue
        verdict = assess_listing(raw.raw_title, raw.description, raw.raw_spec_text)
        if not verdict.is_acceptable and verdict.is_ex_mining:
            to_delete.append(raw.id)
            if raw.category == "pc":
                affected_pc_ids.add(raw.id)
    print(f"akan dibuang (ex-mining per aturan baru): {len(to_delete)}")
    if "--dry" in sys.argv:
        for i, rid in enumerate(to_delete[:20]):
            r = db.get(RawListing, rid)
            print("  -", rid, r.source, "|", r.raw_title[:70])
        return

    CHUNK = 200
    for i in range(0, len(to_delete), CHUNK):
        ids = to_delete[i:i + CHUNK]
        db.query(RawListing).filter(RawListing.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        print(f"  delete {min(i+CHUNK, len(to_delete))}/{len(to_delete)}", flush=True)

    comps = db.scalars(select(PCComponent)).all()
    print(f"recompute {len(comps)} baris pc_components...")
    sample = db.scalars(
        select(RawListing).where(RawListing.category == "pc", RawListing.raw_price.is_not(None)).limit(1)
    ).all()
    # pancing recompute total: normalize satu row pc -> avg dihitung ulang dari SEMUA row pc
    if sample:
        normalize_listing(db, sample[0])
        db.commit()
    db.close()
    print("PURGE SELESAI")


if __name__ == "__main__":
    get_settings()
    main()
