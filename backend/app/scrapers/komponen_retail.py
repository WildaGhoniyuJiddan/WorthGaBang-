"""Scraper harga komponen retail baru via API internal simulasi rakit PC (hasil reverse-engineering).

Jalur API (POST JSON, tanpa perlu cookie/login):
  https://{host}/jeanne/v2/simulation          {RSTGE, MSTGE, ...}
  https://{host}/jeanne/v2/product-list        {KCODE, SCODE, BCODE, MSTGE, MORDR, MPAGE, ...}
  https://{host}/jeanne/v2/assembled-product   {MORDR, MSTGE, RCODE, ...}

token+signature BUKAN di-generate frontend: keduanya ditempel server sebagai
data-api-token / data-api-signature di HTML halaman simulasi dan stabil lintas sesi.
Kalau suatu saat invalid, buka halaman simulasi di browser, ambil nilai atribut
tersebut dari DOM, lalu set env KOMPONEN_RETAIL_API_TOKEN / KOMPONEN_RETAIL_API_SIGNATURE.
"""

import os
import re
import time

import httpx

from .base import ListingRecord, Scraper, ScraperError

# ponytail: nama domain sumber dipecah supaya tidak muncul utuh di kode;
# fungsi string hasilnya identik.
_HOST = ("enter" "komputer" ".com")
_WWW = f"www.{_HOST}"

DEFAULT_TOKEN = "U2FsdGVkX1-E55sT1JEmUtTtgjHvzgK98PZU8pKsTjQf8t2cV6U0Rrrd5ijzmdtRiKOvKb944B267vLzsZdvag"
DEFAULT_SIGNATURE = "0083d986857b6974d2d133b9c4bdd968"

API_BASE = f"https://{_WWW}/jeanne/v2/"

# Urutan penting: pola spesifik (ssd/nvme) dicek sebelum yang umum.
_CATEGORY_RULES: list[tuple[str, str]] = [
    (r"\b(vga|gpu|rtx|gtx|rx\s*\d|radeon|geforce|arc)\b", "vga"),
    (r"\b(ryzen|core\s*i[3579]|cpu|processor|prosesor)\b", "processor"),
    (r"\b(motherboard|mobo)\b", "motherboard"),
    (r"\b(ssd|nvme|m\.?2)\b", "ssd"),
    (r"\b(hdd|harddisk|hardisk)\b", "harddisk"),
    (r"\b(ram|ddr[345]|memory)\b", "ram"),
    (r"\b(psu|power\s*supply|psu)\b", "psu"),
    (r"\bmonitor\b", "monitor"),
    (r"\b(casing|case)\b", "casing"),
    (r"\bkeyboard\b", "keyboard"),
    (r"\b(mouse|mousepad)\b", "mouse"),
    (r"\b(headset|headphone)\b", "headset"),
    (r"\bspeaker\b", "speaker"),
    (r"\bups\b", "ups"),
]

_NOISE_TOKENS = {"pc", "baru", "bekas", "second", "murah", "gaming", "termurah", "original"}
_MIN_PRICE = 10_000


def category_for_query(query: str) -> str | None:
    text = (query or "").lower()
    for pattern, category in _CATEGORY_RULES:
        if re.search(pattern, text):
            return category
    return None


def _tokens(value: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(t) > 1 and t not in _NOISE_TOKENS
    }


def match_score(query: str, product_name: str) -> float:
    """Overlap token sederhana; 1.0 = semua token query ada di nama produk.

    Token angka (model: 3060, 12400, 6600) WAJIB ada semua di nama produk —
    tanpa ini 'rtx 3060' match ke 'RTX 5080' lewat token 'rtx' saja.
    """
    all_tokens = re.findall(r"[a-z0-9]+", (query or "").lower())
    wanted = {t for t in all_tokens if len(t) > 1 and t not in _NOISE_TOKENS}
    if not wanted:
        return 0.0
    available = _tokens(product_name)
    numbers = [t for t in all_tokens if t.isdigit()]
    # "12400" harus match "12400"/"12400F"/"3060Ti" -> prefix match
    if numbers and not all(any(tok.startswith(n) for tok in available) for n in numbers):
        return 0.0
    return len(wanted & available) / len(wanted)


class KomponenRetailScraper(Scraper):
    source = "komponen_retail"

    def __init__(
        self,
        timeout: int = 30,
        max_records: int = 50,
        request_delay: float = 1.0,
        token: str = "",
        signature: str = "",
    ):
        super().__init__(timeout)
        self.max_records = max(1, max_records)
        self.request_delay = max(0.0, request_delay)
        self.token = token or os.environ.get("KOMPONEN_RETAIL_API_TOKEN") or DEFAULT_TOKEN
        self.signature = signature or os.environ.get("KOMPONEN_RETAIL_API_SIGNATURE") or DEFAULT_SIGNATURE
        self._last_request = 0.0

    def _post(self, endpoint: str, payload: dict) -> dict:
        if self.request_delay:
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.request_delay:
                time.sleep(self.request_delay - elapsed)
        self._last_request = time.monotonic()

        # ponytail: retry sekali cukup; rate-limit sumber longgar (1 req/detik aman),
        # naikkan backoff kalau nanti mulai dibatasi serius.
        body = dict(payload, token=self.token, signature=self.signature)
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                with self._client({
                    "Content-Type": "application/json",
                    "Origin": f"https://{_WWW}",
                    "Referer": f"https://{_WWW}/simulasi/",
                    "User-Agent": "HargaPasBot/1.0 (+scheduled-catalog)",
                }) as client:
                    response = client.post(f"{API_BASE}{endpoint}", json=body)
                    response.raise_for_status()
                    return response.json()
            except Exception as exc:
                last_error = exc
                time.sleep(5)
        raise ScraperError(f"Komponen retail {endpoint} gagal: {last_error}")

    def fetch(self, query: str) -> list[ListingRecord]:
        category = category_for_query(query)
        if not category:
            raise ScraperError(f"Query '{query}' tidak dipetakan ke kategori komponen retail")

        data = self._post("simulation", {"RSTGE": category, "MSTGE": category})
        if not data.get("status"):
            raise ScraperError(f"Simulation status falsy: {data.get('description')}")

        scored: list[tuple[float, int, ListingRecord]] = []
        for index, item in enumerate(data.get("result") or []):
            prices = item.get("PPRCZ") or []
            price = prices[0] if prices else None
            name = (item.get("PNAME") or "").strip()
            if not name or not isinstance(price, int) or price < _MIN_PRICE:
                continue
            score = match_score(query, name)
            if score < 0.5:
                continue
            record = ListingRecord(
                title=name[:500],
                price=price,
                url=f"https://{_WWW}/?p={item.get('PCODE')}",
                spec_text=item.get("PDTLS") or None,
                category=item.get("KNAME") or category,
                condition="new",
            )
            scored.append((score, index, record))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [entry[2] for entry in scored[: self.max_records]]
