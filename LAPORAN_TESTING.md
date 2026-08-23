# Laporan Testing WorthGaBang (HargaPas) — 23 Agustus 2026

## Ringkasan

| Area | Status | Catatan |
|---|---|---|
| Backend API (FastAPI :8000) | JALAN | /health, /analyze, /catalog, /freshness, /ingest, /jobs/scrape semua OK |
| Frontend (Next.js :3000) | JALAN | `npm install` diperlukan (node_modules belum ada); wiring API_BASE_URL=localhost:8000 benar |
| Unit tests | 12/12 PASS | parser Tokopedia, parse_price, detect_condition, filter relevansi analyze |
| Tokopedia scraper | JALAN | via r.jina.ai, sweep 71 query: 62 sukses, +642 listing real (total 949) |
| Shopee scraper | BLOKIR | captcha wall; butuh SHOPEE_COOKIE atau jalur extension |
| Facebook Marketplace | BLOKIR | login-wall tanpa cookie sesi valid |
| DB | 949 raw listing | 948 tokopedia + 1 demo FB; katalog 189 komponen unik; 47 terdeteksi second |

## Bug yang ditemukan & sudah difix

1. **Parser harga menerima angka liar** (kritis). `PRICE_RE` lama bikin prefix "Rp"
   opsional → "Image 64" ke-parse jadi harga Rp64. 22 dari 22 item scrape pertama
   harganya sampah (Rp15–64). Fix: regex wajib prefix "rp" ATAU satuan "jt/rb/ribu".
2. **Parser Tokopedia salah baca format Jina baru**: 1 produk = 1 blok markdown
   `[![Image N: ...]`, bukan per-baris. Di-rewrite `_parse_blocks()` (blok-based),
   plus filter harga < Rp100rb dan ekstrak URL produk.
3. **Kondisi second/bekas tidak dideteksi untuk PC component** (temuan audit kamu).
   Sudah: `detect_condition()` di parsing.py, dipanggil ingestion (semua source),
   22 listing second terdeteksi otomatis di sweep terakhir.
4. **Model Ti/Super tercampur**: avg_price "RTX 4060" ikut ngitung "RTX 4060 Ti".
   Fix: guard variant di normalizer.
5. **Pembanding analyze nyampur PC full-build** saat cek GPU lepas ("PC GAMING MINI",
   "Deskmeet" ikut jadi pembanding RTX 4060). Fix: filter kata build
   (pc gaming/rakitan/komputer/desktop/dll) di `_pc_comparisons`.
6. **UA browser malah diblokir r.jina.ai** (Cloudflare "Just a moment"). Tokopedia
   scraper sekarang pakai UA non-browser KHUSUS untuk r.jina.ai.
7. **Aksesori & multi-chipset nyempil jadi pembanding**: "Fan VGA RTX 3060 3070
   3080 Rp225rb" ikut ngeskor. Fix: filter kata aksesori (fan/kipas/dus/bracket/
   kabel) + judul yang menyebut >1 chipset dibuang.
8. **Model katalog duplikat**: "RTX3050"/"RTX 3050"/"rtx 3050" jadi 3 row.
   Fix: `_canonical_model()` uppercase + normalisasi spasi; dup per model dibuang
   via scripts/renormalize.py (340 → 189 komponen).
9. **Median pembanding**: comparisons diurut by similarity lalu dipilih 10 listing
   dengan harga terdekat ke median top-20 — output gak didominasi ekstrem murah/mahal.
10. **Window analyze terlalu sempit**: hanya 500 row terbaru, padahal sweep 71 query
    menghasilkan 777+ row PC. Dilonggarkan ke 2000 + threshold similarity >=0.75.

## Jawaban dua pertanyaanmu (hasil eksperimen nyata, bukan teori)

### 1. UA bot "HargaPasBot/1.0 (+scheduled-catalog)"

Eksperimen A/B langsung:

- **Shopee**: UA bot → HTTP 200 tapi halaman captcha (marker verify/captcha),
  nol listing. UA browser Chrome asli → HASIL SAMA PERSIS. Ganti UA tidak menolong
  Shopee — blokirnya berbasis fingerprint/TLS/cookie, bukan string UA.
- **Facebook**: UA bot → 200 berisi login/checkpoint wall (terdeteksi scraper,
  gagal dengan pesan benar). UA browser → HTTP 400 LANGSUNG. Di sini UA browser
  justru LEBIH BURUK. FB sudah difix balik ke UA bot khusus + header Accept,
  biar failure-nya bersih sampai kamu isi FACEBOOK_COOKIE.
- **r.jina.ai (Tokopedia)**: UA browser → Cloudflare challenge page (403).
  UA bot/default httpx → 200 normal. Ini yang bikin sweep pertama gagal total.

Kesimpulan: hipotesis "bot-UA gampang keblokir" benar arahnya untuk situs umum,
tapi untuk 3 target ini kebalik/absen efeknya. Yang membedakan blok/tidak adalah:
cookie sesi (FB), fingerprint anti-bot (Shopee), dan infrastruktur reader (Tokopedia).

### 2. httpx polos vs SPA (regex "Rp" di HTML mentah)

Benar semua, terkonfirmasi:

- Shopee via httpx: HTML mentah 176KB TAPI nol kemunculan "Rp", nol JSON listing.
  Listing dirender JS. Regex kamu tidak akan menemukan apa-apa.
- **Jina Reader untuk Shopee: SUDAH DICOBA** — hasil 200 tapi cuma shell halaman
  (menu/footer), nol produk, nol "Rp". Jina gagal render konten search Shopee
  (kemungkinan karena anti-bot Shopee level render). Jalur Shopee realistis tetap:
  extension ingestion (seperti desain awal) atau API internal + cookie.
- Facebook: sama, butuh cookie sesi valid + konten dirender JS. Tanpa cookie,
  scraper sekarang minimal gagal dengan pesan yang benar (bukan data sampah).

## Cara pakai

```
cd backend
.venv\Scripts\python -m pytest tests -q          # test suite
.venv\Scripts\python scripts/run_full_sweep.py   # sweep manual 20 query x 3 sumber (~4 menit)
.venv\Scripts\python scheduler.py                # cron mingguan Minggu 03:00 + harian FB
.venv\Scripts\python run.py                      # server API :8000
```

Query list (71) digenerate otomatis dari dataset PCPartPicker (66.778 part,
github.com/docyx/pc-part-dataset, di-clone ke pc-part-dataset/): 31 GPU
(RTX 20/30/40/50 + RX 5000-9000), 12 CPU (Ryzen + Core i5/i7), 28 laptop
(brand x series: ROG/TUF/Legion/LOQ/Nitro/Predator/Katana/Victus/Omen/dll).
Regenerate: `python scripts/generate_query_list.py` — output backend/.env +
backend/app/data/query_list.json. Diatur lewat SCRAPE_QUERIES di backend/.env.

Catatan rate limit: Jina Reader free = 20 request/menit. Scraper Tokopedia sudah
diberi throttle 3.5s/request + retry sekali dengan sleep 30s kalau 403/429.

## Yang masih perlu dikerjakan

1. Isi SHOPEE_COOKIE / FACEBOOK_COOKIE di .env supaya sumber kedua/tiga hidup,
   atau arahkan extension ingestion ke POST /api/v1/ingest/{source}.
2. 21 row legacy (harga sampah pre-fix) masih di DB; aman karena filter analyze
   sudah menyingkirkan dari skor, tapi bisa dibersihkan manual kalau mau.
3. Scheduler Windows: scheduler.py harus tetap jalan (misal Task Scheduler /
   pythonw startup) kalau mau freshness otomatis tanpa terminal terbuka.
