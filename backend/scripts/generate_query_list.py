"""Generate query list untuk scraper dari dataset PC parts (pc-part-dataset)
+ series laptop populer di pasar Indonesia.

Sumber dataset: https://github.com/docyx/pc-part-dataset (PCPartPicker scrape,
66.778 part, CC / edukatif) — folder pc-part-dataset/data/json/.

Output:
- backend/app/data/query_list.json  -> sumber kebenaran query
- backend/.env SCRAPE_QUERIES       -> dipakai config.py

Aturan pemilihan (biar query tetap segelintir tapi mewakili pasar second ID):
- GPU: chipset NVIDIA RTX/GTX & AMD RX generasi 20/30/40/50 dan RX 6xxx/7xxx
  yang umum dijual bekas, plus varian Ti/Super yang punya volume pasar.
- CPU: Ryzen 3000-9000 & Core i5/i7 gen 10th-14th yang laris second.
- Laptop: brand x series gaming/populer + kombinasi CPU generik.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "pc-part-dataset" / "data" / "json"

# ---- GPU dari dataset -------------------------------------------------------
gpus = json.load(open(DATA / "video-card.json", encoding="utf-8"))
chipsets = {}
for item in gpus:
    chip = (item.get("chipset") or "").strip().lower()
    if not chip:
        continue
    chip = re.sub(r"\s*\d+\s*gb$", "", chip)
    chip = re.sub(r"\s*lhr$", "", chip)
    chipsets[chip] = chipsets.get(chip, 0) + 1

def _shorten(chip: str) -> str | None:
    # "geforce rtx 3060 ti" -> "RTX 3060 Ti"; buang prefix vendor
    m = re.search(r"(rtx|gtx)\s*(\d{3,4})(\s*(?:ti|super))?", chip)
    if m:
        variant = (m.group(3) or "").strip()
        num = m.group(2)
        gen = int(num[0])
        if m.group(1) == "rtx" and gen in {20, 30, 40, 50}:
            return f"RTX {num}{(' ' + variant.title()) if variant else ''}"
        if m.group(1) == "gtx" and gen in {10, 16}:
            return f"GTX {num}{(' ' + variant.title()) if variant else ''}"
        return None
    m = re.search(r"radeon rx\s*(\d{4})\s*(xt)?", chip)
    if m:
        return f"RX {m.group(1)}{(' XT') if m.group(2) else ''}"
    return None

gpu_queries: dict[str, int] = {}
for chip, count in chipsets.items():
    short = _shorten(chip)
    if short:
        gpu_queries[short] = gpu_queries.get(short, 0) + count

# ambil GPU dengan >=5 listing di dataset (cukup populer) + wajib-haves
popular_gpus = sorted((q for q, c in gpu_queries.items() if c >= 8))
MUST_GPU = ["RTX 3050", "RTX 3060", "RTX 3060 Ti", "RTX 3070", "RTX 4060",
            "RTX 4060 Ti", "RTX 4070", "RX 6600", "RX 6600 XT", "RX 6700 XT"]
all_gpus = sorted(set(popular_gpus) | set(MUST_GPU))

# ---- CPU dari dataset ------------------------------------------------------
cpus = json.load(open(DATA / "cpu.json", encoding="utf-8"))
cpu_queries: set[str] = set()
for item in cpus:
    name = (item.get("name") or "").strip()
    m = re.match(r"AMD Ryzen\s*([3579])\s*((?:9|7|5)?\d{4})(?:X3D|XT|G|T|GE|GT|E|F|HX|HS)?", name)
    if m:
        cpu_queries.add(f"Ryzen {m.group(1)} {m.group(2)}")
    m = re.match(r"Intel Core i([3579])-((?:10|11|12|13|14)\d{3,4})(?:KF|K|F|T)?", name)
    if m:
        cpu_queries.add(f"Core i{m.group(1)} {m.group(2)}")

# batasi ke model yang laris di pasar second Indonesia
CPU_WHITELIST = (
    "Ryzen 5 5600", "Ryzen 5 7600", "Ryzen 7 5700X", "Ryzen 7 5800X",
    "Ryzen 7 7700", "Ryzen 5 3600", "Ryzen 5 5500",
    "Core i5 12400", "Core i5 13400", "Core i5 11400", "Core i5 10400",
    "Core i7 12700", "Core i7 13700", "Core i7 11700",
)
cpu_final = [q for q in CPU_WHITELIST if q in cpu_queries] or sorted(cpu_queries)

# ---- Laptop: brand x series (pasar Indonesia) ------------------------------
LAPTOP_QUERIES = [
    "ASUS ROG", "ASUS TUF Gaming", "ASUS Vivobook", "ASUS Zenbook",
    "Lenovo Legion", "Lenovo LOQ", "Lenovo IdeaPad", "Lenovo ThinkPad",
    "Acer Nitro", "Acer Predator", "Acer Aspire", "Acer Swift",
    "MSI Katana", "MSI GF63", "MSI Modern", "MSI Cyborg",
    "HP Victus", "HP Omen", "HP Pavilion", "Pavilion Gaming",
    "Dell G15", "Alienware", "Gigabyte Aorus", "Gigabyte G5",
    "Axioo Pongo", "Advan Workpro", "laptop Core i5", "laptop Ryzen 5",
]

query_data = {
    "_meta": {
        "source": "https://github.com/docyx/pc-part-dataset + kurasi pasar second Indonesia",
        "generated": "2026-08-23",
        "note": "GPU/CPU diekstrak otomatis dari dataset; laptop dikurasi manual.",
    },
    "gpu": all_gpus,
    "cpu": cpu_final,
    "laptop": LAPTOP_QUERIES,
}

out_dir = Path(__file__).resolve().parents[1] / "app" / "data"
out_dir.mkdir(exist_ok=True)
out_file = out_dir / "query_list.json"
out_file.write_text(json.dumps(query_data, indent=2), encoding="utf-8")

flat = all_gpus + cpu_final + LAPTOP_QUERIES
env_line = "SCRAPE_QUERIES=" + ",".join(flat) + "\n"
(ROOT / "backend" / ".env").write_text(env_line, encoding="utf-8")
(ROOT / "backend" / ".env.example").write_text(
    "# Salin jadi .env. Query list lengkap digenerate oleh scripts/generate_query_list.py\n"
    + env_line,
    encoding="utf-8",
)

print(f"GPU queries : {len(all_gpus)}")
print(f"CPU queries : {len(cpu_final)}")
print(f"Laptop      : {len(LAPTOP_QUERIES)}")
print(f"TOTAL       : {len(flat)}")
print("tersimpan:", out_file)
