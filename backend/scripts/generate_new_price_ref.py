"""Gabungkan buildcores-open-db (nama chipset/series, tanpa harga) + docyx
pc-part-dataset (harga USD street) jadi satu katalog referensi harga baru.

Output: backend/app/data/new_price_reference.json
  { "gpu": {"rtx 3060": usd}, "cpu": {...} }
Konversi USD->IDR dilakukan saat ingest analyze lewat config USD_TO_IDR.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BC = ROOT / "buildcores-open-db" / "open-db"
PC = ROOT / "pc-part-dataset" / "data" / "json"

# ---- 1. GPU: nama chipset dari buildcores (3835 kartu), harga dari docyx ----
chipsets: set[str] = set()
for f in BC.glob("GPU/*.json"):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    chip = (d.get("chipset") or "").strip()
    if chip:
        chipsets.add(chip)
print("buildcores GPU chipsets:", len(chipsets))

def norm_gpu(name: str) -> str | None:
    n = name.lower()
    m = re.search(r"(rtx|gtx)\s*(\d{3,4})\s*(ti|super)?", n)
    if m:
        gen = int(m.group(2)[0])
        ok = ("rtx" == m.group(1) and gen in {2, 3, 4, 5}) or ("gtx" == m.group(1) and gen in {1})
        if not ok:
            return None
        return f"{m.group(1)} {m.group(2)}{(' ' + m.group(3)) if m.group(3) else ''}"
    m = re.search(r"radeon rx\s*(\d{4})\s*(xt)?", n)
    if m and m.group(1)[0] in "5679":
        return f"rx {m.group(1)}{(' xt') if m.group(2) else ''}"
    return None

gpu_usd: dict[str, float] = {}
for item in json.load(open(PC / "video-card.json", encoding="utf-8")):
    price = item.get("price")
    key = norm_gpu(item.get("chipset") or "")
    if price and key:
        cur = gpu_usd.get(key)
        if cur is None or price < cur:  # pakai harga termurah = street price lower bound
            gpu_usd[key] = float(price)
print("gpu dengan harga:", len(gpu_usd))

# ---- 2. CPU: buildcores metadata.name -> harga dari docyx cpu.json ----------
bc_cpus: set[str] = set()
for f in BC.glob("CPU/*.json"):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    name = ((d.get("metadata") or {}).get("name") or "").strip()
    if name:
        bc_cpus.add(name)
print("buildcores CPU names:", len(bc_cpus))

def norm_cpu(name: str) -> str | None:
    n = name.lower().replace("-", " ")
    m = re.search(r"ryzen\s*([3579])\s*((?:9\d{3}|[357]\d{3}))", n)
    if m:
        return f"ryzen {m.group(1)} {m.group(2)}"
    m = re.search(r"core i([3579])-?((?:10|11|12|13|14)\d{3})", n)
    if m:
        return f"core i{m.group(1)} {m.group(2)}"
    return None

cpu_usd: dict[str, float] = {}
for item in json.load(open(PC / "cpu.json", encoding="utf-8")):
    price = item.get("price")
    key = norm_cpu(item.get("name") or "")
    if price and key:
        cur = cpu_usd.get(key)
        if cur is None or price < cur:
            cpu_usd[key] = float(price)
print("cpu dengan harga:", len(cpu_usd))

out = {
    "_meta": {
        "sources": [
            "https://github.com/buildcores/buildcores-open-db (nama model, ODC-By)",
            "https://github.com/docyx/pc-part-dataset (USD street price)",
        ],
        "generated": "2026-08-23",
        "note": "Harga = USD street terendah per chipset; konversi IDR di runtime.",
    },
    "gpu": dict(sorted(gpu_usd.items())),
    "cpu": dict(sorted(cpu_usd.items())),
}
out_path = Path(__file__).resolve().parents[1] / "app" / "data" / "new_price_reference.json"
out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
print("tersimpan:", out_path)
