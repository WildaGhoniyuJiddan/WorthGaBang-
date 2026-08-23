import hashlib
import re
from typing import Optional


PRICE_RE = re.compile(r"(?:rp\.?\s*)?([\d][\d.,]*)\s*(jt|juta|rb|ribu)?", re.IGNORECASE)
BRANDS = ("asus", "acer", "lenovo", "hp", "dell", "msi", "gigabyte", "zotac", "evga", "galax", "vurrion", "intel", "amd", "nvidia")


def parse_price(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    text = str(value).lower().replace(" ", " ").strip()
    match = PRICE_RE.search(text)
    if not match:
        return None
    multiplier = (match.group(2) or "").lower()
    raw_number = match.group(1)
    if multiplier and ("," in raw_number or "." in raw_number):
        try:
            amount = int(float(raw_number.replace(",", ".")) * 1_000_000)
        except ValueError:
            return None
        return amount if amount > 0 else None
    number = raw_number.replace(".", "").replace(",", "")
    if not number.isdigit():
        return None
    amount = int(number)
    if multiplier in {"jt", "juta"}:
        amount *= 1_000_000
    elif multiplier in {"rb", "ribu"}:
        amount *= 1_000
    return amount if amount > 0 else None


def stable_listing_hash(source: str, title: str, price: Optional[int], url: Optional[str]) -> str:
    identity = "|".join((source or "", title or "", str(price or ""), url or "")).lower().strip()
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def detect_category(title: str, spec_text: str = "") -> str:
    text = f"{title} {spec_text}".lower()
    laptop_terms = ("laptop", "notebook", "macbook", "vivobook", "ideapad", "thinkpad", "zenbook", "rog strix")
    return "laptop" if any(term in text for term in laptop_terms) else "pc"


def detect_brand(text: str) -> Optional[str]:
    lowered = text.lower()
    for brand in BRANDS:
        if re.search(rf"\b{re.escape(brand)}\b", lowered):
            return brand.upper() if brand in {"hp", "msi", "amd"} else brand.title()
    return None


def extract_gb(text: str, pattern: str) -> Optional[int]:
    match = re.search(pattern, text, re.IGNORECASE)
    return int(match.group(1)) if match else None
