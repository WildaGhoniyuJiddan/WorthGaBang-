import re
from urllib.parse import quote

from .base import ListingRecord, Scraper, ScraperError
from ..services.parsing import parse_price


class FacebookMarketplaceScraper(Scraper):
    source = "facebook"

    def __init__(self, cookie: str = "", timeout: int = 30):
        super().__init__(timeout)
        self.cookie = cookie

    def fetch(self, query: str) -> list[ListingRecord]:
        url = f"https://www.facebook.com/marketplace/indonesia/search?query={quote(query)}"
        headers = {"Cookie": self.cookie} if self.cookie else {}
        # ponytail: UA bot eksplisit khusus FB — UA browser malah dapat HTTP 400
        # (tes 23 Aug 2026); bot-UA dapat halaman login-wall yang bisa dideteksi.
        headers.setdefault("User-Agent", "HargaPasBot/1.0 (+scheduled-catalog)")
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
        records = []
        for match in re.finditer(r"(?P<price>Rp\s*[\d.,]+).{0,300}?(?P<title>[^<>\n]{8,180})", response.text, re.IGNORECASE | re.DOTALL):
            price = parse_price(match.group("price"))
            title = re.sub(r"\s+", " ", match.group("title")).strip()
            if price and title:
                records.append(ListingRecord(title=title, price=price, condition="second"))
        if not records:
            raise ScraperError("Facebook Marketplace tidak mengembalikan listing yang bisa diparse")
        return records[:100]
