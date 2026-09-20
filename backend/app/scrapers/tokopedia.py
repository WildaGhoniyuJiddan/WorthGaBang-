import re
import time
from urllib.parse import quote

import httpx

# Browser UA string for detail page requests (detail) page requests (Tokopedia serves full HTML to real browsers)
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)

# UA for Jina requests (to avoid being blocked by Jina or Tokopedia via Jina)
JINA_UA = "WorthGaBangBot/1.0 (+scheduled-catalog)"

from .base import ListingRecord, Scraper, ScraperError
from .tokopedia_detail import extract_detail, looks_like_dead_listing
from ..services.listing_quality import assess_listing
from ..services.parsing import detect_condition, parse_price
from ..services.relevance import component_type_from_query, is_relevant_pc_listing, query_variants

# ponytail: batas bawah harga masuk akal untuk GPU/CPU/laptop; kalau nanti mau
# scrape komponen murah (kabel, fan), turunkan atau jadikan config.
MIN_PLAUSIBLE_PRICE = 100_000

# Regex untuk parsing blok produk dari halaman pencarian Tokopedia (via Jina)
# Ambil grup 2 (nama toko) dari pattern: ...badge_os.png~....jpg] Tokopedia Nama Toko (https://...)
_IMAGE_MD_RE = re.compile(r"!\\[Image [^\\]()]*\\]\\([^)]*\\)")
_JINA_URL = "https://r.jina.ai/http://{}"
# Nama toko: teks setelah gambar badge Official Store, sebelum URL.
# Pattern: badge_os.png~....image.image) Nama Toko (https://...
_SHOP_RE = re.compile(r"badge_os[^)]*\\)\\s+([^\\]]+)(?=\\]\\()")
# Ambil grup 1 (jumlah terjual) dari pattern: ...rating] 5.0 19 terjual ...
_SOLD_RE = re.compile(r"rating[^\\d]*([\\d.,]+)\\s*terjual", re.IGNORECASE)
# Official Store badge di halaman pencarian (tidak ada di detail)
_OFFICIAL_BADGE_RE = re.compile(r"badge_os\\.png")


def _parse_blocks(body: str, query: str | None = None,
                  component_type: str | None = None) -> list[ListingRecord]:
    # Jina merender 1 produk Tokopedia = 1 blok markdown diawali "[![Image N: ...]".
    records: list[ListingRecord] = []
    blocks: list[str] = []
    for line in body.splitlines():
        if line.startswith("[![Image"):
            blocks.append(line)
        elif blocks:
            blocks[-1] += " " + line
    for block in blocks:
        price_match = re.search(r"Rp\\s*[\\d.,]+", block)
        if not price_match:
            continue
        price = parse_price(price_match.group(0))
        if not price or price < MIN_PLAUSIBLE_PRICE:
            continue
        # Judul: teks antara penutup tag gambar pertama dan harga.
        # Pattern: ](...) Title Rp
        title_match = re.search(r']\\([^)]*\\)\\s+(.+?)\\s+Rp', block)
        title = title_match.group(1).strip() if title_match else None
        if not title or len(title) < 4:
            continue
        if query and component_type and not is_relevant_pc_listing(query, title, component_type):
            continue
        # URL detail: terakhir kali ](http...) yang muncul sebelum penutup blok.
        url_match = re.search(r']\\((https?://[^)]+)\\)', block)
        url = url_match.group(1).rstrip(".,") if url_match else None
        # Nama toko: teks segera setelah gambar badge Official Store.
        shop_match = _SHOP_RE.search(block)
        seller = shop_match.group(2) if shop_match else None
        if seller in {"search", "discovery", "p", "etalase"}:
            seller = None
        # Terjual: angka di antara gambar rating dan kata "terjual".
        sold_match = _SOLD_RE.search(block)
        sold_count = None
        if sold_match:
            sold_count = _to_int(sold_match.group(1) or sold_match.group(2))
        # Rating: angka yang sama dengan sold_count (diperoleh dari pola di atas).
        rating = None
        if sold_match:
            try:
                rating = float(sold_match.group(1) or sold_match.group(2))
            except (TypeError, ValueError):
                rating = None
        # Official Store badge: ada jika blok mengandung gambar badge_os.png.
        is_official = bool(_OFFICIAL_BADGE_RE.search(block)) or None
        records.append(ListingRecord(
            title=title[:500],
            price=price,
            url=url,
            condition=detect_condition(title),  # fallback awal dari judul
            seller=seller,
            is_official_store=is_official,
            sold_count=sold_count,
            rating=rating,
        ))
    return records


def _to_int(val: str | None) -> int | None:
    """Ambil angka dari string seperti '1,234' atau '1.234'."""
    if not val:
        return None
    try:
        return int(val.replace(".", "").replace(",", ""))
    except ValueError:
        return None


_last_jina_request = [0.0]


def _throttle() -> None:
    elapsed = time.monotonic() - _last_jina_request[0]
    if elapsed < 3.5:
        time.sleep(3.5 - elapsed)
    _last_jina_request[0] = time.monotonic()


# ---------------------------------------------------------------------------
# Detail page fetch
# ---------------------------------------------------------------------------
# Sekarang detail page diambil dengan HTTP Request biasa, bukan lewat Jina.
# Karena Tokopedia justru lebih suka mengembalikan HTML lengkap ke UA browser
# asli — ini jauh lebih cepat dan stabil daripada proxy rendering.
_DETAIL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}


def _fetch_detail(url: str, client: httpx.Client) -> str:
    try:
        resp = client.get(url, headers=_DETAIL_HEADERS, timeout=30)
        if resp.status_code != 200:
            raise ScraperError(f"Detail fetch failed: HTTP {resp.status_code}")
        return resp.text
    except Exception as exc:
        raise ScraperError(f"Detail fetch error: {exc}") from exc


class TokopediaScraper(Scraper):
    source = "tokopedia"

    def __init__(self, timeout: int = 30, pages: int = 2, max_variants: int = 5,
                 max_records: int = 500, request_delay: float = 3.5,
                 fetch_details: bool = True, max_details: int = 50):
        super().__init__(timeout)
        self.pages = max(1, pages)
        self.max_variants = max(1, max_variants)
        self.max_records = max(1, max_records)
        self.request_delay = max(0.0, request_delay)
        self.fetch_details = fetch_details
        # Batas jumlah detail per query. Setengah menit per 40 detail dikira
        # aman untuk dijadwalkan tiap 15 menit tanpa kena rate limit.
        self.max_details = max(0, max_details)

    def _jina_search(self, target: str, client: httpx.Client) -> str:
        _throttle()
        # Use a separate client with Jina UA to avoid potential blocks
        jina_client = httpx.Client(timeout=max(self.timeout, 90), headers={"User-Agent": JINA_UA})
        try:
            url = _JINA_URL.format(target)
            resp = jina_client.get(url)
        finally:
            jina_client.close()
        if resp.status_code != 200:
            raise ScraperError(f"Tokopedia search request gagal: HTTP {resp.status_code}")
        return resp.text

    def fetch(self, query: str) -> list[ListingRecord]:
        records: list[ListingRecord] = []
        seen: set[str] = set()
        component_type = component_type_from_query(query)
        variants = query_variants(query, max_variants=self.max_variants)

        with self._client({"User-Agent": BROWSER_UA}) as client:
            # ---- Tahap 1: ambil metadata dasar dari halaman pencarian (via Jina) ----
            for variant in variants:
                for page in range(1, self.pages + 1):
                    target = (
                        f"https://www.tokopedia.com/search?st=product&q={quote(variant)}"
                        f"&page={page}"
                    )
                    try:
                        body = self._jina_search(target, client)
                    except ScraperError:
                        if records:
                            continue  # lanjutkan variant lain bila ada hasil
                        raise
                    for record in _parse_blocks(body, query=query,
                                                component_type=component_type):
                        key = (record.url or record.title.lower())
                        if key in seen:
                            continue
                        seen.add(key)
                        records.append(record)
                    if len(records) >= self.max_records:
                        break
                if len(records) >= self.max_records:
                    break

            # ---- Tahap 2: enrich dengan data dari halaman detail ----
            if self.fetch_details:
                enriched = 0
                kept: list[ListingRecord] = []
                for record in records:
                    if enriched >= self.max_details or not record.url:
                        kept.append(record)
                        continue
                    detail_html = _fetch_detail(record.url, client)
                    if looks_like_dead_listing(detail_html):
                        # Listing sudah tidak ada (410/404) — tidak relevan sebagai
                        # pembanding harga. Buang sepenuhnya.
                        continue
                    info = extract_detail(detail_html)
                    enriched += 1

                    # Tulis ulang field yang kita ketahui pasti lebih akurat
                    # daripada yang diambil dari judul saja.
                    record.description = info.get("description")
                    if info.get("condition_source") == "Bekas":
                        record.condition = "second"
                    elif info.get("condition_source") == "Baru":
                        record.condition = "new"
                    record.seller = info.get("seller")
                    record.sold_count = info.get("sold_count")
                    record.review_count = info.get("review_count")
                    record.rating = info.get("rating")
                    record.category_name = info.get("category_name")
                    record.shop_active = info.get("shop_active")

                    # Tambahkan sinyal toko resmi dari pencarian Jina (kalau ada)
                    # sebagai backup pada field is_official_store.
                    # TODO: bisa juga parsing badge dari HTML detail bila perlu.
                    kept.append(record)
                records = kept

        # ---- Tahap 3: filter listing ex-mining (HARD REJECT) ----
        filtered: list[ListingRecord] = []
        for record in records:
            # Ek-mining: deskripsi harus diperiksa, bukan hanya judul
            verdict = assess_listing(record.title, record.description,
                                     record.spec_text)
            if not verdict.is_acceptable:
                if verdict.is_ex_mining:
                    # Tandai alasan supaya bisa di-log
                    record.quality_notes.append(f"rejected:{verdict.reject_reason}")
                    continue  # buang total, bukan hanya skip
                continue
            if verdict.usage_context:
                record.quality_notes.append(f"usage:{verdict.usage_context}")
            if verdict.condition_hint and not record.condition:
                record.condition = verdict.condition_hint
            filtered.append(record)
        return filtered[: self.max_records]


__all__ = [
    "TokopediaScraper",
]