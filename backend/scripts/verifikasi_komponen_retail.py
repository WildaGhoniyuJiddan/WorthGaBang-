# Verifikasi end-to-end: scrape real komponen retail -> DB -> anchor harga baru.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.jobs import run_source
from app.models import RawListing
from app.services.analysis import new_price_anchor
from sqlalchemy import select

run = run_source("komponen_retail", "rtx 3060", schedule="manual")
print(f"ScrapeRun: status={run.status} inserted={run.item_count} err={run.error_message}")

with SessionLocal() as db:
    rows = db.scalars(
        select(RawListing)
        .where(RawListing.source == "komponen_retail")
        .order_by(RawListing.id.desc())
        .limit(5)
    ).all()
    print(f"\n{len(rows)} listing terakhir dari komponen_retail di DB:")
    for r in rows:
        print(f"  [{r.category}] {r.raw_title[:70]} = Rp{r.raw_price:,}")

print()
for q in ["RTX 3060", "rx 6600", "ryzen 5 5600", "core i5 12400"]:
    a = new_price_anchor(q)
    print(f"anchor('{q}') = {a:,}" if a else f"anchor('{q}') = None")
