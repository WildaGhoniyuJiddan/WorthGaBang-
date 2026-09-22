"""
Batch scraper pipeline for WorL project.
Scrapes data locally first, processes it, then uploads to Supabase.
This reduces egress and allows better data validation before insertion.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Setup Supabase client for batch upload only
from supabase import create_client, Client

# Local directories
LOCAL_DIR = Path(__file__).parent / "local_scratch"
SCRAPED_DIR = LOCAL_DIR / "scraped_raw"
PROCESSED_DIR = LOCAL_DIR / "processed_batch"
LOGS_DIR = LOCAL_DIR / "logs"


def init_supabase() -> Client:
    """Initialize Supabase client with service role key."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def save_scraped_data(source: str, query: str, records: list, metadata: dict = None) -> Path:
    """Save scraped raw data locally with timestamp."""
    SCRAPED_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_query = query.replace("/", "_").replace("\\", "_")[:40]
    filename = f"{source}_{safe_query}_{timestamp}.json"
    filepath = SCRAPPED_DIR / filename
    
    data = {
        "source": source,
        "query": query,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "metadata": metadata or {},
        "records": records
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # Log
    LOGS_DIR.mkdir(exist_ok=True)
    log_entry = {"action": "save_local", "filename": filename, "size_bytes": filepath.stat().st_size}
    with open(LOGS_DIR / "scratch.log", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    return filepath


def process_batch_records(filepath: Path) -> list[dict]:
    """
    Process raw scraped data locally.
    Returns cleaned, validated records ready for Supabase upload.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    processed = []
    skipped = 0
    
    for record in data.get("records", []):
        # Basic validation
        if not record.get("title"):
            skipped += 1
            continue
        
        # Clean text fields (remove HTML/markdown junk)
        title = record.get("title", "")
        spec_text = record.get("spec_text", "")
        
        # Normalize price to integer (IDR)
        try:
            price = int(record.get("price", 0))
            if price <= 0:
                skipped += 1
                continue
        except (ValueError, TypeError):
            skipped += 1
            continue
        
        # Extract category based on source/context
        category = data.get("source", "").split("_")[0]
        
        processed.append({
            "raw_title": title[:500],  # Limit length
            "raw_price": price,
            "raw_spec_text": spec_text[:1000] if spec_text else None,
            "category": category,
            "condition": record.get("condition", "new"),
            "url": record.get("url"),
            "seller": record.get("seller"),
            "scraped_at": data.get("scraped_at"),
            "source": data.get("source")
        })
    
    # Save processed batch locally
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
    
    print(f"[{data['source']}] Scraped: {len(data['records'])}, Processed: {len(processed)}, Skipped: {skipped}")
    
    return processed


def upload_to_supabase(processed_records: list[dict], batch_source: str):
    """Upload processed batch to Supabase via insert_many."""
    supabase = init_supabase()
    
    # Insert directly into raw_listings table
    result = supabase.table("raw_listings").insert(processed_records).execute()
    
    # Log upload
    LOGS_DIR.mkdir(exist_ok=True)
    log_entry = {
        "action": "upload_batch",
        "source": batch_source,
        "record_count": len(processed_records),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    with open(LOGS_DIR / "upload.log", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    return result


def run_batch_scraper(source: str, query: str, scrape_function=None, **kwargs):
    """
    Run scraper → save local → process → upload.
    
    Args:
        source: Source name (tokopedia, facebook_marketplace, etc.)
        query: Search query
        scrape_function: Custom scrape function that returns records list
        **kwargs: Extra args passed to scrape_function
    """
    print(f"\n=== Batch Scraper: {source} - '{query}' ===")
    
    # Step 1: Scrape locally (using custom function or default)
    if scrape_function:
        records = scrape_function(query, **kwargs)
    else:
        # Default placeholder - replace with actual scraper logic
        records = []
    
    if not records:
        print(f"[{source}] No records scraped")
        return {"status": "empty", "count": 0}
    
    # Step 2: Save raw scraped data locally
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filepath = SCRAPED_DIR / f"{source}_{query}_{timestamp}.json"
    save_scraped_data(source, query, records)
    
    # Step 3: Process & validate locally
    processed = process_batch_records(filepath)
    
    # Step 4: Upload to Supabase (only once, batch mode)
    upload_to_supabase(processed, source)
    
    return {
        "status": "success",
        "source": source,
        "query": query,
        "scraped_count": len(records),
        "uploaded_count": len(processed)
    }


if __name__ == "__main__":
    # Example usage:
    # from scrapers.tokopedia import TokopediaScraper
    
    # scraper = TokopediaScraper(pages=2, max_records=500)
    # run_batch_scraper(
    #     source="tokopedia",
    #     query="RTX 4060",
    #     scrape_function=scraper.fetch
    # )
    
    print("Usage: python local_scraper.py")
    print("Call run_batch_scraper() with your scraper function")
