from dataclasses import dataclass
from typing import Optional

import httpx


class ScraperError(RuntimeError):
    pass


@dataclass
class ListingRecord:
    title: str
    price: Optional[int]
    url: Optional[str] = None
    spec_text: Optional[str] = None
    category: Optional[str] = None
    condition: Optional[str] = None


class Scraper:
    source: str

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def fetch(self, query: str) -> list[ListingRecord]:
        raise NotImplementedError

    def _client(self, headers: Optional[dict[str, str]] = None) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", **(headers or {})},
        )

