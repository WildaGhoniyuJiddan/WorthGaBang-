"""Ingest CSV facebook_marketplace_*.csv (hasil extension lama) ke DB + CSV export."""
import csv
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from app.db import SessionLocal
from app.scrapers.facebook import FacebookMarketplaceScraper
from app.services.ingestion import IngestStats, ingest_listings, listing_input_from_record

CSV_FIELDS = [
    "query", "title", "price", "condition", "condition_source",
    "seller", "is_official_store", "sold_count", "rating",
    "category", "url", "description",
]

def main():
    scraper = FacebookMarketplaceScraper(max_records=100_000)
    records = scraper._fetch_from_csv("")
    print(f"records (setelah dedup+parse): {len(records)}", flush=True)
    total_new = total_enr = total_ex = 0
    CHUNK = 250
    for i in range(0, len(records), CHUNK):
        chunk = records[i:i + CHUNK]
        for attempt in range(4):
            db = SessionLocal()
            try:
                st = IngestStats()
                ingest_listings(db, "facebook", [listing_input_from_record(r) for r in chunk], stats=st)
                db.commit()
                total_new += st.inserted
                total_enr += st.enriched
                total_ex += st.skipped_ex_mining
                print(f"chunk {i//CHUNK+1}: +{st.inserted} baru, {st.enriched} perkaya, {st.skipped_ex_mining} ex-mining", flush=True)
                break
            except Exception as exc:
                db.rollback()
                if "Deadlock" in str(exc.__class__.__name__) or "deadlock" in str(exc).lower():
                    import time as _t
                    print(f"chunk {i//CHUNK+1}: deadlock, retry {attempt+1}", flush=True)
                    _t.sleep(2 + attempt * 3)
                else:
                    print(f"chunk {i//CHUNK+1}: GAGAL {str(exc)[:200]}", flush=True)
                    break
            finally:
                db.close()
    print(f"TOTAL: baru={total_new} perkaya={total_enr} ex_mining={total_ex}", flush=True)
    # ingest_listings mengembalikan int atau stats tergantung versi; hitung dari DB saja sudah cukup.
    out = BACKEND / "exports" / "hasil_scrape_facebook_20260824.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in records:
            w.writerow({
                "query": "csv_backfill", "title": r.title, "price": r.price,
                "condition": r.condition, "condition_source": r.condition_source,
                "seller": r.seller, "is_official_store": r.is_official_store,
                "sold_count": r.sold_count, "rating": r.rating,
                "category": r.category, "url": r.url,
                "description": (r.description or "").replace("\r\n", " | ").replace("\n", " | "),
            })
    print(f"CSV -> {out} ({len(records)} baris)")

if __name__ == "__main__":
    main()
