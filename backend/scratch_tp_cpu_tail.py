"""Batch 3: hanya 7 query CPU yang belum kejar (sisa dari batas waktu batch 2)."""
import argparse, csv, json, sys, time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from app.config import get_settings
from app.db import SessionLocal
from app.scrapers.tokopedia import TokopediaScraper
from app.services.ingestion import IngestStats, ingest_listings, listing_input_from_record

QUERIES = ["Core i5 12400", "Core i5 13400", "Core i5 11400", "Core i5 10400",
           "Core i7 12700", "Core i7 13700", "Core i7 11700"]

CSV_FIELDS = ["query", "title", "price", "condition", "condition_source", "seller",
              "is_official_store", "sold_count", "rating", "category", "url", "description"]

def main():
    s = get_settings()
    scraper = TokopediaScraper(timeout=s.scrape_timeout_seconds, pages=3, max_variants=2,
                               max_records=s.tokopedia_max_records, request_delay=1.0,
                               fetch_details=True, max_details=60)
    out = BACKEND / "exports" / "hasil_scrape_tokopedia_pc_20260921_b3.csv"
    fh = out.open("w", newline="", encoding="utf-8-sig")
    w = csv.DictWriter(fh, fieldnames=CSV_FIELDS); w.writeheader()
    tot = IngestStats(); documented = 0
    for i, q in enumerate(QUERIES, 1):
        t0 = time.time()
        try:
            records = scraper.fetch(q)
        except Exception as exc:
            print(f"[{i}/{len(QUERIES)}] {q} GAGAL {str(exc)[:100]}", flush=True); continue
        db = SessionLocal(); st = IngestStats()
        try:
            ingest_listings(db, "tokopedia", [listing_input_from_record(r) for r in records], stats=st)
        finally:
            db.close()
        with_desc = sum(1 for r in records if r.description)
        documented += with_desc
        tot.inserted += st.inserted; tot.enriched += st.enriched; tot.skipped_ex_mining += st.skipped_ex_mining
        for r in records:
            w.writerow({"query": q, "title": r.title, "price": r.price, "condition": r.condition,
                        "condition_source": r.condition_source, "seller": r.seller,
                        "is_official_store": r.is_official_store, "sold_count": r.sold_count,
                        "rating": r.rating, "category": r.category, "url": r.url,
                        "description": (r.description or "").replace("\r\n", " | ").replace("\n", " | ")})
        fh.flush()
        print(f"[{i}/{len(QUERIES)}] {q:<16} dapat={len(records)} baru={st.inserted} perkaya={st.enriched} exmin={st.skipped_ex_mining} desc={with_desc} ({time.time()-t0:.0f}s)", flush=True)
    fh.close()
    print(json.dumps({"baru": tot.inserted, "perkaya": tot.enriched, "ex_mining_dibuang": tot.skipped_ex_mining, "deskripsi_run_ini": documented, "csv": str(out)}), flush=True)

if __name__ == "__main__":
    main()
