"""
Batch Scraper Jobs for WorL Project
====================================
Workflow WAJIB (diputuskan user 2026-10-07): SCRAPE -> LOKAL -> BERSIH -> UPLOAD.

1. Scrape disimpan mentah ke `local_scratch/scraped_raw/*.json`
2. Diproses/divalidasi ke `local_scratch/processed_batch/*_processed.json`
3. Upload ke Supabase HANYA lewat `upload_pending()` — langkah eksplisit terpisah,
   tidak pernah jalan otomatis di akhir scrape.

Alasan: Supabase Free plan punya kuota egress 5 GB; data yang belum bersih
tidak boleh memakan kuota, dan tiap baris buruk harus bisa dibuang di lokal.
"""
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session


# Local directories (not in git)
LOCAL_DIR = Path(__file__).parent / "local_scratch"
SCRAPED_DIR = LOCAL_DIR / "scraped_raw"
PROCESSED_DIR = LOCAL_DIR / "processed_batch"
LOGS_DIR = LOCAL_DIR / "logs"


UPLOADED_DIR = LOCAL_DIR / "uploaded"


def save_local(source: str, query: str, records: list) -> Path:
    """Save raw scraped JSON locally with timestamp."""
    SCRAPED_DIR.mkdir(parents=True, exist_ok=True)

    # Scraper menghasilkan ListingRecord (dataclass) — simpan sebagai dict.
    records = [asdict(r) if is_dataclass(r) else r for r in records]

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_q = query.replace("/", "_").replace("\\", "_")[:40]
    filename = f"{source}_{safe_q}_{ts}.json"
    filepath = SCRAPED_DIR / filename
    
    data = {
        "source": source,
        "query": query,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "records": records
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    LOGS_DIR.mkdir(exist_ok=True)
    log_entry = {"action": "save_local", "filename": filename, "size_bytes": filepath.stat().st_size}
    with open(LOGS_DIR / "scratch.log", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    print(f"[{source}] Saved locally: {len(records)} records → {filepath.name}")
    return filepath


def process_batch_records(filepath: Path) -> tuple[list[dict], int]:
    """Process raw JSON, validate & clean data."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    processed = []
    skipped = 0
    
    for record in data.get("records", []):
        # Validation
        if not record.get("title"):
            skipped += 1
            continue
        
        title = (record.get("title") or "")[:500]
        spec_text = (record.get("spec_text") or "")[:1000]
        
        try:
            price = int(record.get("price", 0))
            if price <= 0:
                skipped += 1
                continue
        except (ValueError, TypeError):
            skipped += 1
            continue
        
        category = data.get("source", "").split("_")[0]
        
        processed.append({
            "raw_title": title,
            "raw_price": price,
            "raw_spec_text": spec_text,
            "category": category,
            "condition": record.get("condition", "new"),
            "url": record.get("url"),
            "seller": record.get("seller"),
            # Field kualitas — jangan dibuang: dipakai ingest untuk tolak
            # ex-mining dan menilai toko aktif.
            "description": record.get("description"),
            "is_official_store": record.get("is_official_store"),
            "sold_count": record.get("sold_count"),
            "rating": record.get("rating"),
            "condition_source": record.get("condition_source"),
            "scraped_at": data.get("scraped_at"),
            "source": data.get("source")
        })
    
    # Save processed locally too
    PROCESSED_DIR.mkdir(exist_ok=True)
    base_filename = filepath.stem
    processed_filepath = PROCESSED_DIR / f"{base_filename}_processed.json"
    
    with open(processed_filepath, "w", encoding="utf-8") as f:
        json.dump({
            "batch_id": base_filename,
            "source": data.get("source"),
            "scraped_at": data.get("scraped_at"),
            "total_processed": len(processed),
            "skipped": skipped,
            "records": processed
        }, f, ensure_ascii=False, indent=2)
    
    print(f"[{data['source']}] Processed: {len(processed)}, Skipped: {skipped}")
    return processed, skipped


def upload_pending() -> dict:
    """Upload batch yang SUDAH diproses ke Supabase — langkah eksplisit.

    Dipanggil terpisah setelah data lokal diperiksa; tidak pernah jalan
    otomatis sesudah scrape. Jalur insert memakai `ingest_listings` (hash
    dedupe + gerbang kualitas), bukan REST supabase-py.
    """
    from .db import SessionLocal
    from .services.ingestion import IngestStats, ListingInput, ingest_listings

    summary = {"files": 0, "inserted": 0, "enriched": 0,
               "duplicate": 0, "rejected": 0}
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADED_DIR.mkdir(parents=True, exist_ok=True)

    db: Session = SessionLocal()
    try:
        for path in sorted(PROCESSED_DIR.glob("*_processed.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            source = data.get("source") or path.stem.split("_")[0]
            if source == "facebook_marketplace":
                source = "facebook"  # nama kolom raw_listings.source
            items = [
                ListingInput(
                    title=r.get("raw_title") or "",
                    price=r.get("raw_price"),
                    url=r.get("url"),
                    spec_text=r.get("raw_spec_text"),
                    category=r.get("category"),
                    condition=r.get("condition"),
                    description=r.get("description"),
                    seller=r.get("seller"),
                    is_official_store=r.get("is_official_store"),
                    sold_count=r.get("sold_count"),
                    rating=r.get("rating"),
                    condition_source=r.get("condition_source"),
                    scraped_at=datetime.fromisoformat(r["scraped_at"])
                    if r.get("scraped_at") else None,
                )
                for r in data.get("records", [])
            ]
            stats = IngestStats()
            if items:
                ingest_listings(db, source, items, stats=stats)

            path.rename(UPLOADED_DIR / path.name)
            summary["files"] += 1
            summary["inserted"] += stats.inserted
            summary["enriched"] += stats.enriched
            summary["duplicate"] += stats.skipped_duplicate
            summary["rejected"] += stats.skipped_ex_mining + stats.skipped_other
            print(f"[{source}] {path.name}: +{stats.inserted} baru, "
                  f"{stats.skipped_duplicate} duplikat, "
                  f"{stats.skipped_ex_mining + stats.skipped_other} dibuang")
    finally:
        db.close()

    LOGS_DIR.mkdir(exist_ok=True)
    with open(LOGS_DIR / "upload.log", "a") as f:
        f.write(json.dumps({**summary, "action": "upload_pending",
                            "timestamp": datetime.now(timezone.utc).isoformat()}) + "\n")
    print(f"Upload selesai: {summary}")
    return summary


def run_source_batch(
    source: str,
    query: str,
    schedule: str = "manual",
    is_fallback: bool = False,
) -> Optional["ScrapeRun"]:
    """Scrape → save local → process. TANPA upload (upload = langkah terpisah)."""
    from .db import SessionLocal
    from .models import ScrapeRun
    from .config import get_settings
    from .scrapers import TokopediaScraper, FacebookMarketplaceScraper
    
    db: Session = SessionLocal()
    run = ScrapeRun(source=source, schedule=schedule, status="running", is_fallback=is_fallback)
    db.add(run)
    db.commit()
    
    try:
        # Create scraper based on source
        settings = get_settings()
        timeout = settings.scrape_timeout_seconds
        
        if source == "tokopedia":
            scraper = TokopediaScraper(
                timeout=timeout,
                pages=settings.tokopedia_pages,
                max_variants=settings.tokopedia_query_variants,
                max_records=settings.tokopedia_max_records,
                request_delay=settings.tokopedia_request_delay_seconds,
            )
        elif source == "facebook_marketplace":
            scraper = FacebookMarketplaceScraper(
                cookie=settings.facebook_cookie,
                timeout=timeout
            )
        else:
            raise ValueError(f"Unsupported source: {source}")
        
        # Step 1: Scrape
        print(f"\n=== Scraping: {source} - '{query}' ===")
        records = scraper.fetch(query)
        
        if not records:
            run.status = "success"
            run.item_count = 0
            db.commit()
            db.close()
            return run
        
        # Step 2: Save raw locally
        filepath = save_local(source, query, records)
        
        # Step 3: Process & validate
        processed_records, skipped = process_batch_records(filepath)
        
        # Step 4: JANGAN upload di sini — data harus diperiksa dulu di lokal.
        # Upload terpisah: python -m app.batch_jobs upload
        # Update run record
        run.status = "success"
        run.item_count = len(processed_records)
        if skipped > 0:
            run.error_message = f"invalid records: {skipped}"
        
        db.commit()
        return run
        
    except Exception as exc:
        db.rollback()
        run = db.merge(run)
        run.status = "failed"
        run.error_message = str(exc)[:2000]
        db.commit()
        db.close()
        raise
        
    finally:
        db.close()


def run_cycle_batch(query: str | None = None) -> dict:
    """Run batch cycle for all sources."""
    from .config import get_settings
    
    query = query or get_settings().query_list[0]
    result = {"query": query, "runs": [], "fallback_source": None}
    
    for source in ("tokopedia", "facebook_marketplace"):
        run = run_source_batch(source, query, schedule="manual")
        if run:
            result["runs"].append({
                "source": run.source,
                "status": run.status,
                "item_count": run.item_count,
                "error_message": run.error_message
            })
    
    print(f"\n📊 Batch Cycle Result: {result}")
    return result


if __name__ == "__main__":
    """CLI: `python -m app.batch_jobs` (scrape+proses ke lokal) | `... upload`."""
    import sys

    cmd = "scrape"
    args = sys.argv[1:]
    if args and args[0] in ("upload", "status"):
        cmd = args.pop(0)
    elif args and args[0] == "scrape":
        args.pop(0)

    if cmd == "upload":
        # Langkah upload — hanya dipanggil setelah data lokal diperiksa.
        print(json.dumps(upload_pending(), indent=2))
    elif cmd == "status":
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        pending = sorted(PROCESSED_DIR.glob("*_processed.json"))
        raw = sorted(SCRAPED_DIR.glob("*.json")) if SCRAPED_DIR.exists() else []
        print(json.dumps({
            "raw_files": len(raw),
            "pending_upload": [p.name for p in pending],
        }, indent=2))
    else:
        query = args[0] if args else "RTX 4060"
        print("=" * 60)
        print(f"BATCH SCRAPE (lokal saja): {query}")
        print("=" * 60)
        result = run_cycle_batch(query=query)
        print(json.dumps(result, indent=2, default=str))
        print("\nData lokal: backend/app/local_scratch/")
        print("Upload setelah dicek: python -m app.batch_jobs upload")
