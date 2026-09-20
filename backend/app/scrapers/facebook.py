import csv
import re
from pathlib import Path
from urllib.parse import quote

from .base import ListingRecord, Scraper, ScraperError
from ..services.listing_quality import assess_listing
from ..services.parsing import parse_price

# CSV hasil scraper Facebook (worl-tools) punya kolom yang jauh lebih kaya
# daripada HTML marketplace yang sedang login-wall. Kita utamakan CSV karena
# di dalamnya sudah ada `description` — kunci untuk mendeteksi kondisi asli
# ("like new", "pemakaian 1 tahun") dan menolak "ex mining".
_DEFAULT_CSV_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

_CSV_PRICE_RE = re.compile(r"[\d][\d.,]*")


def _csv_price_to_int(value: str, unit_hint: str = "") -> int | None:
    """Konversi harga CSV ("IDR9,300,000") ke integer rupiah.

    CSV Facebook memakai format "IDR9,300,000" — koma adalah pemisah ribuan,
    jadi harus dibuang sebelum jadi integer. Kalau kolom price_rp kosong
    (sering terjadi), kita fallback ke price_text.
    """
    raw = (value or "").strip()
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None
    amount = int(digits)
    # Kalau kolom teks menyebut "jt"/"juta", kalikan 1_000_000.
    hint = (unit_hint or "").lower()
    if "jt" in hint or "juta" in hint:
        amount *= 1_000_000
    return amount if amount > 0 else None


def _parse_price_cell(row: dict) -> int | None:
    for key in ("price_rp", "price"):
        value = (row.get(key) or "").strip()
        if value:
            parsed = _csv_price_to_int(value)
            if parsed:
                return parsed
    text = (row.get("price_text") or "").strip()
    if text:
        parsed = parse_price(text) or _csv_price_to_int(text, unit_hint=text)
        if parsed:
            return parsed
    return None


def _iter_csv_rows(paths: list[Path], query: str | None = None):
    """Baca baris CSV Facebook, filter kasar berdasarkan keyword bila diminta."""
    keyword = (query or "").strip().lower()
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if keyword:
                    haystack = " ".join(
                        str(row.get(k) or "")
                        for k in ("name", "description", "keyword")
                    ).lower()
                    if keyword not in haystack:
                        continue
                yield row


class FacebookMarketplaceScraper(Scraper):
    source = "facebook_marketplace"

    def __init__(self, cookie: str = "", timeout: int = 30, csv_dir: str | Path | None = None,
                 use_csv: bool = True, max_records: int = 500):
        super().__init__(timeout)
        self.cookie = cookie
        self.csv_dir = Path(csv_dir) if csv_dir else _DEFAULT_CSV_DIR
        self.use_csv = use_csv
        self.max_records = max(1, max_records)

    # -- Sumber 1: CSV hasil scraper (punya deskripsi) ----------------------
    def _fetch_from_csv(self, query: str) -> list[ListingRecord]:
        paths = sorted(self.csv_dir.glob("facebook_*.csv"))
        if not paths:
            return []
        records: list[ListingRecord] = []
        seen: set[str] = set()
        for row in _iter_csv_rows(paths, query):
            title = (row.get("name") or "").strip()
            if not title:
                continue
            price = _parse_price_cell(row)
            url = (row.get("url") or "").strip() or None
            description = (row.get("description") or "").strip() or None
            seller = (row.get("author") or "").strip() or None
            key = (url or f"{title}|{price}").lower()
            if key in seen:
                continue
            seen.add(key)
            # Item Facebook "description" mengemban isi utama (sering identik
            # dengan judul tapi kerap memuat detail kondisi tambahan).
            records.append(ListingRecord(
                title=title[:500],
                price=price,
                url=url,
                description=description,
                seller=seller,
                condition="second",  # Facebook Marketplace = pasar bekas
                condition_source="Bekas",
            ))
            if len(records) >= self.max_records:
                break
        return records

    # -- Sumber 2: HTML live (perlu cookie) --------------------------------
    def _fetch_from_html(self, query: str) -> list[ListingRecord]:
        url = f"https://www.facebook.com/marketplace/indonesia/search?query={quote(query)}"
        headers = {"Cookie": self.cookie} if self.cookie else {}
        # ponytail: UA bot eksplisit khusus FB — UA browser malah dapat HTTP 400
        # (tes 23 Aug 2026); bot-UA dapat halaman login-wall yang bisa dideteksi.
        headers.setdefault("User-Agent", "WorthGaBangBot/1.0 (+scheduled-catalog)")
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        try:
            with self._client(headers) as client:
                response = client.get(url)
                response.raise_for_status()
        except Exception as exc:
            raise ScraperError(f"Facebook Marketplace request gagal: {exc}") from exc
        body = response.text.lower()
        if any(marker in body for marker in ("login", "checkpoint", "security check", "temporarily blocked")):
            raise ScraperError("Facebook Marketplace membutuhkan sesi/cookie yang valid")
        records: list[ListingRecord] = []
        for match in re.finditer(
            r"(?P<price>Rp\s*[\d.,]+).{0,300}?(?P<title>[^<>\n]{8,180})",
            response.text,
            re.IGNORECASE | re.DOTALL,
        ):
            price = parse_price(match.group("price"))
            title = re.sub(r"\s+", " ", match.group("title")).strip()
            if price and title:
                records.append(ListingRecord(
                    title=title, price=price, condition="second", condition_source="Bekas"
                ))
        return records

    def fetch(self, query: str) -> list[ListingRecord]:
        records: list[ListingRecord] = []
        error: Exception | None = None

        if self.use_csv:
            records = self._fetch_from_csv(query)

        if not records:
            try:
                records = self._fetch_from_html(query)
            except ScraperError as exc:
                error = exc

        if not records:
            if error:
                raise error
            raise ScraperError("Facebook Marketplace tidak mengembalikan listing yang bisa diparse")

        # Buang listing ex-mining — deskripsi ikut diperiksa, bukan judul saja.
        filtered: list[ListingRecord] = []
        for record in records:
            verdict = assess_listing(record.title, record.description, record.spec_text)
            if not verdict.is_acceptable:
                continue
            if verdict.usage_context:
                record.quality_notes.append(f"usage:{verdict.usage_context}")
            filtered.append(record)
        return filtered[: self.max_records]
