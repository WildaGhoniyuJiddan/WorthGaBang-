"""
Batch Scraper Jobs for WorL Project
====================================
Mengurangi egress Supabase dengan:
1. Scraping data lokal (JSON)
2. Processing & cleaning data
3. Upload 1 batch ke Supabase

Benefits:
- Egress turun ~90% (1 upload vs streaming thousands of rows)
- Data quality lebih baik (validasi sebelum insert)
- Backup lokal untuk audit trail
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from supabase import create_client, Client
from sqlalchemy.orm import Session


# Local directories (not in git)
LOCAL_DIR = Path(__file__).parent / "local_scratch"
SCRAPED_DIR = LOCAL_DIR / "scraped_raw"
PROCESSED_DIR = LOCAL_DIR / "processed_batch"
LOGS_DIR = LOCAL_DIR / "logs"


def init_supabase() -> Client:
    """Initialize Supabase client with service role key."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def save_local(source: str, query: str, records: list) -> Path:
    """Save raw scraped JSON locally with timestamp."""
    SCRAPED_DIR.mkdir(parents=True, exist_ok=True)
    
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_q = query.replace("/", "_").replace("\\", "_")[:40]
    filename = f"{source}_{safe_q}_{ts}.json"
    filepath = SCRAPPED_DIR / filename
    
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
        
        title = record.get("title", "")[:500]
        spec_text = record.get("spec_text", "")[:1000]
        
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
            "total_processed": len(processed),
            "skipped": skipped,
            "records": processed
        }, f, ensure_ascii=False, indent=2)
    
    print(f"[{data['source']}] Processed: {len(processed)}, Skipped: {skipped}")
    return processed, skipped


def upload_to_supabase(processed_records: list[dict]):
    """Upload entire batch to Supabase in ONE operation."""
    supabase = init_supabase()
    result = supabase.table("raw_listings").insert(processed_records).execute()
    return result


def run_source_batch(
    source: str,
    query: str,
    schedule: str = "manual",
    is_fallback: bool = False,
) -> Optional["ScrapeRun"]:
    """Scrape → save local → process → upload (single batch operation)."""
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
        
        # Step 4: Upload single batch to Supabase
        if processed_records:
            upload_to_supabase(processed_records)
        
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
    """Test batch scraper manually."""
    print("=" * 60)
    print("TEST BATCH SCRAPER")
    print("=" * 60)
    
    result = run_cycle_batch(query="RTX 4060")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(json.dumps(result, indent=2, default=str))
    
    print(f"\n✅ Batch scraper test complete!")
    print(f"Check local files at: backend/app/local_scratch/")
