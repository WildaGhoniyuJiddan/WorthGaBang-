import re
import time
from urllib.parse import quote

from .base import ListingRecord, Scraper, ScraperError
from ..services.parsing import detect_condition, parse_price
from ..services.relevance import component_type_from_query, is_relevant_pc_listing, query_variants

# ponytail: batas bawah harga masuk akal untuk GPU/CPU/laptop; kalau nanti mau
# scrape komponen murah (kabel, fan), turunkan atau jadikan config.
MIN_PLAUSIBLE_PRICE = 100_000

_IMAGE_MD_RE = re.compile(r"!\[Image [^\]]*\]\([^)]*\)")


def _parse_blocks(body: str, query: str | None = None, component_type: str | None = None) -> list[ListingRecord]:
    # Jina merender 1 produk Tokopedia = 1 blok markdown diawali "[![Image N: ...]".
    records: list[ListingRecord] = []
    blocks: list[str] = []
    for line in body.splitlines():
        if line.startswith("[![Image"):
            blocks.append(line)
        elif blocks:
            blocks[-1] += " " + line
    for block in blocks:
        price_match = re.search(r"Rp\s*[\d.,]+", block)
        if not price_match:
            continue
        price = parse_price(price_match.group(0))
        if not price or price < MIN_PLAUSIBLE_PRICE:
            continue
        title = _IMAGE_MD_RE.sub(" ", block)
        title = title.split("](")[0]
        title = title.split(price_match.group(0))[0]
        title = re.sub(r"\s+", " ", title).strip(" -•[]")
        if len(title) < 4:
            continue
        if query and component_type and not is_relevant_pc_listing(query, title, component_type):
            continue
        url_match = re.search(r"https://www\.tokopedia\.com/[^\s)\"]+", block)
        url = url_match.group(0).rstrip(".,") if url_match else None
        records.append(ListingRecord(
            title=title[:500],
            price=price,
            url=url,
            condition=detect_condition(title),
        ))
    return records


_last_jina_request = [0.0]


def _throttle() -> None:
    elapsed = time.monotonic() - _last_jina_request[0]
    if elapsed < 3.5:
        time.sleep(3.5 - elapsed)
    _last_jina_request[0] = time.monotonic()


class TokopediaScraper(Scraper):
    source = "tokopedia"

    def __init__(self, timeout: int = 30, pages: int = 2, max_variants: int = 5, max_records: int = 500, request_delay: float = 3.5):
        super().__init__(timeout)
        self.pages = max(1, pages)
        self.max_variants = max(1, max_variants)
        self.max_records = max(1, max_records)
        self.request_delay = max(0.0, request_delay)

    def fetch(self, query: str) -> list[ListingRecord]:
        records: list[ListingRecord] = []
        seen: set[str] = set()
        component_type = component_type_from_query(query)
        for variant in query_variants(query, self.max_variants):
            for page in range(1, self.pages + 1):
                target = f"https://www.tokopedia.com/search?st=product&q={quote(variant)}&page={page}"
                reader_url = f"https://r.jina.ai/http://{target.removeprefix('https://')}"
                response = self._request(reader_url)
                parsed = _parse_blocks(response.text, query=variant, component_type=component_type)
                for record in parsed:
                    key = record.url or f"{record.title.lower()}|{record.price}"
                    if key in seen:
                        continue
                    seen.add(key)
                    records.append(record)
                if len(records) >= self.max_records:
                    return records[: self.max_records]
        if not records:
            raise ScraperError("Tokopedia tidak mengembalikan listing yang bisa diparse")
        return records[: self.max_records]

    def _request(self, reader_url: str):
        response = None
        for attempt in range(2):
            if self.request_delay:
                elapsed = time.monotonic() - _last_jina_request[0]
                if elapsed < self.request_delay:
                    time.sleep(self.request_delay - elapsed)
                _last_jina_request[0] = time.monotonic()
            try:
                # r.jina.ai menerima UA non-browser lebih konsisten daripada UA browser.
                with self._client({"User-Agent": "HargaPasBot/1.0 (+scheduled-catalog)"}) as client:
                    response = client.get(reader_url)
                    if response.status_code in (403, 429) and attempt == 0:
                        time.sleep(30)
                        continue
                    response.raise_for_status()
                return response
            except Exception as exc:
                if attempt == 1:
                    raise ScraperError(f"Tokopedia request gagal: {exc}") from exc
        raise ScraperError("Tokopedia request tidak menghasilkan response")
