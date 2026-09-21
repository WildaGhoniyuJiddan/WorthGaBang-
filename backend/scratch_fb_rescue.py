"""Rescue pass: ingest baris FB CSV yang lolos dari chunk gagal (harga sampah di-buang)."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from app.db import SessionLocal
from app.scrapers.facebook import FacebookMarketplaceScraper
from app.services.ingestion import IngestStats, ingest_listings, listing_input_from_record

MAX_PRICE = 1_000_000_000  # >1 Milyar = spam

def main():
    scraper = FacebookMarketplaceScraper(max_records=100_000)
    records = [r for r in scraper._fetch_from_csv("") if not (r.price and r.price > MAX_PRICE)]
    print(f"records valid: {len(records)}", flush=True)
    st_all = IngestStats()
    CHUNK = 250
    for i in range(0, len(records), CHUNK):
        chunk = records[i:i + CHUNK]
        for attempt in range(4):
            db = SessionLocal()
            try:
                st = IngestStats()
                ingest_listings(db, "facebook", [listing_input_from_record(r) for r in chunk], stats=st)
                db.commit()
                st_all.inserted += st.inserted
                st_all.enriched += st.enriched
                st_all.skipped_ex_mining += st.skipped_ex_mining
                break
            except Exception as exc:
                db.rollback()
                if "deadlock" in str(exc).lower():
                    import time as _t
                    _t.sleep(2 + attempt * 3)
                else:
                    print(f"chunk {i//CHUNK+1} GAGAL: {str(exc)[:160]}", flush=True)
                    break
            finally:
                db.close()
    print(f"RESCUE TOTAL: baru={st_all.inserted} perkaya={st_all.enriched} ex_mining={st_all.skipped_ex_mining}", flush=True)

if __name__ == "__main__":
    main()
