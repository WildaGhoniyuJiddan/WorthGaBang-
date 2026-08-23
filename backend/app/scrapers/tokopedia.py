import re
import time
from urllib.parse import quote

from .base import ListingRecord, Scraper, ScraperError
from ..services.parsing import detect_condition, parse_price

# ponytail: batas bawah harga masuk akal untuk GPU/CPU/laptop; kalau nanti mau
# scrape komponen murah (kabel, fan), turunkan atau jadikan config.
MIN_PLAUSIBLE_PRICE = 100_000

_IMAGE_MD_RE = re.compile(r"!\[Image [^\]]*\]\([^)]*\)")


def _parse_blocks(body: str) -> list[ListingRecord]:
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

    def fetch(self, query: str) -> list[ListingRecord]:
        target = f"https://www.tokopedia.com/search?st=product&q={quote(query)}"
        reader_url = f"https://r.jina.ai/http://{target.removeprefix('https://')}"
        response = None
        for attempt in range(2):
            _throttle()
            try:
                # ponytail: r.jina.ai malah ngeblok UA browser via Cloudflare
                # ("Just a moment..."); UA non-browser yang diterima.
                with self._client({"User-Agent": "HargaPasBot/1.0 (+scheduled-catalog)"}) as client:
                    response = client.get(reader_url)
                    if response.status_code in (403, 429) and attempt == 0:
                        time.sleep(30)
                        continue
                    response.raise_for_status()
                break
            except Exception as exc:
                if attempt == 1:
                    raise ScraperError(f"Tokopedia request gagal: {exc}") from exc

        records = _parse_blocks(response.text)
        if not records:
            raise ScraperError("Tokopedia tidak mengembalikan listing yang bisa diparse")
        return records[:100]
