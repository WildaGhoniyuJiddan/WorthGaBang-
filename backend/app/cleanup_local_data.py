"""
Cleanup script for local_scratch directory.
Delete files older than 7 days to save disk space.
Run weekly as cron job or manually.
"""
import json
from datetime import datetime, timezone
from pathlib import Path


LOCAL_DIR = Path(__file__).parent / "local_scratch"
DAYS_TO_KEEP = 7


def cleanup_old_files():
    """Delete files older than DAYS_TO_KEEP from scraped_raw and processed_batch."""
    folders = ["scraped_raw", "processed_batch"]
    
    deleted_count = 0
    freed_bytes = 0
    
    for folder_name in folders:
        folder = LOCAL_DIR / folder_name
        
        if not folder.exists():
            print(f"[SKIP] {folder_name} folder doesn't exist")
            continue
        
        now = datetime.now(timezone.utc)
        
        for filepath in folder.glob("*.json"):
            age_days = (now - datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc)).days
            
            if age_days > DAYS_TO_KEEP:
                size = filepath.stat().st_size
                filepath.unlink()
                deleted_count += 1
                freed_bytes += size
                
                print(f"[DELETED] {filepath.name} ({age_days} days old, {size:,} bytes)")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"CLEANUP SUMMARY")
    print("=" * 60)
    print(f"Deleted files: {deleted_count}")
    print(f"Freed space: {freed_bytes / 1024 / 1024:.2f} MB")
    
    return deleted_count, freed_bytes


if __name__ == "__main__":
    print("=" * 60)
    print("CLEANUP LOCAL SCRATCH FILES")
    print(f"Days to keep: {DAYS_TO_KEEP}")
    print("=" * 60)
    print(f"\nScanning {LOCAL_DIR}...\n")
    
    cleanup_old_files()
    
    print("\n✅ Cleanup complete!")
