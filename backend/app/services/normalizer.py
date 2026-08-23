import re
from datetime import datetime, timezone
from statistics import mean

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import LaptopUnit, PCComponent, RawListing
from .parsing import clean_text, detect_brand, extract_gb


BENCHMARKS = {
    "rtx 3060": 125,
    "rtx 4060": 175,
    "rtx 4070": 245,
    "rx 6600": 115,
    "ryzen 5 5600": 100,
    "ryzen 5 7600": 145,
    "core i5 12400": 105,
    "core i5 13400": 135,
}


def _find_model(title: str, component_type: str) -> str:
    text = clean_text(title)
    patterns = {
        "gpu": r"((?:rtx|gtx|rx)\s*\d{3,4}(?:\s*ti|\s*super)?)",
        "cpu": r"((?:ryzen\s*[3579]|core\s*i[3579])\s*[- ]?\d{4,5}[a-z]*)",
        "ram": r"(\d+\s*gb\s*(?:ddr[345])?)",
        "storage": r"(\d+\s*(?:gb|tb)\s*(?:ssd|nvme|hdd))",
    }
    match = re.search(patterns.get(component_type, r"(.+)"), text, re.IGNORECASE)
    return clean_text(match.group(1)) if match else text[:255]


def _component_type(title: str) -> str:
    text = title.lower()
    if any(word in text for word in ("rtx", "gtx", "radeon", "rx ", "vga", "gpu")):
        return "gpu"
    if any(word in text for word in ("ryzen", "core i", "intel", "processor", "cpu")):
        return "cpu"
    if "ram" in text or "ddr4" in text or "ddr5" in text:
        return "ram"
    if any(word in text for word in ("ssd", "nvme", "hdd", "storage")):
        return "storage"
    return "other"


def _benchmark(model: str) -> int:
    lowered = model.lower()
    for key, value in BENCHMARKS.items():
        if key in lowered:
            return value
    return 0


def normalize_laptop(raw: RawListing) -> LaptopUnit:
    text = f"{raw.raw_title} {raw.raw_spec_text or ''}"
    cpu_match = re.search(r"((?:intel\s+)?core\s+i[3579]\s*[- ]?\d{4,5}[a-z]*|ryzen\s*[3579]\s*\d{4,5}[a-z]*)", text, re.IGNORECASE)
    gpu_match = re.search(r"((?:rtx|gtx|rx)\s*\d{3,4}(?:\s*ti|\s*super)?)", text, re.IGNORECASE)
    screen_match = re.search(r"(\d{2}(?:\.\d)?)\s*(?:inch|inci|\")", text, re.IGNORECASE)
    return LaptopUnit(
        raw_listing_id=raw.id,
        brand=detect_brand(text),
        model=clean_text(raw.raw_title)[:255],
        cpu=clean_text(cpu_match.group(1)) if cpu_match else None,
        gpu=clean_text(gpu_match.group(1)) if gpu_match else None,
        ram_gb=extract_gb(text, r"(\d{1,3})\s*gb\s*(?:ram|ddr|memory)?") or extract_gb(text, r"(\d{1,3})\s*gb"),
        storage_gb=extract_gb(text, r"(\d{2,5})\s*gb\s*(?:ssd|nvme|hdd|storage)") or extract_gb(text, r"(\d+)\s*tb\s*(?:ssd|nvme|hdd)") and int(extract_gb(text, r"(\d+)\s*tb") or 0) * 1000,
        screen_size=float(screen_match.group(1)) if screen_match else None,
        price=raw.raw_price or 0,
        condition=raw.condition or ("second" if "second" in text.lower() or "bekas" in text.lower() else "new"),
        source=raw.source,
        listing_url=raw.listing_url,
        scraped_at=raw.scraped_at,
    )


def normalize_listing(session: Session, raw: RawListing) -> None:
    if not raw.raw_price:
        return
    if raw.category == "laptop":
        existing = session.scalar(select(LaptopUnit).where(LaptopUnit.raw_listing_id == raw.id))
        if not existing:
            session.add(normalize_laptop(raw))
        return

    component_type = _component_type(raw.raw_title)
    model = _find_model(raw.raw_title, component_type)
    brand = detect_brand(raw.raw_title)
    existing = session.scalar(
        select(PCComponent).where(
            PCComponent.component_type == component_type,
            PCComponent.brand == brand,
            PCComponent.model == model,
        )
    )
    if not existing:
        existing = PCComponent(component_type=component_type, brand=brand, model=model)
        session.add(existing)
    session.flush()
    all_rows = session.scalars(
        select(RawListing).where(RawListing.category == "pc", RawListing.raw_price.is_not(None))
    ).all()
    model_tokens = [token for token in re.findall(r"[a-z0-9]+", model.lower()) if len(token) > 1]
    matching_prices = [
        row.raw_price
        for row in all_rows
        if row.raw_price and all(token in row.raw_title.lower() for token in model_tokens)
    ]
    prices = matching_prices or [row.raw_price for row in all_rows if row.raw_price]
    existing.avg_price = int(mean(prices)) if prices else raw.raw_price
    existing.sample_count = len(prices)
    existing.benchmark_score = _benchmark(model)
    existing.updated_at = datetime.now(timezone.utc)


def normalize_pending(session: Session) -> int:
    pending = session.scalars(select(RawListing).order_by(RawListing.id)).all()
    count = 0
    for raw in pending:
        normalize_listing(session, raw)
        count += 1
    session.commit()
    return count
