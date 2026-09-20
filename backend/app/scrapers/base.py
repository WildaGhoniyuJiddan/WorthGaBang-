from dataclasses import dataclass, field
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
    # Deskripsi lengkap produk. Penting untuk mendeteksi kondisi asli
    # ("like new", "pemakaian 1 tahun") dan menolak "ex mining".
    description: Optional[str] = None
    # Nama toko/penjual.
    seller: Optional[str] = None
    # Tokopedia Official Store / distributor resmi -> indikasi barang baru.
    is_official_store: Optional[bool] = None
    sold_count: Optional[int] = None
    rating: Optional[float] = None
    # Kondisi mentah dari label marketplace ("Bekas"/"Baru"), kalau tersedia.
    condition_source: Optional[str] = None
    # Catatan kualitas: alasan listing dibuang atau konteks pemakaian.
    quality_notes: list[str] = field(default_factory=list)


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
