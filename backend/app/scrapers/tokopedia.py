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
_JINA_URL = "https://r.jina.ai/http://{}"

# Strategi: hapus semua sintaks gambar markdown ![alt](url) dari blok, lalu
# parse teks yang sudah bersih. Jina me-render 1 produk seperti:
#   [![Image 1: product-image](img...) Judul Rp6.570.000 ![Image 2: rating](svg...)
#    5.0 2 terjual ![Image 3: shop badge](...badge_os.png...) Duta Mandiri Infokom
#    Jakarta Pusat](https://www.tokopedia.com/slug/product-url?...)
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")          # ![alt](url)
_DETAIL_URL_RE = re.compile(r"\]\((https?://[^)\s]*tokopedia\.com/[^)\s]*)\)")
_RP_RE = re.compile(r"Rp\s*[\d.]+")
_TITLE_RE = re.compile(r"^(.*?)\s+Rp")
_SOLD_RE = re.compile(r"([\d.]+)\+?\s*terjual", re.IGNORECASE)
_RATING_RE = re.compile(r"\]\([^)]*\)\s+(\d\.\d)\s")          # rating setelah gambar svg
# Seller (versi Official Store): teks antara gambar badge_os dan link detail.
#   ![Image 3: shop badge](...badge_os.png...) Redcomp Jakarta Pusat](https://...
_SELLER_RE = re.compile(r"!\[[^\]]*\]\([^)]*badge_os[^)]*\)\s*([^]\[]+?)\s*\]\(https?://")
# Seller (non-badge): teks setelah "... terjual" sampai link detail penutup blok.
#   ...](svg) 5.0 70+ terjual Plushy Store Tangerang](https://...
_SELLER_AFTER_SOLD_RE = re.compile(r"terjual\s+([^]\[]+?)\s*\]\(https?://")
_BADGE_OS_RE = re.compile(r"badge_os\.png", re.IGNORECASE)


def _split_blocks(body: str) -> list[str]:
    """Satu blok = satu produk, diawali baris '[![Image N: product-image]'."""
    blocks: list[str] = []
    for line in body.splitlines():
        if line.startswith("[![Image"):
            blocks.append(line)
        elif blocks:
            blocks[-1] += " " + line
    return blocks


def _parse_blocks(body: str, query: str | None = None,
                  component_type: str | None = None) -> list[ListingRecord]:
    records: list[ListingRecord] = []
    for raw in _split_blocks(body):
        detail_match = _DETAIL_URL_RE.search(raw)
        url = detail_match.group(1).rstrip(".,") if detail_match else None
        if url and not url.startswith("https://www.tokopedia.com/"):
            url = None  # link afiliasi/iklan, skip saja detail-nya

        alt_texts = _MD_IMAGE_RE.findall(raw)
        is_official = bool(_BADGE_OS_RE.search(raw))
        # Seller: prefer teks setelah gambar badge_os; fallback teks setelah
        # "... terjual" sebelum link detail penutup blok.
        seller = None
        seller_match = _SELLER_RE.search(raw) or _SELLER_AFTER_SOLD_RE.search(raw)
        if seller_match:
            seller = seller_match.group(1).strip()
        if seller and (len(seller) > 80 or not _BADGE_OS_RE.search(raw)
                       and ("Rp" in seller or "terjual" in seller.lower())):
            seller = None  # match kepanjangan (blok tidak utuh) — abaikan
        if seller in {"search", "discovery", "p", "etalase", "image"}:
            seller = None

        # Bersihkan sintaks gambar -> teks murni: "Judul Rp... 5.0 2 terjual Duta..."
        clean = _MD_IMAGE_RE.sub(" ", raw).strip()
        # Buang prefix link luar (biasanya judul blok sama dengan produk pertama).
        clean = re.sub(r"^\[", "", clean)
        price_match = _RP_RE.search(clean)
        if not price_match:
            continue
        price = parse_price(price_match.group(0))
        if not price or price < MIN_PLAUSIBLE_PRICE:
            continue
        title_match = _TITLE_RE.search(clean)
        title = title_match.group(1).strip() if title_match else None
        if not title or len(title) < 4:
            continue
        if query and component_type and not is_relevant_pc_listing(query, title, component_type):
            continue
        sold_count = None
        rating = None
        sold_match = _SOLD_RE.search(clean)
        if sold_match:
            sold_count = _to_int(sold_match.group(1))
        rating_match = _RATING_RE.search(raw)
        if rating_match:
            try:
                rating = float(rating_match.group(1))
            except ValueError:
                rating = None
        records.append(ListingRecord(
            title=title[:500],
            price=price,
            url=url,
            condition=detect_condition(title),  # fallback awal dari judul
            seller=seller,
            is_official_store=True if is_official else None,
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
                    if info.get("condition_source"):
                        record.condition_source = info["condition_source"]
                    record.seller = info.get("seller") or record.seller
                    record.sold_count = info.get("sold_count") or record.sold_count
                    record.review_count = info.get("review_count")
                    record.rating = info.get("rating") or record.rating
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