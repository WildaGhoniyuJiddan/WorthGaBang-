# Batch Scraper Implementation - Mengurangi Egress Supabase

## 🎯 Tujuan
Mengurangi egress bandwidth Supabase dengan scraping data lokal terlebih dahulu, kemudian upload dalam 1 batch operation.

## ⚡ Keuntungan
- **Egress turun drastis**: 1x upload per scrape (bukan streaming thousands of rows)
- **Validasi data**: Bisa clean & filter sebelum insert ke DB
- **Error handling lebih baik**: Data tersimpan lokal sebagai backup
- **Cost saving**: Mengurangi database operations & bandwidth Supabase

---

## 📁 Struktur File Baru

```
backend/
├── app/
│   ├── batch_jobs.py        # Main batch scraper logic
│   └── local_scratch/       # Scratch folder (gitignored)
│       ├── scraped_raw/     # Raw JSON setelah scrape
│       ├── processed_batch/ # JSON setelah cleaning
│       └── logs/            # Log aktivitas
```

---

## 🔄 Cara Kerja Workflow

### **Approach Lama** (Streaming):
```
Scrape → Stream langsung ke Supabase (row by row) 
→ Egress tinggi: N × query_rows MB
```

### **Approach Baru** (Batch):
```
Scrape → Save local JSON 
       → Process & Clean data
       → Upload 1 batch to Supabase
       → Egress rendah: 1 × total_batch MB
```

---

## 🛠️ Implementasi

### 1. File: `batch_jobs.py`

```python
def run_batch_scraper(source: str, query: str, fetch_fn):
    """Complete workflow: scrape → save local → process → upload"""
    
    # Step 1: Scrape locally
    records = fetch_fn(query)
    
    # Step 2: Save raw JSON lokal
    filepath = save_local(source, query, records)
    
    # Step 3: Process & validate data
    processed_records, skipped = process_batch(filepath)
    
    # Step 4: Upload 1 batch ke Supabase
    if processed_records:
        upload_to_supabase(processed_records)
    
    return {"status": "success", "uploaded_count": len(processed_records)}
```

### 2. Fungsi Utama

#### `save_local(source, query, records)`
- Simpan raw scraped data sebagai JSON di `local_scratch/scraped_raw/`
- Format: `{source}_{query}_{timestamp}.json`
- Sebagai backup dan audit trail

#### `process_batch(filepath)`
- Load JSON dari disk
- Validasi: cek title, price > 0, dll
- Clean: trim text fields, limit length
- Filter invalid records
- Simpan hasil ke `processed_batch/`
- Return: `(processed_records, skipped_count)`

#### `upload_to_supabase(records)`
- Insert semua records sekaligus via Supabase client
- 1x operation vs thousands of individual inserts
- jauh lebih efisien untuk egress

---

## 📊 Estimasi Pengurangan Egress

### Skenario: Scraping RTX 4060 dari Tokopedia
- **Query volume**: 500 listings
- **Average row size**: ~800 bytes

**Approach lama (streaming):**
- 500 row × 800 bytes = 400 KB stream ke Supabase
- Jika query 10x/hari = 4 MB/day egress

**Approach baru (batch):**
- Save lokal: 400 KB JSON file
- Upload 1 batch: 400 KB sekali jalan
- Dengan caching, bisa ↓ jadi 1×/hari = 400 KB/day

### ✅ **Penghematan: 90%+ egress reduction**

---

## 🧪 Cara Test

### Manual Testing:
```bash
cd backend
python -c "
from app.batch_jobs import run_batch_scraper
from scrapers.tokopedia import TokopediaScraper

scraper = TokopediaScraper(pages=2, max_records=500)
result = run_batch_scraper(
    source='tokopedia',
    query='RTX 4060',
    fetch_fn=scraper.fetch
)
print(result)
"
```

### Check Output Files:
```bash
ls -lh backend/app/local_scratch/scraped_raw/
ls -lh backend/app/local_scratch/processed_batch/
```

---

## 🔄 Migrasi dari Jobs Lama

### Option A: Ganti Semua (Recommended)
Replace `jobs.py` dengan `batch_jobs.py`:
```python
# Lama:
from app.jobs import run_source, run_cycle

# Baru:
from app.batch_jobs import run_source_batch, run_cycle_batch
```

### Option B: Hybrid Mode
Jalankan kedua mode berdampingan:
- `run_source()` → immediate insert (untuk real-time)
- `run_source_batch()` → scheduled jobs (efficiency)

---

## 🗂️ Local Scratch Data Lifecycle

### Folder Structure:
```
local_scratch/
├── scraped_raw/
│   └── tokopedia_RTX_4060_20260922_184816.json
├── processed_batch/
│   └── tokopedia_RTX_4060_20260922_184816_processed.json
└── logs/
    ├── scratch.log      # Log save_local
    └── upload.log       # Log upload batches
```

### Cleanup Policy:
```python
# Script cleanup otomatis (cron daily)
import shutil
from pathlib import Path

LOCAL_DIR = Path(__file__).parent / "local_scratch"
DAYS_TO_KEEP = 7

for folder in ["scraped_raw", "processed_batch"]:
    for f in (LOCAL_DIR / folder).glob("*.json"):
        if (datetime.now() - f.stat().st_mtime).days > DAYS_TO_KEEP:
            f.unlink()
```

---

## ⚠️ Catatan Penting

### Environment Variables Required:
```bash
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
```

### Install Dependencies:
```bash
pip install supabase-client
```

### Git Ignore Lokal Files:
Add to `.gitignore`:
```
local_scratch/scraped_raw/*
local_scratch/processed_batch/*
!local_scratch/.gitkeep
```

---

## 📈 Monitoring & Logging

### Log Format (scratch.log):
```json
{"action": "save_local", "filename": "tokopedia_RTX_4060_...", "size_bytes": 409600}
```

### Log Format (upload.log):
```json
{"action": "upload_batch", "source": "tokopedia", "record_count": 487, "timestamp": "..."}
```

### Verify Upload Success:
```sql
-- Check last inserted rows
SELECT COUNT(*) FROM raw_listings WHERE source = 'tokopedia';
SELECT MIN(scraped_at), MAX(scraped_at) FROM raw_listings;
```

---

## 🔧 Troubleshooting

### Error: "No module named 'supabase'"
```bash
pip install supabase-client
```

### Error: "File not found"
Check jika `scraped_raw/*.json` ada atau belum dibuat:
```bash
ls -lh backend/app/local_scratch/scraped_raw/
```

### Egress masih tinggi?
- Pastikan pakai `insert(batch)` bukan loop `insert(row-by-row)`
- Verifikasi `upload_to_supabase()` dipanggil sekali per scrape
- Monitor network traffic dengan tools seperti Wireshark

---

## 🎓 Best Practices

1. **Scrape off-peak hours** → Reduce concurrent DB operations
2. **Rate limit scraping** → Avoid blocking IP
3. **Process incrementally** → Jangan wait all scrape selesai
4. **Validate before upload** → Minim waste bandwidth on bad data
5. **Monitor success rate** → Track % valid vs skipped records

---

## 📝 Contoh Lengkap Integration

```python
# Example: Cron job scheduler integration
from app.batch_jobs import run_batch_scraper
from scrapers.tokopedia import TokopediaScraper
import time

QUERY_LIST = [
    "RTX 4060",
    "Ryzen 5 5600",
    "MacBook Air M1",
    # ... add more queries
]

if __name__ == "__main__":
    scraper = TokopediaScraper(pages=2, max_records=500)
    
    for query in QUERY_LIST:
        try:
            result = run_batch_scraper(
                source="tokopedia",
                query=query,
                fetch_fn=scraper.fetch
            )
            print(f"✅ {query}: {result['uploaded_count']} records")
            
            # Respectful delay between queries
            time.sleep(scraper.request_delay_seconds)
            
        except Exception as e:
            print(f"❌ {query}: Failed - {str(e)}")
```

---

## 🚀 Next Steps

1. ✅ Replace `jobs.py` dengan `batch_jobs.py`
2. ⚙️ Update Vercel/Cron triggers
3. 📊 Setup monitoring dashboard
4. 🗑️ Implement log cleanup cron
5. 📈 Monitor egress reduction effect

---

**Catatan**: Setelah implementasi ini, bandwidth Supabase turun drastis karena:
1. **Database ops**: 1 insert statement vs thousands
2. **Data transfer**: Local processing + 1x upload
3. **Connection reuse**: Single connection per batch

Dengan approach ini, proyek WorL bisa tetap di plan gratis/free tier meski traffic naik! 🎉
