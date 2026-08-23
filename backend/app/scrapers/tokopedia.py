import re
from urllib.parse import quote

from .base import ListingRecord, Scraper, ScraperError
from ..services.parsing import parse_price


class TokopediaScraper(Scraper):
    source = "tokopedia"

    def fetch(self, query: str) -> list[ListingRecord]:
        target = f"https://www.tokopedia.com/search?st=product&q={quote(query)}"
        reader_url = f"https://r.jina.ai/http://{target.removeprefix('https://')}"
        try:
            with self._client() as client:
                response = client.get(reader_url)
                response.raise_for_status()
        except Exception as exc:
            raise ScraperError(f"Tokopedia request gagal: {exc}") from exc

        records: list[ListingRecord] = []
        lines = [line.strip() for line in response.text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            price = parse_price(line)
            if not price:
                continue
            title = re.sub(r"^[-*\d.)\s]+", "", line)
            title = re.sub(r"\s+", " ", title).strip()
            if len(title) < 4 or title.lower().startswith("rp"):
                continue
            url = None
            for nearby in lines[max(0, index - 2): index + 3]:
                match = re.search(r"https?://[^\s)]+", nearby)
                if match and "tokopedia.com" in match.group(0):
                    url = match.group(0).rstrip(".,")
                    break
            records.append(ListingRecord(title=title[:500], price=price, url=url))
        if not records:
            raise ScraperError("Tokopedia tidak mengembalikan listing yang bisa diparse")
        return records[:100]

