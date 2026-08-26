"""Scraper harga LAPTOP BARU via API internal Enterkomputer kategori "notebook".

Satu jalur API dengan komponen_retail (jeanne/v2/simulation) tapi kategori
notebook: 800+ unit laptop baru lengkap dengan harga IDR retail. Kondisi dipaksa
"new" — sumber ini khusus harga retail baru.

Dipakai pipeline pengumpulan data Laptop (run_pipeline_laptop).
"""

import re

from .base import ListingRecord, Scraper, ScraperError
from .komponen_retail import DEFAULT_SIGNATURE, DEFAULT_TOKEN, _HOST, _WWW

# ponytail: token/signature sama dengan komponen_retail (server yang sama);
# kalau nanti di-rotate cukup update konstanta di komponen_retail.
_MIN_PRICE = 1_000_000  # laptop baru di bawah 1jt = aksesori/junk

_BRAND_RE = re.compile(
    r"\b(asus|acer|lenovo|msi|hp|dell|axioo|advan|infinix|huawei|apple|"
    r"gigabyte|razer|samsung|xiaomi|honor|lg|fujitsu|toshiba)\b",
    re.IGNORECASE,
)


def _is_laptop_name(name: str) -> bool:
    text = name.lower()
    if any(w in text for w in ("laptop", "notebook", "macbook")):
        return True
    # Banyak listing toko cuma sebut seri ("Lenovo LOQ 15", "ASUS TUF F15").
    return bool(_BRAND_RE.search(text))


class NotebookRetailScraper(Scraper):
    source = "notebook_retail"

    def __init__(self, timeout: int = 30, max_records: int = 2000, request_delay: float = 1.0):
        super().__init__(timeout)
        self.max_records = max(1, max_records)
        self.request_delay = max(0.0, request_delay)

    def fetch(self, query: str = "notebook") -> list[ListingRecord]:
        import time

        if self.request_delay:
            time.sleep(self.request_delay)
        with self._client({
            "Content-Type": "application/json",
            "Origin": f"https://{_WWW}",
            "Referer": f"https://{_WWW}/simulasi/",
            "User-Agent": "HargaPasBot/1.0 (+scheduled-catalog)",
        }) as client:
            response = client.post(
                f"https://{_WWW}/jeanne/v2/simulation",
                json={"RSTGE": "notebook", "MSTGE": "notebook", "token": DEFAULT_TOKEN, "signature": DEFAULT_SIGNATURE},
            )
            response.raise_for_status()
            data = response.json()
        if not data.get("status"):
            raise ScraperError(f"Notebook simulation status falsy: {data.get('description')}")

        records: list[ListingRecord] = []
        seen: set[str] = set()
        for item in data.get("result") or []:
            prices = item.get("PPRCZ") or []
            price = prices[0] if prices else None
            name = (item.get("PNAME") or "").strip()
            brand = (_BRAND_RE.search(name).group(1).title() if _BRAND_RE.search(name) else None)
            if not isinstance(price, int) or price < _MIN_PRICE:
                continue
            # Nama tanpa brand & tanpa kata laptop = aksesori yang lolos kategori
            # (tas, charger, docking) -> buang. Brand saja cukup karena semua
            # produk kategori notebook adalah unit.
            if not brand and not _is_laptop_name(name):
                continue
            key = f"{name.lower()}|{price}"
            if key in seen:
                continue
            seen.add(key)
            records.append(ListingRecord(
                title=name[:500],
                price=price,
                url=f"https://{_HOST}/?p={item.get('PCODE')}",
                spec_text=item.get("PDTLS") or None,
                # kategori DB konsisten dgn pipeline lain: "laptop".
                category="laptop",
                condition="new",
            ))
            if len(records) >= self.max_records:
                break
        if not records:
            raise ScraperError("Notebook retail tidak mengembalikan unit yang bisa diparse")
        return records
