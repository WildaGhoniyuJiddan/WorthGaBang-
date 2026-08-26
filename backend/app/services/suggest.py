"""Autocomplete per section, dua pool kondisi: BARU dan BEKAS.

- condition="baru"  -> katalog retail API Enterkomputer (app/data/retail_catalog.json),
  di-regenerate cron bulanan (jobs.run_monthly_komponen_retail).
- condition="bekas" -> judul + harga listing marketplace second (raw_listings /
  pc_components / laptop_units), dengan filter relevansi anti build-PC.
Tanpa condition -> perilaku lama (gabungan), dipakai mode analisis "any".
"""
import json
import re
from pathlib import Path
from statistics import median

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import LaptopUnit, PCComponent, RawListing
from .relevance import _BUILD_WORDS, is_relevant_pc_listing

_RETAIL_CATALOG = Path(__file__).resolve().parents[1] / "data" / "retail_catalog.json"


def _load_retail() -> dict:
    try:
        return json.loads(_RETAIL_CATALOG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _stokens(text: str) -> set[str]:
    """Token utk pencocokan saran: potongan alfanumerik utuh ('rx6600' tetap satu)."""
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _sq(text: str) -> str:
    """Bentuk squash tanpa spasi/simbol: 'rx 6600' dan 'rx6600' sama."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


# Sinyal judulnya BUKAN komponen lepas (biasanya build PC) — dipakai saat
# mengekstrak harga kanonik RAM/storage supaya harga build tidak meracuni median.
_NOT_STANDALONE_RE = re.compile(
    r"\b(?:pc|rakitan|ryzen|core\s*i?\d?|intel|amd|rtx|gtx|vga|motherboard)\b|rx\s*\d{3,4}",
    re.IGNORECASE,
)

# Judul listing cuma layak jadi saran RAM/storage kalau memang soal itu.
_SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ram": ("ram", "memori", "memory", "sodimm", "so-dimm"),
    "storage": ("ssd", "hdd", "nvme", "harddisk", "hard disk", "m.2", "m2 "),
}


# ponytail: kanonik RAM/storage manual karena agregasi katalog belum bersih;
# ganti dengan pc_components kalau ingestion sudah bisa pisahkan merek.
_CANONICAL: dict[str, list[str]] = {
    "ram": [
        "RAM DDR3 4GB", "RAM DDR3 8GB", "RAM DDR4 4GB", "RAM DDR4 8GB",
        "RAM DDR4 16GB", "RAM DDR4 32GB", "RAM DDR5 8GB", "RAM DDR5 16GB",
        "RAM DDR5 32GB", "RAM Laptop DDR4 8GB",
    ],
    "storage": [
        "SSD SATA 240GB", "SSD SATA 480GB", "SSD SATA 1TB", "SSD NVMe 256GB",
        "SSD NVMe 512GB", "SSD NVMe 1TB", "SSD NVMe 2TB",
        "HDD 1TB", "HDD 2TB",
    ],
}

# Pola deteksi bentuk kanonik dari judul listing apa adanya.
_RAM_RE = re.compile(r"ram|memori|memory|ddr[345]", re.IGNORECASE)
_DDR_RE = re.compile(r"ddr\s*([345])|ddr([345])\s*laptop", re.IGNORECASE)
_GB_RE = re.compile(r"(\d{1,2})\s*gb\b", re.IGNORECASE)
_SSD_RE = re.compile(r"\bssd\b|nvme|m\.?2\b", re.IGNORECASE)
_HDD_RE = re.compile(r"\bhdd\b|harddisk|hard disk", re.IGNORECASE)
_TB_RE = re.compile(r"(\d)\s*tb\b", re.IGNORECASE)

_SECTIONS = set(_CANONICAL) | {"gpu", "cpu", "motherboard", "laptop"}
_MAX_LABEL = 90


def _match_score(label_tokens: set[str], label_sq: str, query_tokens: set[str], query_sq: str) -> int:
    """0 = tidak cocok; makin tinggi makin relevan."""
    if not query_tokens:
        return 0
    if query_tokens <= label_tokens:
        score = 40
    elif query_sq and (label_sq.startswith(query_sq) or query_sq in label_sq):
        score = 30  # squash match: 'rx660'/'ryzen5' cocok 'rx 6600'/'ryzen 5'
    elif all(any(t.startswith(q) for t in label_tokens) for q in query_tokens):
        score = 10  # prefix per-token
    else:
        return 0
    return score


def _norm_key(label: str) -> str:
    """Key dedupe tahan beda urutan kata & duplikat merek ('Lenovo Lenovo X' == 'X Lenovo')."""
    return " ".join(sorted(_stokens(label))) or label.upper()


def _canonical_ram(title: str) -> str | None:
    if not _RAM_RE.search(title):
        return None
    ddr = re.search(r"ddr\s*([345])", title, re.IGNORECASE)
    laptop = bool(re.search(r"laptop|so-dimm|sodimm", title, re.IGNORECASE))
    gb = _GB_RE.search(title)
    if gb:
        size = f"{gb.group(1)}GB"
    else:
        tb = _TB_RE.search(title)
        if not tb:
            return None
        size = f"{int(tb.group(1)) * 1024}GB"
    if ddr:
        return f"RAM Laptop DDR{ddr.group(1)} {size}" if laptop else f"RAM DDR{ddr.group(1)} {size}"
    return f"RAM Laptop {size}" if laptop else None


def _canonical_storage(title: str) -> str | None:
    tb = _TB_RE.search(title)
    gb_match = _GB_RE.search(title)
    size = f"{tb.group(1)}TB" if tb else (f"{gb_match.group(1)}GB" if gb_match else None)
    if not size:
        return None
    if _HDD_RE.search(title):
        return f"HDD {size}"
    if _SSD_RE.search(title):
        nvme = bool(re.search(r"nvme", title, re.IGNORECASE))
        sata = bool(re.search(r"sata", title, re.IGNORECASE))
        if nvme and sata:
            return f"SSD NVMe {size}"  # NVMe disebut spesifik -> prioritas
        if nvme:
            return f"SSD NVMe {size}"
        if sata:
            return f"SSD SATA {size}"
        return f"SSD {size}"
    return None


def _market_prices(db: Session, section: str) -> dict[str, list[int]]:
    """Median harga per bentuk kanonik RAM/storage dari judul listing real."""
    out: dict[str, list[int]] = {}
    if section not in _CANONICAL:
        return out
    canon_fn = _canonical_ram if section == "ram" else _canonical_storage
    rows = db.execute(
        select(RawListing.raw_title, RawListing.raw_price)
        .where(RawListing.category == "pc", RawListing.raw_price.is_not(None), RawListing.raw_price > 50_000)
        .order_by(desc(RawListing.scraped_at)).limit(4000)
    ).all()
    for title, price in rows:
        if _NOT_STANDALONE_RE.search(title or ""):
            continue  # judul build PC -> harganya bukan harga RAM/SSD lepas
        key = canon_fn(title or "")
        if key and price:
            out.setdefault(key, []).append(int(price))
    return out


def _retail_candidates(section: str, query_tokens: set[str], query_sq: str) -> list[dict]:
    """Pool saran kondisi BARU: katalog retail EK (harga retail IDR real)."""
    retail = _load_retail()
    catalog: dict = {}
    if section in ("gpu", "cpu", "motherboard"):
        # gpu/cpu/motherboard: nama produk + harga retail per item.
        for prod in retail.get(section) or []:
            model = (prod.get("model") or "").strip()
            price = prod.get("price")
            if model and isinstance(price, int):
                catalog[model[:90]] = price
    elif section == "ram":
        catalog = dict(retail.get("ram_canonical") or {})
    elif section == "storage":
        catalog = dict(retail.get("storage_canonical") or {})
    candidates: dict[str, tuple[tuple[int, int], int, float | None, str]] = {}

    def add(label: str, price: float | None) -> None:
        label = " ".join(str(label or "").split())
        if not label:
            return
        low = label.lower()
        score = _match_score(_stokens(label), _sq(label), query_tokens, query_sq)
        if score <= 0 and query_tokens:
            return
        key = _norm_key(label)
        rank = (score, 0)
        prev = candidates.get(key)
        if prev is None or rank > prev[0]:
            candidates[key] = (rank, 0, price, label)

    for model, price in catalog.items():
        add(model, float(price))
    ranked = sorted(candidates.values(), key=lambda r: (r[0], -len(r[3])), reverse=True)[:12]
    return [{"label": lb, "samples": 0, "price": round(pr) if pr else None}
            for (_, _), _, pr, lb in ranked]


def suggest_components(db: Session, section: str, q: str, limit: int = 8,
                       condition: str | None = None) -> list[dict]:
    section = (section or "").lower()
    if section not in _SECTIONS:
        return []
    qlow = " ".join((q or "").lower().split())
    cond = (condition or "").lower() or None

    # Pool BARU: murni katalog retail — tanpa listing marketplace.
    if cond == "baru":
        retail = _retail_candidates(section, _stokens(qlow), _sq(qlow))[:limit]
        if retail:
            return retail
        # ponytail: katalog retail belum ada utk section ini (mis. laptop) ->
        # fallback ke pool gabungan DB (unit condition=new dominan);
        # pisahkan beneran per kondisi kalau campuran mulai meracuni.
    cond = None

    query_tokens = _stokens(qlow)
    query_sq = _sq(qlow)
    candidates: dict[str, tuple[tuple[int, int], int, float | None, str]] = {}

    def add(label: str, popularity: int, price: float | None, bonus: int = 0) -> None:
        label = " ".join(str(label or "").split())
        if not label or "http" in label.lower():
            return
        low = label.lower()
        # Section RAM/storage: saran judul harus benar-benar soal RAM/SSD,
        # bukan build PC yang kebetulan mention.
        keywords = _SECTION_KEYWORDS.get(section)
        if keywords:
            if not any(k in low for k in keywords) or _NOT_STANDALONE_RE.search(low):
                return
        elif section == "gpu" and re.search(r"\b(?:frame|bracket|riser|backplate|support)\b", low):
            return  # aksesori VGA, bukan kartunya
        # Filter relevansi seragam utk SEMUA pool (kanonik/katalog/listing):
        # buang aksesori, build PC, dan komponen beda jenis.
        if query_tokens and not is_relevant_pc_listing(qlow, low, section):
            return
        key = _norm_key(label)
        score = _match_score(_stokens(label), _sq(label), query_tokens, query_sq)
        if score <= 0 and query_tokens:
            return
        if len(label) > _MAX_LABEL:  # judul marketplace panjang berisi sampah promo -> pangkas
            label = label[:_MAX_LABEL].rsplit(" ", 1)[0] + "…"
        rank = (score + bonus, popularity)
        prev = candidates.get(key)
        if prev is None or rank > prev[0]:
            candidates[key] = (rank, popularity, price, label)

    # 1) Kanonik RAM/storage + median harga real dari listing.
    market = _market_prices(db, section)
    for label in _CANONICAL.get(section, []):
        prices = market.get(label, [])
        add(label, max(len(prices), 20), median(prices) if prices else None, bonus=15)

    # 2) Katalog komponen (model bersih hasil agregasi).
    if section in ("gpu", "cpu", "motherboard"):
        rows = db.execute(
            select(PCComponent.model, PCComponent.sample_count, PCComponent.avg_price)
            .where(PCComponent.component_type == section)
        ).all()
        # Gabungkan duplikat antar-merek dulu (model sama = satu entri),
        # baru buang artefak agregasi: banyak model beda dengan samples+harga identik.
        collapsed: dict[str, tuple[int, float | None]] = {}
        for model, samples, price in rows:
            key = (model or "").upper()
            if not key:
                continue
            prev = collapsed.get(key)
            if prev is None or (samples or 0) > prev[0]:
                collapsed[key] = (samples or 0, price)
        signatures: dict[tuple[int, int], int] = {}
        for samples, price in collapsed.values():
            sig = (samples, int(price or 0))
            signatures[sig] = signatures.get(sig, 0) + 1
        for model, (samples, price) in collapsed.items():
            if signatures[(samples, int(price or 0))] > 3:
                continue  # baris artefak scraper, bukan produk nyata
            add(model, min(samples, 50), price, bonus=15)

    # 3) Katalog laptop.
    if section == "laptop":
        rows = db.execute(
            select(LaptopUnit.brand, LaptopUnit.model, LaptopUnit.price)
            .where(LaptopUnit.price > 100_000).order_by(desc(LaptopUnit.scraped_at)).limit(400)
        ).all()
        for brand, model, price in rows:
            brand_words = set((brand or "").lower().split())
            model_words = (model or "").split()
            trimmed = " ".join(w for w in model_words if w.lower() not in brand_words)
            label = " ".join(filter(None, [brand, trimmed or model]))
            # Junk scraper (URL/markdown) & judul non-laptop jangan masuk pool.
            if "http" in label.lower() or not is_relevant_pc_listing(label, label, "laptop"):
                continue
            add(label, 1, price)

    # 4) Judul listing real — bahasa pasar apa adanya, plus harganya.
    if query_tokens:
        rows = db.execute(
            select(RawListing.raw_title, RawListing.raw_price)
            .where(
                RawListing.category == ("laptop" if section == "laptop" else "pc"),
                RawListing.raw_price.is_not(None),
                RawListing.raw_price > 50_000,
            )
            .order_by(desc(RawListing.scraped_at)).limit(2000)
        ).all()
        for title, price in rows:
            if not is_relevant_pc_listing(title, title, section):
                continue
            add(title, 1, price)

    ranked = sorted(candidates.values(), key=lambda r: (r[0], r[1], -len(r[3])), reverse=True)[:limit]
    return [
        {"label": label, "samples": popularity, "price": round(price) if price else None}
        for (_, popularity), popularity, price, label in ranked
    ]
