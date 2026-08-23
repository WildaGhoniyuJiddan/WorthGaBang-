# WorL Extension v3 — Pengumpul Pertanyaan Worth-It (FB Feed)

Extension Chrome buat nangkep post pertanyaan "worth it ga sih beli ini di harga segini"
dari feed/timeline/grup Facebook, lalu kirim ke backend lokal buat dikumpulin jadi dataset.

Satu mode fokus: **FB feed/grup question collector**. Kode Marketplace/Tokopedia/Shopee
versi lama masih ada di `legacy/marketplace-ecom.js` (tidak dimuat otomatis).

## Cara kerja

1. Login manual ke Facebook di Chrome (sekali saja, sesi tersimpan)
2. `python worl-backend.py` dari folder D:\Projek\WorL (backend harus hidup dulu)
3. Buka tab Facebook yang mau discan (feed grup / halaman search)
4. Klik ikon WorL di toolbar → popup:
   - Toggle hijau = ON
   - Kata kunci (opsional; kalau tab aktif bukan FB, dibuka ke halaman search FB)
   - Maks pertanyaan (berhenti kalau tercapai)
   - Opsional: **Cek jawaban** — buka tiap permalink, hitung komentar +
     timestamp komentar pertama → latency jawaban (jauh lebih lambat)
5. Klik **Mulai Scan** → extension scroll otomatis, tangkap post begitu dirender
   (MutationObserver), deteksi pertanyaan worth-it, kirim ke backend
6. CSV tersimpan otomatis ke `worl-extension/hasil/`
7. Lihat hasil juga di http://localhost:8787/products

## Instalasi / update

1. `chrome://extensions` → Developer mode ON
2. **Load unpacked** → pilih folder `worl-extension/`
3. Kalau sudah pernah install: klik ikon refresh (↻) di kartu WorL Collector

## Detail teknis

- **Deteksi**: kata worth (grup keraguan vs assertif) + harga + frasa penilai
  (layak/wajar/rugi) + gerbang SELL_SIGNALS — post jualan hanya lolos kalau ada
  tanda tanya atau partikel keraguan eksplisit (`ga/gak/kah`). Tiap record punya
  `detected_reason` (rule A/B/D, mis. `A+sell_filtered`) biar gampang diaudit.
- **Dedup & stats persisten** via chrome.storage.local (`seen_<id>`, `worl_stats`) —
  aman tab reload / re-inject, gak ada duplikat ke CSV.
- **Kirim data** lewat background service worker (`background.js`, retry 2x,
  delay 1.5s) — fetch dari context ekstensi, CORS-safe berkat host_permissions.
- **Timestamp absolut** dari `<abbr title>` → field `posted_at_title` (+ISO bila
  formatnya dikenali). Dasar perhitungan latency jawaban.
- **Cek jawaban** (opsional): antrian permalink di `worl_reply_queue`, diproses
  setelah scan selesai; hasil update record yang sama via `id` sama
  (`answered`, `first_reply_latency_minutes`).
- **Anti-deteksi**: delay scroll acak 1800–3200ms, batas sesi 20 menit / 400 post /
  maxItems (mana duluan), early-stop kalau FB throttle render.

## Skema payload (POST http://localhost:8787/collect)

```json
{
  "site": "facebook_feed",
  "keyword": "string",
  "page_url": "string",
  "type": "question_post | session_summary",
  "scraped_at": "ISO datetime",
  "items": [{
    "id": "hash url/text (kunci dedup & update)",
    "author": "string", "name": "string",
    "time_text": "'5 j'", "posted_at_title": "isi title <abbr>",
    "posted_at": "ISO | null",
    "comments": "string angka", "shares": "string angka",
    "description": "max 3000 char", "url": "permalink",
    "is_question": 1, "group": "string",
    "detected_reason": "'A' | 'B' | 'D' | 'A+sell_filtered' | ...",
    "answered": "bool|null", "first_reply_latency_minutes": "number|null"
  }]
}
```

Backend idempotent by `items[].id`: kalau id sudah ada di CSV, update baris itu
(penting untuk update `answered` susulan).

## Test

```
node test_question_detector.js   # harus 100% pass
```

Termasuk kasus false-positive jualan ("worth banget gan!") yang wajib FALSE.
