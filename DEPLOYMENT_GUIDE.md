# Panduan Deployment Projek WorL (Supabase + Vercel)

Dokumen ini adalah instruksi operasional langkah-demi-langkah bagi AI Agent / DevOps Engineer untuk mendeploy seluruh ekosistem **WorthGaBang (WorL)** ke **Supabase** (Database PostgreSQL) dan **Vercel** (Backend FastAPI Serverless + Frontend Next.js).

---

## Daftar Isi
1. [Arsitektur & Komponen Projek](#1-arsitektur--komponen-projek)
2. [Prasyarat & Checklist File Git](#2-prasyarat--checklist-file-git-penting)
3. [Langkah 1: Setup Database Supabase](#3-langkah-1-setup-database-supabase)
4. [Langkah 2: Deploy Backend ke Vercel](#4-langkah-2-deploy-backend-ke-vercel)
5. [Langkah 3: Deploy Frontend ke Vercel](#5-langkah-3-deploy-frontend-ke-vercel)
6. [Langkah 4: Pengujian & Verifikasi Pasca-Deploy](#6-langkah-4-pengujian--verifikasi-pasca-deploy)
7. [Troubleshooting Umum](#7-troubleshooting-umum)

---

## 1. Arsitektur & Komponen Projek

Projek WorL merupakan monorepo yang terdiri dari 2 aplikasi utama di Vercel dan 1 database terkelola:
* **Database**: Supabase PostgreSQL (Port 6543 Transaction Pooler / Port 5432 Direct).
* **Backend (`/backend`)**: FastAPI Python serverless via Mangum adapter (`backend/api/index.py` & `backend/vercel.json`).
* **Frontend (`/frontend`)**: Next.js 15 App Router (TypeScript, React 19).

```
[User Browser]
       |
       v
[Frontend Vercel] ---> HTTP REST API ---> [Backend Vercel (FastAPI)]
                                                    |
                                                    v (SQLAlchemy + psycopg3)
                                          [Supabase PostgreSQL]
```

---

## 2. Prasyarat & Checklist File Git (PENTING!)

### A. Perbaikan File Dataset Referensi di `.gitignore`
Backend membutuhkan 4 file katalog referensi statis di `backend/app/data/` agar fitur kalkulasi skor PassMark, rekomendasi alternatif, dan harga ritel berfungsi:
1. `benchmark_scores.json` (~844 KB - Database PassMark CPU & GPU)
2. `new_price_reference.json` (~4.3 KB - Anchor harga retail resmi)
3. `retail_catalog.json` (~308 KB - Katalog komponen EnterKomputer)
4. `query_list.json` (~2 KB - Daftar target model query scraping)

> [!IMPORTANT]
> **File JSON referensi ini sudah diizinkan di `.gitignore`:**
> ```gitignore
> # Data and Storage folders
> /data/
> backend/data/
> worl-tools/data/
> !backend/app/data/
> !backend/app/data/*.json
> ```
> Jalankan perintah untuk melacaknya ke Git:
> ```bash
> git add .gitignore backend/app/data/*.json
> git commit -m "fix: bundle reference json datasets for vercel build"
> ```

### B. File yang WAJIB DITRACK ke Git
* Seluruh isi folder `backend/` (kecuali `.env`, `.venv`, `__pycache__`, data dump).
* Seluruh isi folder `frontend/` (kecuali `.env.local`, `.next`, `node_modules`).
* File konfigurasi `backend/vercel.json` dan `backend/api/index.py`.

### C. File yang DILARANG DITRACK (Rahasia)
* `backend/.env` (Berisi credentials asli).
* `frontend/.env.local`
* `*.db`, `*.sqlite`, file dump scraper lokal.

---

## 3. Langkah 1: Setup Database Supabase

### 1. Dapatkan Connection String Supabase
1. Masuk ke dashboard [Supabase](https://supabase.com/dashboard) -> Buka Projek Anda.
2. Buka **Project Settings** -> **Database**.
3. Di bagian **Connection string**, pilih mode **URI**:
   - Disarankan menggunakan **Transaction Pooler (Port 6543)** untuk Vercel Serverless:
     ```
     postgresql://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
     ```
   - Atau **Direct Connection (Port 5432)**:
     ```
     postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres
     ```

### 2. Jalankan Migrasi Skema Tabel (Alembic)
Dari terminal lokal dengan virtual environment aktif (`.venv`):
```bash
cd backend
# Set DATABASE_URL sementara di terminal
$env:DATABASE_URL="postgresql://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres"

# Eksekusi migrasi Alembic
.venv\Scripts\alembic upgrade head
```
Perintah ini akan membuat 6 tabel di Supabase:
- `raw_listings`
- `pc_components`
- `laptop_units`
- `scrape_runs`
- `analysis_logs`
- `alembic_version`

### 3. Terapkan Row Level Security (RLS)
Buka menu **SQL Editor** di dashboard Supabase, lalu jalankan script dari [`backend/migrations/enable_rls.sql`](file:///d:/Projek/WorL/backend/migrations/enable_rls.sql):
```sql
DO $$
DECLARE
  t text;
BEGIN
  FOR t IN
    SELECT unnest(ARRAY[
      'alembic_version',
      'analysis_logs',
      'laptop_units',
      'pc_components',
      'raw_listings',
      'scrape_runs'
    ])
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS "public read" ON public.%I;', t);
    EXECUTE format(
      'CREATE POLICY "public read" ON public.%I FOR SELECT USING (true);',
      t
    );
  END LOOP;
END $$;
```

---

## 4. Langkah 2: Deploy Backend ke Vercel

Backend dideploy sebagai project terpisah di Vercel:

### 1. Pengaturan Project Vercel (Backend)
* **Import Git Repository**: Pilih repo projek WorL.
* **Project Name**: `worthgabang-backend` (atau nama pilihan Anda).
* **Root Directory**: `backend` *(Wajib diset ke folder `backend`)*.
* **Framework Preset**: `Other`.

### 2. Environment Variables (Backend)
Masukkan key & value berikut di menu **Settings -> Environment Variables**:

| Variable Name | Contoh Value | Keterangan |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql://postgres.[REF]:[PASS]@aws-0-[REG].pooler.supabase.com:6543/postgres` | URL koneksi Supabase |
| `ENVIRONMENT` | `production` | Mode produksi |
| `CORS_ORIGINS` | `https://worthgabang-frontend.vercel.app,http://localhost:3000` | URL domain frontend Vercel |
| `INTERNAL_JOB_TOKEN` | `<random_secret_string_32_karakter>` | Token rahasia otentikasi cron / scraping |
| `STALE_AFTER_HOURS`| `72` | Waktu kedaluwarsa data (jam) |

> [!NOTE]
> `backend/app/db.py` sudah otomatis mengubah prefix `postgresql://` menjadi `postgresql+psycopg://` dan mematikan `prepare_threshold` agar kompatibel dengan Vercel Serverless & Supabase Pooler.

### 3. Deploy
Klik tombol **Deploy**. Setelah selesai, Anda akan mendapatkan URL backend (misal: `https://worthgabang-backend.vercel.app`).

Uji endpoint healthcheck di browser:
`https://worthgabang-backend.vercel.app/health`
Harus mengembalikan: `{"status":"ok","service":"worthgabang-api","environment":"production"}`.

---

## 5. Langkah 3: Deploy Frontend ke Vercel

Frontend dideploy sebagai project kedua di Vercel:

### 1. Pengaturan Project Vercel (Frontend)
* **Import Git Repository**: Pilih repo projek yang sama.
* **Project Name**: `worthgabang-frontend`.
* **Root Directory**: `frontend` *(Wajib diset ke folder `frontend`)*.
* **Framework Preset**: `Next.js`.

### 2. Environment Variables (Frontend)
Masukkan key berikut di **Settings -> Environment Variables**:

| Variable Name | Contoh Value | Keterangan |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_BASE_URL` | `https://worthgabang-backend.vercel.app` | URL Backend Vercel dari Langkah 2 |

### 3. Deploy
Klik **Deploy**. Setelah build selesai, frontend akan online di URL Vercel (misal: `https://worthgabang-frontend.vercel.app`).

> [!TIP]
> **Update CORS Backend**: Setelah mendapatkan domain frontend yang fix, pastikan variabel `CORS_ORIGINS` di project backend Vercel sudah menyertakan domain frontend tersebut!

---

## 6. Langkah 4: Pengujian & Verifikasi Pasca-Deploy

Jalankan checklist pengujian berikut untuk memastikan seluruh sistem berfungsi:

- [ ] **Test Healthcheck Backend**:
  ```bash
  curl -s https://[YOUR-BACKEND-URL]/health
  # Response: {"status":"ok","service":"worthgabang-api",...}
  ```
- [ ] **Test API Analisis Komponen PC**:
  ```bash
  curl -X POST https://[YOUR-BACKEND-URL]/api/v1/analyze \
    -H "Content-Type: application/json" \
    -d '{"mode":"pc","query":"RTX 3060","price":4000000,"component_type":"gpu"}'
  # Response harus menyertakan score, verdict, dan comparisons.
  ```
- [ ] **Test API Analisis Laptop**:
  ```bash
  curl -X POST https://[YOUR-BACKEND-URL]/api/v1/analyze \
    -H "Content-Type: application/json" \
    -d '{"mode":"laptop","query":"Acer Aspire 7 Pro","price":13000000,"gpu":"RTX 3050","cpu":"i5-13420H"}'
  ```
- [ ] **Test UI Frontend**:
  Buka URL frontend di browser, coba lakukan kalkulasi harga di tab **PC Components**, **Laptop**, dan **Bundle Paket**. Pastikan hasil spektrum harga dan pembanding muncul tanpa error CORS di console browser.

---

## 7. Troubleshooting Umum

1. **Error: `DuplicatePreparedStatement` pada Supabase / PostgreSQL**:
   - Penyebab: Vercel serverless me-reuse koneksi TCP antar request.
   - Solusi: Sudah tertangani di `backend/app/db.py` baris 24 (`"prepare_threshold": None`). Pastikan menggunakan Supabase Transaction Pooler (Port 6543).

2. **Error: `NetworkError when attempting to fetch resource` di Frontend**:
   - Penyebab: CORS origin belum didaftarkan di backend.
   - Solusi: Buka dashboard Vercel Backend -> Environment Variables -> Edit `CORS_ORIGINS` -> Tambahkan domain frontend Vercel (tanpa trailing slash) -> Lakukan **Redeploy**.

3. **Hasil Analisis selalu "Data Terbatas" dan tidak ada rekomendasi alternatif**:
   - Penyebab: File JSON `backend/app/data/*.json` tidak ter-bundle ke build Vercel.
   - Solusi: Periksa bagian [2.A](#a-perbaikan-file-dataset-referensi-di-gitignore), un-ignore file tersebut di Git dan commit ulang.
