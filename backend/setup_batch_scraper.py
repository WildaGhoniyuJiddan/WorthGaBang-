"""
Installation guide for batch scraper implementation.
Run these commands to set up the egress-reduction feature.
"""
print("=" * 60)
print("BATCH SCRAPER - SETUP GUIDE")
print("=" * 60)

print("""
📋 STEPS TO INSTALL:

1. Install Supabase client (already done ✅):
   
   cd backend
   .venv/Scripts/pip install supabase

2. Verify environment variables in .env.local:

   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
   
   ⚠️ Make sure you have the SERVICE ROLE KEY, not anon key!

3. Test batch scraper:

   # Quick test
   .venv/Scripts/python app/batch_jobs.py
   
   This will test scraping "RTX 4060" and show if it works

4. Check local files created:

   ls -lh app/local_scratch/scraped_raw/
   ls -lh app/local_scratch/processed_batch/

5. Monitor upload success:

   cat app/local_scratch/logs/upload.log


✅ FILES CREATED:
- app/batch_jobs.py              : Main batch scraper logic
- app/cleanup_local_data.py      : Cleanup old local files
- app/cron_cleanup.py            : Cron wrapper
- local_scratch/                 : Scratch directory (gitignored)
- BATCH_SCRAPER_GUIDE.md         : Full documentation


🔄 USAGE:

Replace old cron jobs with new batch version:

OLD CODE:
  from app.jobs import run_cycle

NEW CODE:  
  from app.batch_jobs import run_cycle_batch


💡 NEXT STEPS:
- Restart your Vercel deployments
- Update any scheduled jobs to use batch_jobs.py
- Monitor egress reduction in Supabase dashboard


🎯 EXPECTED RESULTS:
- Egress bandwidth ↓ ~60-90%
- Database operations ↓ 10x
- Faster uploads (batch insert vs row-by-row)
- Local backup of all scraped data

""")
print("=" * 60)
print("SETUP COMPLETE! Ready to test.")
print("=" * 60)
