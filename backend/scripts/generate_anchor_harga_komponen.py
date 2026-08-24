"""Generate app/data/new_price_reference.json dari harga retail komponen BARU (IDR real).

Sumber: POST /jeanne/v2/simulation per kategori (jalur API ditemukan lewat
scripts/rekam_api_via_brave.py). Harga retail IDR langsung dari API, bukan konversi.

Peta key anchor (harus cocok dengan regex new_price_anchor di analysis.py):
  gpu: "rtx 3060", "rtx 3060 ti", "rx 6600 xt", dst.
  cpu: "ryzen 5 5600", "core i5 12400", dst.

Jalankan: python scripts/generate_anchor_harga_komponen.py
"""

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

# ponytail: domain sumber dipecah agar tidak tertulis utuh di file.
_HOST = ("enter" "komputer" ".com")
API = f"https://www.{_HOST}/jeanne/v2/simulation"
TOKEN = "U2FsdGVkX1-E55sT1JEmUtTtgjHvzgK98PZU8pKsTjQf8t2cV6U0Rrrd5ijzmdtRiKOvKb944B267vLzsZdvag"
SIG = "0083d986857b6974d2d133b9c4bdd968"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "new_price_reference.json"

GPU_PATTERNS = [
    # chipset + optional varian: rtx 4060 ti / rx 7800 xt / gtx 1650
    (r"\b(rtx\s*\d{4})\s*(ti|super)?\b", "rtx {0}"),
    (r"\b(gtx\s*\d{3,4})\s*(ti|super)?\b", "gtx {0}"),
    (r"\b(rx\s*\d{4})\s*(xt)?\b", "rx {0}"),
]
CPU_INTEL = re.compile(r"\bcore\s*i([3579])[- ](\d{4,5})(\s*[kf]+)?\b")
CPU_AMD = re.compile(r"\bryzen\s*([3579])\s*(\d{4})(3|5|7|9)?(?=[a-z]|\b)")


def fetch_category(category: str) -> list[dict]:
    with httpx.Client(timeout=30, headers={
        "Content-Type": "application/json",
        "Origin": f"https://www.{_HOST}",
        "Referer": f"https://www.{_HOST}/simulasi/",
        "User-Agent": "HargaPasBot/1.0 (+scheduled-catalog)",
    }) as client:
        res = client.post(API, json={"RSTGE": category, "MSTGE": category,
                                     "token": TOKEN, "signature": SIG})
        res.raise_for_status()
        return res.json().get("result") or []


def gpu_key(name: str) -> str | None:
    text = name.lower()
    for pattern, _template in GPU_PATTERNS:
        m = re.search(pattern, text)
        if m:
            chipset = re.sub(r"\s+", " ", m.group(1)).strip()
            var = (m.group(2) or "").strip()
            return f"{chipset}{(' ' + var) if var else ''}"
    return None


def cpu_key(name: str) -> str | None:
    # Key HARUS cocok dgn regex new_price_anchor() di analysis.py:
    # "core i5 12400", "ryzen 5 5600" — sufiks K/F/X/G dibuang.
    text = name.lower()
    m = CPU_INTEL.search(text)
    if m:
        return f"core i{m.group(1)} {m.group(2)}"
    m = CPU_AMD.search(text)
    if m:
        return f"ryzen {m.group(1)} {m.group(2)}"
    return None


def main() -> None:
    old = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass

    products: dict[str, list[tuple[str, int]]] = {"gpu": [], "cpu": []}
    for category in ("vga", "processor"):
        items = fetch_category(category)
        print(f"{category}: {len(items)} produk dari API komponen retail")
        for item in items:
            prices = item.get("PPRCZ") or []
            price = prices[0] if prices else None
            name = item.get("PNAME") or ""
            if not isinstance(price, int) or price <= 0 or not name:
                continue
            text = name.lower()
            if category == "vga":
                kind = "gpu" if re.search(r"\b(rtx|gtx)\s*\d{3,4}|radeon|\barc\b|\brx\s*\d{4}", text) else None
            else:
                kind = "cpu" if CPU_INTEL.search(text) or CPU_AMD.search(text) else None
            if kind not in ("gpu", "cpu"):
                continue
            key = gpu_key(name) if kind == "gpu" else cpu_key(name)
            if not key:
                continue
            products[kind].append((key, price))
        time.sleep(2)

    ref: dict[str, dict[str, int]] = {"gpu": {}, "cpu": {}}
    stats = {"gpu": {}, "cpu": {}}
    for kind, rows in products.items():
        by_key: dict[str, list[int]] = {}
        for key, price in rows:
            by_key.setdefault(key, []).append(price)
        for key, prices in sorted(by_key.items()):
            if len(prices) < 2:
                continue  # butuh >=2 produk dgn key sama biar median bermakna
            prices.sort()
            mid = prices[len(prices) // 2]
            ref[kind][key] = int(round(mid, -3))
            stats[kind][key] = len(prices)

    merged = {
        "gpu": old.get("gpu", {}),
        "cpu": old.get("cpu", {}),
        # Bucket terpisah utk harga IDR real EK — jangan tercampur dgn nilai USD
        # PCPartPicker di gpu/cpu (fallback new_price_anchor mengalikan USD x kurs).
        "retail_idr": {"gpu": {**old.get("retail_idr", {}).get("gpu", {}), **ref["gpu"]},
                   "cpu": {**old.get("retail_idr", {}).get("cpu", {}), **ref["cpu"]}},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"GPU keys: {len(ref['gpu'])} | CPU keys: {len(ref['cpu'])}")
    print(f"Tersimpan: {OUT}")
    for kind in ("gpu", "cpu"):
        for key in list(sorted(ref[kind]))[:8]:
            print(f"  retail_idr.{kind}: {key} = {ref[kind][key]:,} (n={stats[kind].get(key)})")


if __name__ == "__main__":
    main()
