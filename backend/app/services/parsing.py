import hashlib
import re
from typing import Optional


# ponytail: harga wajib ber-prefix mata uang ("Rp") atau satuan ("jt/rb") supaya
# angka liar di judul/markdown ("Image 64", "RTX 4060", "5.0 rating") tidak ikut ke-match.
# Kalau nanti ada sumber yang tulis harga telanjang ("4.500.000"), tambahkan context-flag per scraper.
PRICE_RE = re.compile(
    r"rp\.?\s*(?P<idr>[\d][\d.,]*)|(?P<num>[\d][\d.,]*)\s*(?P<unit>jt|juta|rb|ribu)\b",
    re.IGNORECASE,
)
BRANDS = (
    # GPU AIB / komponen
    "asus", "acer", "lenovo", "hp", "dell", "msi", "gigabyte", "zotac", "evga",
    "galax", "vurrion", "intel", "amd", "nvidia", "sapphire", "powercolor",
    "colorful", "xfx", "asrock", "palit", "gainward", "axle", "leadtek", "pny",
    # brand laptop/PC lokal & entry-level Indonesia
    "axioo", "advan", "zyrex", "infinix", "hisi", "kozy",
    # brand lain yang umum di listing
    "apple", "macbook", "huawei", "honor", "xiaomi", "redmibook", "realme",
    "samsung", "toshiba", "dynabook", "fujitsu", "microsoft", "surface",
    "razer", "alienware", "chuwi", "vaio", "lg",
    # fallback: kalau merk induk gak disebut, series punya nilai identifikasi
    "rog", "tuf", "legion", "nitro", "vivobook", "zenbook", "ideapad",
    "thinkpad", "victus", "omen", "katana", "aorus", "chromebook", "predator",
)

SECOND_HINTS = ("second", "bekas", "2nd", "preloved", "pre-owned", "preowned", " used ", "like new")


def parse_price(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    text = str(value).lower().replace("\u00a0", " ").strip()
    match = PRICE_RE.search(text)
    if not match:
        return None
    if match.group("idr"):
        digits = match.group("idr").replace(".", "").replace(",", "")
        if not digits.isdigit():
            return None
        amount = int(digits)
        return amount if amount > 0 else None
    raw_number = match.group("num")
    unit = (match.group("unit") or "").lower()
    if unit in {"jt", "juta"}:
        try:
            amount = int(float(raw_number.replace(",", ".")) * 1_000_000)
        except ValueError:
            return None
        return amount if amount > 0 else None
    digits = raw_number.replace(".", "").replace(",", "")
    if not digits.isdigit():
        return None
    amount = int(digits)
    if unit in {"rb", "ribu"}:
        amount *= 1_000
    return amount if amount > 0 else None


def detect_condition(text: str) -> Optional[str]:
    lowered = f" {str(text or '').lower()} "
    if any(hint in lowered for hint in SECOND_HINTS):
        return "second"
    return None


def stable_listing_hash(source: str, title: str, price: Optional[int], url: Optional[str]) -> str:
    identity = "|".join((source or "", title or "", str(price or ""), url or "")).lower().strip()
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def strip_query_prefix(text: str) -> str:
    """Bersihkan prefix keyword query seperti 'Arc B580 — ' atau '[query] \ufffc ' dari judul."""
    raw = str(text or "").strip()
    cleaned = re.sub(r"^[^\u2014\ufffc]+[\u2014\ufffc]\s*", "", raw).strip()
    return cleaned or raw


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def detect_category(title: str, spec_text: str = "") -> str:
    from .relevance import is_laptop_listing

    return "laptop" if is_laptop_listing(title, spec_text) else "pc"


def detect_brand(text: str) -> Optional[str]:
    lowered = text.lower()
    for brand in BRANDS:
        if re.search(rf"\b{re.escape(brand)}\b", lowered):
            return brand.upper() if brand in {"hp", "msi", "amd"} else brand.title()
    return None


def extract_gb(text: str, pattern: str) -> Optional[int]:
    match = re.search(pattern, text, re.IGNORECASE)
    return int(match.group(1)) if match else None
