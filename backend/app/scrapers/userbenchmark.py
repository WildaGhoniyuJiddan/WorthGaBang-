"""Scraper skor benchmark UserBenchmark via r.jina.ai.

UserBenchmark blok akses langsung non-browser: subdomain kategori
(cpu/gpu/ssd/hdd/ram.userbenchmark.com) redirect ke halaman captcha
"click the green human". Jalur yang lolos: render via r.jina.ai
(pola sama dengan scraper Tokopedia).

Yang diambil per model komponen:
  - benchmark_score : "Average Bench" persen (0-100), indeks performa global
  - samples         : jumlah sampel user ("Based on N user benchmarks")
  - rank            : posisi di kategori ("37 th of 453")
  - price_usd       : harga referensi Amazon/Ebay kalau tersedia

Catatan kredibilitas: skor UserBenchmark kontroversial (metodologi
non-transparent, bias vendor) — pakai sebagai sinyal pelengkap, bukan
satu-satunya anchor performa.
"""

import re
import time

import httpx

from .base import ListingRecord, Scraper, ScraperError

JINA_BASE = "https://r.jina.ai/"
_UA_NON_BROWSER = "WorthGaBangBot/1.0 (+benchmark-catalog)"

# ponytail: cache ID statis hasil scrape manual; regenerate berkala via cron
# kalau model baru dirasa perlu. Upgrade: parse halaman list per kategori.
_KNOWN_IDS = {
    # gpu
    ("gpu", "rtx4060ti"): 4149,
    ("gpu", "rtx4060"): 4150,
    # cpu
    ("cpu", "ryzen55600x"): 4084,
}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "x"


class UserBenchmarkScraper(Scraper):
    source = "userbenchmark"

    def __init__(self, timeout: int = 30, request_delay: float = 4.0):
        super().__init__(timeout)
        self.request_delay = request_delay
        self._last_request = 0.0

    def _get(self, url: str) -> str:
        if self.request_delay:
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.request_delay:
                time.sleep(self.request_delay - elapsed)
        self._last_request = time.monotonic()
        try:
            with self._client({"User-Agent": _UA_NON_BROWSER}) as client:
                response = client.get(f"{JINA_BASE}{url}")
                response.raise_for_status()
                return response.text
        except Exception as exc:
            raise ScraperError(f"userbenchmark fetch gagal: {exc}") from exc

    def fetch_model(self, component_type: str, model: str) -> dict:
        """Skor benchmark 1 model. Return {} kalau halaman tidak ditemukan."""
        component_type = component_type.lower()
        key = _sq(model)
        page_id = _KNOWN_IDS.get((component_type, key))
        if not page_id:
            return {}
        host = f"{component_type}.userbenchmark.com"
        text = self._get(f"https://{host}/{_slugify(model)}/Rating/{page_id}")

        result: dict = {"component_type": component_type, "model": model}
        m = re.search(r"Average Bench:\s*([\d.]+)%", text)
        if m:
            result["benchmark_score"] = float(m.group(1))
        m = re.search(r"\((\d+)\w{0,2} of (\d+)\)", text)
        if m:
            result["rank"] = int(m.group(1))
            result["category_total"] = int(m.group(2))
        m = re.search(r"Based on ([\d,]+) user benchmarks?", text)
        if m:
            result["samples"] = int(m.group(1).replace(",", ""))
        m = re.search(r"\[\$(\d+(?:,\d{3})*)\]", text)
        if m:
            result["price_usd"] = int(m.group(1).replace(",", ""))
        return result if "benchmark_score" in result else {}

    def fetch(self, query: str) -> list[ListingRecord]:
        """Antarmuka Scraper standar; query diabaikan (pakai fetch_model)."""
        return []


def _sq(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())
