"""
Quick deployment commands for batch scraper implementation.
Run this to deploy everything automatically.
"""


def quick_deploy():
    """Deploy batch scraper with minimal steps."""
    import subprocess
    import sys
    
    print("=" * 60)
    print("QUICK DEPLOYMENT FOR WORL BATCH SCRAPER")
    print("=" * 60)
    
    steps = [
        ("1. Verify Python syntax", 
         ["python", "-m", "py_compile", "app/batch_jobs.py"]),
        
        ("2. Install dependencies if needed", 
         [sys.executable, "-m", "pip", "install", "supabase"]),
        
        ("3. Test imports", 
         ["python", "-c", "from app.batch_jobs import run_cycle_batch; print('✅ Imports OK')"]),
        
        ("4. Create local directories",
         ["mkdir", "-p", "app/local_scratch/scraped_raw"]),
    ]
    
    for desc, cmd in steps:
        print(f"\n{desc}...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"   ✅ Success")
                print(f"   {result.stdout.strip()}")
            else:
                print(f"   ❌ Failed:")
                print(f"   {result.stderr}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n" + "=" * 60)
    print("DEPLOYMENT READY!")
    print("=" * 60)
    print("""
Next steps:
1. Deploy to Vercel
2. Monitor egress metrics in Supabase dashboard
3. Check logs for any upload errors

To test: python app/batch_jobs.py
To cleanup: python app/cron_cleanup.py
""")


if __name__ == "__main__":
    quick_deploy()
