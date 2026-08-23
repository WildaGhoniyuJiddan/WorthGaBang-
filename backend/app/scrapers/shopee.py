import json
import re
from urllib.parse import quote

from .base import ListingRecord, Scraper, ScraperError
from ..services.parsing import parse_price


class ShopeeScraper(Scraper):
    source = "shopee"

    def __init__(self, cookie: str = "", timeout: int = 30):
        super().__init__(timeout)
        self.cookie = cookie

    def fetch(self, query: str) -> list[ListingRecord]:
        url = f"https://shopee.co.id/search?keyword={quote(query)}"
        headers = {"Cookie": self.cookie} if self.cookie else {}
        try:
            with self._client(headers) as client:
                response = client.get(url)
                response.raise_for_status()
        except Exception as exc:
            raise ScraperError(f"Shopee request gagal: {exc}") from exc
        if any(marker in response.text.lower() for marker in ("verify/traffic", "captcha", "403")):
            raise ScraperError("Shopee meminta verifikasi anti-bot; isi SHOPEE_COOKIE atau gunakan ingestion extension")
        return self._parse(response.text)

    def _parse(self, body: str) -> list[ListingRecord]:
        records: list[ListingRecord] = []
        for match in re.finditer(r"(?P<title>[^\n]{8,200}).{0,200}?(?P<price>Rp\s*[\d.,]+)", body, re.IGNORECASE | re.DOTALL):
            title = re.sub(r"\s+", " ", match.group("title")).strip(" -•")
            price = parse_price(match.group("price"))
            if price:
                records.append(ListingRecord(title=title, price=price))
        return records[:100]

