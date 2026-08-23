# HargaPas

HargaPas membantu pengguna menilai kewajaran harga PC component atau laptop berdasarkan katalog listing marketplace yang sudah dinormalisasi.

## Struktur

- `backend/` — FastAPI, SQLAlchemy, Alembic, scraper adapter, ETL, scoring, dan scheduler.
- `frontend/` — Next.js MVP untuk form cek harga dan hasil analisis.
- `worl-extension/` dan file scraper lama — baseline/legacy dari eksperimen sebelumnya.

## Menjalankan backend lokal

```powershell
cd backend
Copy-Item .env.example .env
<python> -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
python scripts/seed_demo.py
python run.py
```

API tersedia di `http://localhost:8000`, dokumentasi OpenAPI di `/docs`.

Untuk memakai PostgreSQL/Supabase, ubah `DATABASE_URL`, misalnya:

```text
postgresql+psycopg://user:password@host:5432/hargapas
```

## Menjalankan frontend lokal

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

Buka `http://localhost:3000`.

## Job scraping

```powershell
cd backend
python cli.py scrape --query "RTX 4060"
python scheduler.py
```

Tokopedia dan Shopee dijadwalkan mingguan; Facebook Marketplace dijadwalkan harian. Jika Facebook gagal pada manual cycle dan Tokopedia berhasil, response job menandai Tokopedia sebagai fallback source. Cookie browser untuk sumber yang memakai sesi dapat diisi lewat `FACEBOOK_COOKIE` dan `SHOPEE_COOKIE`.

