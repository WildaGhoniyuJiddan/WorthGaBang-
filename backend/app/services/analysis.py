import re
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import LaptopUnit, RawListing, ScrapeRun
from ..schemas import AnalyzeRequest, Comparison, Freshness
from .scoring import score_price


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", (value or "").lower()) if len(token) > 1}


def _similarity(query: str, title: str) -> float:
    wanted = _tokens(query)
    actual = _tokens(title)
    if not wanted or not actual:
        return 0.0
    return round(len(wanted & actual) / len(wanted), 3)


# ponytail: filter kasar listing full-build vs komponen lepas; kalau nanti
# katalog punya kolom is_build yang beneran, ganti ini.
_BUILD_WORDS = ("pc gaming", "pc rakitan", "komputer", "desktop", "pc mini", "built up", "fullset", "paket ")
_ACCESSORY_WORDS = ("fan ", "kipas", "cooler ", "dus ", "box only", "bracket", "cable", "kabel", "riser", "backplate", "sticker", "case ")


def _is_relevant_pc_listing(query: str, title: str, component_type: str | None) -> bool:
    text = f"{query} {title}".lower()
    if any(word in text for word in _BUILD_WORDS):
        return False
    if any(word in text for word in _ACCESSORY_WORDS):
        return False
    # listing komponen asli menyebut 1 chipset; aksesori/build menyebut banyak
    return len(re.findall(r"(?:rtx|gtx|rx)\s*\d{3,4}", title.lower())) <= 1


def _age_label(seconds: int | None) -> str:
    if seconds is None:
        return "belum ada data"
    if seconds < 60:
        return "baru saja"
    if seconds < 3600:
        return f"{seconds // 60} menit lalu"
    if seconds < 86_400:
        return f"{seconds // 3600} jam lalu"
    return f"{seconds // 86_400} hari lalu"


def _freshness_for_source(session: Session, source: str) -> Freshness:
    run = session.scalar(
        select(ScrapeRun).where(ScrapeRun.source == source).order_by(desc(ScrapeRun.started_at)).limit(1)
    )
    timestamp = run.finished_at if run and run.status == "success" else None
    if timestamp is None:
        timestamp = session.scalar(select(RawListing.scraped_at).where(RawListing.source == source).order_by(desc(RawListing.scraped_at)).limit(1))
    now = datetime.now(timezone.utc)
    if timestamp is None:
        age = None
    else:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age = max(0, int((now - timestamp).total_seconds()))
    return Freshness(
        last_updated_at=timestamp,
        age_seconds=age,
        label=_age_label(age),
        is_stale=age is None or age > get_settings().stale_after_hours * 3600,
        primary_source=source,
    )


def freshness(session: Session, preferred_source: str = "tokopedia") -> Freshness:
    candidates = ["tokopedia", "shopee", "facebook"]
    fresh = [_freshness_for_source(session, source) for source in candidates]
    available = [item for item in fresh if item.last_updated_at is not None and not item.is_stale]
    if available:
        selected = next((item for item in available if item.primary_source == preferred_source), available[0])
    else:
        selected = next((item for item in fresh if item.last_updated_at is not None), fresh[0])
    return selected


def all_freshness(session: Session) -> dict[str, Freshness]:
    return {source: _freshness_for_source(session, source) for source in ("tokopedia", "shopee", "facebook")}


def _pc_comparisons(session: Session, request: AnalyzeRequest) -> list[Comparison]:
    # ponytail: ambil 2000 row terakhir; kalau katalog >20k listing, pindahkan
    # filter relevan ke query SQL (LIKE per token model).
    rows = session.scalars(
        select(RawListing).where(RawListing.category == "pc", RawListing.raw_price.is_not(None)).order_by(desc(RawListing.scraped_at)).limit(2000)
    ).all()
    scored = [
        (_similarity(request.query, row.raw_title), row)
        for row in rows
        if _is_relevant_pc_listing(request.query, row.raw_title, request.component_type)
    ]
    # butuh kemiripan token tinggi (>=0.75) supaya "RX 6600" tidak membandingkan
    # diri dengan PC build yang iseng mention RX 6600 atau laptop seri lain
    matching = [item for item in scored if item[0] >= 0.75]
    if not matching:
        return []
    # urutkan by similarity lalu ambil median harga sebagai anchor: median
    # kebal aksesori murah dan build mahal.
    matching.sort(key=lambda item: (item[0], item[1].scraped_at), reverse=True)
    top = matching[:20]
    prices = sorted(item[1].raw_price or 0 for item in top)
    anchor = prices[len(prices) // 2]
    # pilih listing yang harganya paling dekat dengan median supaya output
    # comparisons representatif, bukan ekstrem termurah/termahal
    top.sort(key=lambda item: abs((item[1].raw_price or 0) - anchor))
    selected = top[:10]
    return [
        Comparison(
            title=row.raw_title,
            price=row.raw_price or 0,
            source=row.source,
            listing_url=row.listing_url,
            similarity=similarity,
            condition=row.condition,
        )
        for similarity, row in selected
    ]


def _laptop_comparisons(session: Session, request: AnalyzeRequest) -> list[Comparison]:
    rows = session.scalars(
        select(LaptopUnit).where(LaptopUnit.price > 0).order_by(desc(LaptopUnit.scraped_at)).limit(500)
    ).all()
    requested = " ".join(filter(None, [request.query, request.cpu, request.gpu, request.brand]))
    scored = []
    for row in rows:
        if request.condition and request.condition != "any" and row.condition and row.condition != request.condition:
            continue
        title = " ".join(filter(None, [row.brand, row.model, row.cpu, row.gpu, f"{row.ram_gb or ''}GB", f"{row.storage_gb or ''}GB"]))
        similarity = _similarity(requested, title)
        if request.ram_gb and row.ram_gb:
            similarity += 0.15 if row.ram_gb >= request.ram_gb else 0
        if request.storage_gb and row.storage_gb:
            similarity += 0.1 if row.storage_gb >= request.storage_gb else 0
        scored.append((min(1.0, similarity), row))
    matching = [item for item in scored if item[0] > 0]
    selected = sorted(matching or scored, key=lambda item: (item[0], item[1].scraped_at), reverse=True)[:10]
    return [
        Comparison(
            title=row.model or row.brand or "Laptop",
            price=row.price,
            source=row.source,
            listing_url=row.listing_url,
            similarity=similarity,
            condition=row.condition,
        )
        for similarity, row in selected
    ]


def analyze(session: Session, request: AnalyzeRequest):
    comparisons = _pc_comparisons(session, request) if request.mode == "pc" else _laptop_comparisons(session, request)
    result = score_price(request.price, [comparison.price for comparison in comparisons])
    selected_source = "tokopedia" if request.mode == "pc" else (comparisons[0].source if comparisons else "tokopedia")
    return result, comparisons, freshness(session, selected_source)
