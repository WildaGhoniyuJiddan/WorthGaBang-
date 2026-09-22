"""
Cron job wrapper for cleanup_local_data.py
Run this weekly to clean up local_scratch files.
"""
from app.cleanup_local_data import cleanup_old_files


if __name__ == "__main__":
    print("Running cleanup cron job...")
    cleanup_old_files()
    print("\n✅ Cron job completed!")
