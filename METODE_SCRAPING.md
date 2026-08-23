# Riset Metode Scraping — WorL (Worth it or Less)

Tanggal: 2026-08-22 10:37
Konteks: hackathon app "worth it checker" PC/Laptop. Target data: harga live Tokopedia, Shopee, X.

## Hasil Testing (real, dijalankan dari Windows ini)

### Tokopedia
| Metode | Hasil |
|---|---|
| requests biasa | 200 OK tapi SSR cuma skeleton, 0 produk |
| Scrapling Fetcher (TLS impersonation) | 200, tetap skeleton — produk dirender client-side |
| Playwright chromium headless | ERR_HTTP2_PROTOCOL_ERROR konsisten (blok fingerprint headless) |
| StealthyFetcher (camoufox) | 200 + render, tapi selector produk timeout — halaman tidak selesai load |
| **Jina AI Reader (r.jina.ai)** | **BERHASIL** — markdown berisi nama + harga + URL produk. 10 produk parsed dari 1 request |

Cara kerja Jina: proxy browser cloud mereka yang render halaman, return markdown. Gratis tanpa key (rate limited), lebih cepat kalau pakai API key.

Parser: `parse_jina_tokped2.py` -> `tokped_jina_products.json` (nama, price_rp, url).

Contoh hasil real (RTX 3060):
- Vurrion RTX 3060 12GB Froztine: Rp6.570.000
- MSI RTX 3060 VENTUS 2X OC: Rp10.082.000 (100+ terjual)
- ZOTAC RTX 3060 Twin Edge: Rp9.396.000
- EVGA RTX 3060 Ti 2nd: Rp5.499.999

### Shopee
| Metode | Hasil |
|---|---|
| API v4 langsung | 403 error 90309999 (butuh anti-bot token) |
| camoufox headed | redirect ke /verify/traffic/error = wall anti-bot |

Kesimpulan: Shopee paling keras. Butuh cookies login asli ATAU jina dengan key+timeout ATAU extension approach.

### X (Twitter)
| Metode | Hasil |
|---|---|
| nitter instances | respons kosong/mati |
| x.com guest search (chromium & camoufox) | redirect ke /i/jf/onboarding = wajib login |
Jalur: cookies X dari browser user (sama seperti FB dulu), atau API resmi (bayar).

### Reddit (untuk metrik worth-it)
arctic-shift API gratis tanpa auth — sudah dipakai untuk 218 post real.

## Rekomendasi Arsitektur Scraping untuk WorL

1. **Tokopedia = sumber harga utama**: Jina AI Reader (gratis tier) -> parse markdown.
   Fallback: Scrapling Fetcher kalau Tokopedia mulai SSR penuh.
2. **Shopee**: minta user export cookies shopee.co.id sekali (valid ~2 minggu),
   lalu inject ke camoufox -> intercept /api/v4/search/search_items response JSON-nya.
3. **FB Marketplace**: tetap dataset curated statis buat demo (sesuai kesepakatan).
4. **X**: optional — butuh cookies user; skip dulu buat MVP.
5. **llm-scraper**: terinstall + siap (test_llmscraper.js). Pakai kalau mau ekstraksi
   semantik ("GPU ini setara apa") via LLM. Butuh OPENAI_API_KEY env.

## Catatan Teknis Penting (dari praktisi Fiverr - validasi kita sendiri cocok)
- E-commerce besar blok headless → opsi: RDP Windows + browser headed, atau extension content script,
  atau proxy renderer (Jina).
- Komputer harus nyala kalau pakai browser lokal — Jina memindahkan beban ke cloud mereka.

## File Terkait
- test_jina.py / jina_tokped.md / tokped_jina_products.json : jalur Tokopedia yang works
- worl-extension/ : Chrome extension (content script) — jalur utama Shopee/FB Marketplace
- worl-backend.py : backend penerima data extension -> SQLite (port 8787)
- worl-scraper.js : mesin ekstraksi LLM sendiri (port dari llm-scraper, paket asli sudah diuninstall)
- test_worl_scraper.js : self-check engine (preprocess + struktur)
