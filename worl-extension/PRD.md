# PRD — WorL Extension v3 (PC/Laptop Worth-It Question Collector)

Status: draft untuk dieksekusi coding agent
Scope file: folder `worl-extension/` (manifest.json, content.js, popup.html, popup.js, test_question_detector.js)
Tidak termasuk: `worl-backend.py` (tidak ada di repo ini, cuma didefinisikan kontraknya di Appendix A)

---

## 0. Konteks

WorL adalah extension Chrome buat validasi data untuk project riset "PC/Laptop worth-it checker": scan feed/grup Facebook, tangkap post yang isinya orang nanya "worth it ga sih beli ini di harga segini", terus kirim ke backend lokal buat dikumpulin jadi dataset.

Versi sekarang (v7 di `content.js`, manifest v2.0.0) sudah bisa jalan tapi punya beberapa bug korektnes dan gap fitur yang bikin datanya kurang bisa dipercaya. PRD ini isinya audit lengkap + spesifikasi perbaikan, disusun per langkah biar bisa dieksekusi berurutan tanpa bikin breaking change beruntun.

---

## 1. Audit — Temuan di Kode Existing

### Bug 1 (P0, korektnes data) — False positive: post jualan ke-detect sebagai pertanyaan

Lokasi: `isWorthQuestion()` di `content.js` baris 136-163, khususnya `WORTH_WORDS` baris 103-108 dan Rule A baris 159 (`hasWorth && hasPrice`).

Masalahnya: Rule A cuma butuh kata "worth" + ada penyebutan harga, **tanpa wajib ada tanda tanya atau partikel keraguan (ga/gak/kah)**. Beberapa entri di `WORTH_WORDS` (`worth sih`, `worth nih`, `worth bang`, `worth gan`) itu justru sering dipakai penjual sebagai kalimat promosi, bukan pertanyaan. Sudah aku tes langsung:

```
"RTX 3060 dijual 2jt worth banget gan, buruan cepetan!"        -> true (harusnya false)
"WTS ryzen 5 3600 harga 1.5jt worth it pasti, chat langsung"    -> true (harusnya false)
"ready stock rtx 3060 harga 3jt worth banget, no php"           -> true (harusnya false)
```

Ini bug paling berbahaya karena tujuan utama extension ini adalah misahin "orang yang nanya" dari "orang yang jualan" — kalau bocor ke jualan, dataset-nya rusak dari akarnya.

**Fix yang diminta:**
1. Tambah daftar `SELL_SIGNALS` (regex/kata): `jual`, `dijual`, `wts`, `ready stock`, `ready\b`, `preloved`, `nego tipis`, `minat chat`, `minat wa`, `order`, `siap kirim`, `cod`, `garansi toko`, `real pic`.
2. Kalau teks kena `SELL_SIGNALS`, maka teks itu **wajib** punya `hasQMark === true` atau salah satu partikel keraguan eksplisit (`ga`, `gak`, `ngga`, `nggak`, `kah` yang nempel ke kata worth/layak/wajar) baru dianggap pertanyaan. Tanpa itu, langsung `return false` walau kata lain match.
3. Pisahkan `WORTH_WORDS` jadi dua grup: `WORTH_DOUBT` (partikel keraguan eksplisit — selalu valid sebagai sinyal tanya) vs `WORTH_ASSERT` (`sih`, `nih`, `bang`, `gan` — netral, butuh dukungan `hasQMark` atau `hasJudge` biar valid).
4. Tambahin field `detected_reason` di hasil deteksi (rule mana yang match: A/B/C/D + apakah kena filter SELL_SIGNALS) supaya nanti gampang di-audit manual kalau ada yang salah lagi.

### Bug 2 (P0, fitur inti belum ada) — Cek jawaban (checkReplies) cuma janji, belum ada implementasinya

Lokasi: `state.checkReplies` dideklarasi di baris 30, tapi di seluruh `content.js` tidak ada satupun kode yang membacanya. Sudah aku grep, nol referensi lain.

Ini masalah karena README poin 4 dan komentar di baris 16-18 bilang metrik utama pitch project ("Dampak terukur": persentase pertanyaan yang dijawab + kecepatan jawaban) itu justru fitur yang belum dibangun sama sekali. Tanpa ini, extension baru ngumpulin "ada berapa pertanyaan", bukan "berapa yang gak terjawab" — padahal itu inti argumen project-nya.

**Fix yang diminta:**
- Kalau `state.checkReplies === true`, setelah `scanFeed()` nemuin pertanyaan baru, masukkan urlnya ke antrian (`chrome.storage.local`, key `worl_reply_queue`).
- Proses antrian di luar loop scroll utama (biar ga ganggu scan feed): buka `location.href = url`, tunggu render, hitung komentar + ambil timestamp komentar pertama via `abbr.title` (lihat Bug 5), balik ke feed (`history.back()`), lanjut item berikutnya.
- Hasil dikirim sebagai update terhadap record yang sudah ada (pakai `id` yang sama), isi field `answered` (bool) dan `first_reply_latency_minutes` (null kalau belum ada komentar).
- Mode ini defaultnya `false` di popup (biar user pilih sadar, karena jauh lebih lambat — sesuai catatan di kode aslinya).

### Bug 3 (P0, integritas data) — Dedup dan counter cuma hidup di memory

Lokasi: `seenIds = new Set()` (baris 255) dan `stats = {...}` (baris 256), keduanya variabel module-level biasa.

Kalau tab di-reload, FB navigasi penuh (bukan SPA push-state), atau content script ke-inject ulang, `seenIds` sama `stats` reset ke kosong. Efeknya: post yang udah pernah dikirim ke backend bisa terkirim ulang (duplikat di CSV), dan angka di badge/status jadi ga akurat buat sesi panjang.

**Fix yang diminta:**
- Ganti dedup jadi persistent: sebelum `send()`, cek `chrome.storage.local.get('seen_' + id)`; kalau sudah ada, skip. Kalau belum, `set` dulu baru kirim. (Pola ini sebenernya sudah dipakai di `runDetailCrawl()` baris 431 buat mode marketplace — tinggal disamakan ke `fb_feed`.)
- Simpan `stats` juga di `chrome.storage.local` (key `worl_stats`), di-increment lewat `get` -> `set`, bukan variabel lokal. Biar kalau session sempat kereset, angka total tetap nyambung.

### Bug 4 (P1, reliabilitas jaringan) — Fetch ke backend rawan gagal karena CORS

Lokasi: `send()` baris 238-251 langsung `fetch()` dari content script.

Ini gotcha umum di Chrome extension: `host_permissions` di manifest (baris 7) cuma membebaskan CORS untuk fetch yang jalan dari context ekstensi (background/service worker, popup). Fetch yang jalan dari **content script** tetap kena aturan CORS punya origin halaman (`facebook.com` manggil ke `localhost:8787`) — kecuali backend Python-nya secara eksplisit ngirim header `Access-Control-Allow-Origin`. Kalau belum, semua `send()` bisa gagal diam-diam (makanya folder `hasil/` masih kosong).

**Fix yang diminta (tetap dalam scope extension, ga perlu ubah backend):**
- Tambah `background.js` sebagai service worker (`"background": {"service_worker": "background.js"}` di manifest).
- Content script kirim payload lewat `chrome.runtime.sendMessage({type:'worl_send', payload})`, bukan `fetch()` langsung.
- `background.js` yang eksekusi `fetch()` ke `BACKEND` (fetch dari service worker context ini yang beneran dilindungi `host_permissions`, jadi CORS-safe).
- Tambahin retry sederhana (2x percobaan, delay 1.5 detik) di level background, plus `sendResponse({ok, status})` balik ke content script buat update badge.

### Bug 5 (P1, kualitas data) — Timestamp cuma teks relatif, absolute time-nya diabaikan

Lokasi: `extractPost()` baris 207-209, `timeText = smartText(abbr)` cuma ambil textContent (misal "5 j", "Kemarin").

FB biasanya naruh timestamp lengkap di atribut `title` elemen `<abbr>` (misal "Kamis, 4 September 2025 pukul 10:15"). Ini penting justru buat Bug 2 (hitung latency jawaban) — tanpa waktu absolut, "kecepatan jawaban" gak bisa dihitung sama sekali walau fitur cek-jawaban-nya sudah jadi.

**Fix yang diminta:**
- Tambah pengambilan `abbr.getAttribute('title')` sebagai `posted_at_raw_title`.
- Parse ke ISO string kalau formatnya kekenali (fallback: simpan string mentah aja, biar backend/analisis nanti yang parse, jangan buang datanya).

### Bug 6 (P2, kebersihan arsitektur) — Kode marketplace/e-commerce jadi beban mati

Lokasi: `content.js` baris 356-465 (`parseFbList`, `parseTokpedList`, `parseShopeeList`, `runDetailCrawl`, `finishDetail`, `scrollAndNext`) + tombol "FB Marketplace" dan "E-commerce" di `popup.html` baris 53-64 dan `MODES` di `popup.js` baris 15-20.

Berdasarkan pesan kamu hari ini, misi extension ini sekarang fokus tunggal: nangkep pertanyaan worth-it di post FB. Mode marketplace/tokopedia/shopee itu sisa dari scope versi sebelumnya (README lama nyebut "Scraper Shopee/Tokopedia/FB Marketplace") dan sekarang cuma nambah selector DOM yang berpotensi patah tanpa nambah value ke misi utama.

**Fix yang diminta (bukan dihapus permanen, dipisah):**
- Pindahin fungsi-fungsi itu ke `legacy/marketplace-ecom.js`, tidak di-load default di manifest.
- Popup disederhanain jadi single-mode (langsung "Mulai Scan" untuk `fb_feed`, tanpa pilihan Marketplace/E-commerce).
- Kalau nanti butuh lagi, kodenya masih ada tinggal di-load balik — bukan ditulis ulang dari nol.

### Bug 7 (P1, keamanan akun) — Tidak ada jitter atau batas sesi, pola scroll gampang kedeteksi

Lokasi: `runQuestionCollector()` baris 305-329, interval scroll & delay-nya fixed (`800ms`, `sleep(2700)`), dan syarat berhenti cuma `stats.pcQuestions < state.maxItems` — kalau grup-nya sepi pertanyaan worth-it, sesi bisa scroll lama banget tanpa batas waktu.

Karena ini jalan di sesi login pribadi kamu (bukan akun burner), pola scroll+delay yang konstan itu ciri khas bot dan berisiko kena flag otomatis dari FB.

**Fix yang diminta:**
- Randomize delay tiap iterasi scroll (misal `1800-3200ms`, bukan angka tetap).
- Tambah dua batas berhenti baru selain `maxItems`: batas waktu (misal 20 menit) dan batas total post discan (misal 400), mana pun tercapai duluan.
- Kalau `idle` counter (baris 325-328) kena threshold beberapa kali dalam satu sesi berturut-turut (indikasi FB nge-throttle render), hentikan sesi lebih awal daripada terus nyoba.

---

## 2. Goals & Non-Goals

**Goals (v3):**
- Deteksi pertanyaan worth-it akurat, minim false positive dari post jualan.
- Data yang terkumpul persist, gak duplikat, dan lengkap (termasuk status terjawab/belum + latency kalau `checkReplies` aktif).
- Extension aman dipakai di akun pribadi tanpa bikin sesi scroll mencurigakan.
- Satu mode fokus: FB feed/grup question collector.

**Non-goals (v3):**
- Scraping harga produk Marketplace/Tokopedia/Shopee (dipisah ke legacy, lihat Bug 6).
- Rekomendasi "worth it atau nggak" otomatis — itu scope project [[hemolink]]-nya beda, di luar extension ini, extension cuma pengumpul data mentah.
- Backend Python (`worl-backend.py`) — kontraknya didefinisikan di Appendix A, tapi implementasinya di luar scope PRD ini.

---

## 3. Skema Data (kontrak payload ke backend)

Field baru ditandai **[BARU]**.

```json
{
  "site": "facebook_feed",
  "keyword": "string",
  "page_url": "string",
  "type": "question_post | session_summary",
  "scraped_at": "ISO datetime",
  "items": [{
    "id": "hash url atau text — [BARU], dipakai buat dedup & update record",
    "name": "author",
    "author": "string",
    "time_text": "teks relatif asli (mis. '5 j')",
    "posted_at_title": "isi atribut title dari <abbr> — [BARU]",
    "comments": "string angka",
    "shares": "string angka",
    "description": "string, max 3000 char",
    "url": "string",
    "is_question": 1,
    "group": "string",
    "detected_reason": "kode rule yang match, mis. 'A' / 'B' / 'D+sell_filtered' — [BARU]",
    "answered": "bool | null — [BARU], null kalau checkReplies off",
    "first_reply_latency_minutes": "number | null — [BARU]"
  }]
}
```

---

## 4. Langkah Eksekusi (untuk coding agent)

Kerjakan berurutan. Tiap step harus tetap bikin extension bisa di-load ulang (`chrome://extensions` reload) tanpa error sebelum lanjut ke step berikutnya.

**Step 1 — Fix deteksi (Bug 1)**
Ubah `isWorthQuestion()` sesuai spesifikasi di Bug 1. Tambah kasus false-positive dari Bug 1 ke `test_question_detector.js` sebagai kasus `false`. Jalankan `node test_question_detector.js`, harus 100% pass termasuk kasus baru.

**Step 2 — Dedup & stats persistent (Bug 3)**
Ganti `seenIds`/`stats` in-memory jadi berbasis `chrome.storage.local`, ikutin pola `done_<url>` yang sudah ada di `runDetailCrawl`.

**Step 3 — Background service worker (Bug 4)**
Tambah `background.js`, ubah `send()` di content script jadi `chrome.runtime.sendMessage`, update `manifest.json`.

**Step 4 — Timestamp absolut (Bug 5)**
Tambah pengambilan `abbr.title` di `extractPost()`, masukkan ke payload sebagai `posted_at_title`.

**Step 5 — Implementasi checkReplies (Bug 2)**
Bangun antrian + logic buka-permalink-hitung-latency sesuai spesifikasi Bug 2. Ini bergantung ke Step 4 (butuh timestamp absolut buat hitung latency).

**Step 6 — Anti-deteksi (Bug 7)**
Randomize delay, tambah batas waktu & batas scanned-post di `runQuestionCollector()`.

**Step 7 — Bersihin scope (Bug 6)**
Pindah kode marketplace/ecom ke `legacy/marketplace-ecom.js`, sederhanain `popup.html`/`popup.js` jadi single-mode, update `manifest.json` content_scripts kalau perlu.

**Step 8 — Sinkronkan README**
Update `README.md` supaya cocok sama arsitektur v3 (background worker, mode tunggal, field data baru).

---

## 5. Acceptance Criteria

- [ ] `node test_question_detector.js` pass 100%, termasuk minimal 4 kasus baru dari pola "post jualan pakai kata worth" (Bug 1).
- [ ] Reload tab FB dua kali di tengah sesi scan tidak menghasilkan record duplikat di backend (verifikasi manual: cek `id` yang sama gak terkirim dua kali).
- [ ] `send()` tidak lagi dipanggil langsung dari `content.js` — hanya lewat `chrome.runtime.sendMessage`.
- [ ] Payload `question_post` berisi `posted_at_title`, `detected_reason`, `answered`, `first_reply_latency_minutes` (null valid kalau `checkReplies` off).
- [ ] Sesi scan otomatis berhenti kalau kena salah satu dari tiga batas: `maxItems` tercapai, batas waktu, atau batas scanned-post.
- [ ] Popup tidak lagi menampilkan tombol "FB Marketplace" / "E-commerce"; fungsi lama masih ada dan bisa diimpor balik dari `legacy/marketplace-ecom.js`.
- [ ] `manifest.json` valid (load unpacked tanpa error) dan mendeklarasikan `background.service_worker`.

---

## Appendix A — Kontrak yang diasumsikan untuk `worl-backend.py`

File ini tidak ada di repo yang di-scan, jadi diasumsikan (bukan ditulis ulang oleh agent kecuali diminta terpisah):

- Endpoint `POST /collect` menerima payload sesuai skema di Bagian 3, idempotent berdasarkan `items[].id` (kalau `id` sudah ada di CSV, update record itu — bukan append baris baru). Ini penting khusus buat mendukung Step 5 (checkReplies ngirim update susulan ke record yang sama).
- Endpoint ini sebaiknya set header `Access-Control-Allow-Origin` mengizinkan origin ekstensi, sebagai lapisan aman kedua di luar fix Bug 4.
- `GET /products` (disebut di README) buat lihat hasil — di luar scope PRD ini.
