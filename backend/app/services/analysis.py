import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import LaptopUnit, RawListing, ScrapeRun
from ..schemas import AnalyzeRequest, Comparison, Freshness
from .relevance import is_relevant_pc_listing
from .scoring import score_price


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", (value or "").lower()) if len(token) > 1}


def _similarity(query: str, title: str) -> float:
    wanted = _tokens(query)
    actual = _tokens(title)
    if not wanted or not actual:
        return 0.0
    return round(len(wanted & actual) / len(wanted), 3)


# ponytail: harga BARU referensi (USD street dari PCPartPicker dataset) -> IDR.
# Kurs & diskon retail ID di-hardcode; kalau mau presisi, ambil kurs harian API.
USD_TO_IDR = 16_500
RETAIL_MARKUP = 1.10  # harga retail Indonesia biasanya ~10% di atas USD street

_NEW_PRICE_REF_PATH = Path(__file__).resolve().parents[2] / "app" / "data" / "new_price_reference.json"
_new_price_ref: dict | None = None


def _load_new_price_ref() -> dict:
    global _new_price_ref
    if _new_price_ref is None:
        try:
            _new_price_ref = json.loads(_NEW_PRICE_REF_PATH.read_text(encoding="utf-8"))
        except Exception:
            _new_price_ref = {"gpu": {}, "cpu": {}}
    return _new_price_ref


def _anchor_key(query: str) -> str | None:
    """Key model GPU/CPU dari query; format sama dengan generator anchor komponen retail."""
    q = " ".join((query or "").lower().split())
    m = re.search(r"(rtx|gtx)\s*(\d{3,4})\s*(ti|super)?", q)
    if m:
        return f"{m.group(1)} {m.group(2)}{(' ' + m.group(3)) if m.group(3) else ''}"
    m = re.search(r"rx\s*(\d{4})\s*(xt)?", q)
    if m:
        return f"rx {m.group(1)}{(' xt') if m.group(2) else ''}"
    m = re.search(r"ryzen\s*([3579])\s*((?:9\d{3}|[357]\d{3}))", q)
    if m:
        return f"ryzen {m.group(1)} {m.group(2)}"
    m = re.search(r"core i([3579])\s*-?\s*((?:10|11|12|13|14)\d{3})", q)
    if m:
        return f"core i{m.group(1)} {m.group(2)}"
    return None


def new_price_anchor(query: str) -> int | None:
    """Harga BARU referensi (IDR) untuk query GPU/CPU, None kalau gak ketemu.

    Prioritas: harga retail IDR real dari sumber komponen retail, bucket
    "retail_idr" di new_price_reference.json (generator:
    scripts/generate_anchor_harga_komponen.py). Fallback: konversi USD street
    PCPartPicker -> IDR.
    """
    ref = _load_new_price_ref()
    key = _anchor_key(query)
    if not key:
        return None

    # ponytail: exact-match saja utk harga retail — "rtx 3060 ti" itu produk BEDA,
    # bukan varian "rtx 3060", jadi tidak boleh ikut median.
    for bucket in ("gpu", "cpu"):
        price = _load_new_price_ref().get("retail_idr", {}).get(bucket, {}).get(key)
        if price:
            return int(price)

    usd = ref.get("gpu", {}).get(key) or ref.get("cpu", {}).get(key)
    if not usd:
        return None
    return int(usd * USD_TO_IDR * RETAIL_MARKUP)


def _is_relevant_pc_listing(query: str, title: str, component_type: str | None) -> bool:
    return is_relevant_pc_listing(query, title, component_type)


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


def freshness(session: Session, preferred_source: str = "facebook_marketplace") -> Freshness:
    # ponytail: source names match raw_listings values (facebook_marketplace dari
    # ekstensi, tokopedia dari scraper); tambah shopee kalau scraper-nya live.
    candidates = ["facebook_marketplace", "tokopedia"]
    fresh = [_freshness_for_source(session, source) for source in candidates]
    available = [item for item in fresh if item.last_updated_at is not None and not item.is_stale]
    if available:
        selected = next((item for item in available if item.primary_source == preferred_source), available[0])
    else:
        selected = next((item for item in fresh if item.last_updated_at is not None), fresh[0])
    return selected


def all_freshness(session: Session) -> dict[str, Freshness]:
    return {source: _freshness_for_source(session, source) for source in ("facebook_marketplace", "tokopedia")}


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
    if request.condition and request.condition != "any":
        wanted = request.condition
        same = [item for item in matching if (item[1].condition or "new") == wanted]
        # kalau kondisi itu gak ada samsek, jangan paksa pakai lawannya
        matching = same
        if not matching:
            return []
    # outlier guard: median robust, tapi IQR ekstrem tetap bisa narik anchor;
    # buang harga di luar [Q1-1.5xIQR, Q3+1.5xIQR] sebelum pilih pembanding.
    matching.sort(key=lambda item: (item[0], item[1].scraped_at), reverse=True)
    top = matching[:20]
    prices = sorted(item[1].raw_price or 0 for item in top)
    q1 = prices[max(0, len(prices) // 4)]
    q3 = prices[min(len(prices) - 1, (3 * len(prices)) // 4)]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inliers = [item for item in top if lo <= (item[1].raw_price or 0) <= hi]
    top = inliers or top
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
            condition=row.condition or "new",
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
    # fallback anchor harga BARU dari katalog referensi (buildcores+PCPartPicker)
    # kalau listing second yang relevan gak cukup untuk kasih verdict.
    if (result.verdict == "data terbatas" or not comparisons) and request.condition != "second":
        ref_new = new_price_anchor(request.query)
        if ref_new:
            result = score_price(request.price, [ref_new])
            if not comparisons:
                comparisons = [
                    Comparison(
                        title=f"Reference harga baru {request.query} (bukan listing marketplace)",
                        price=ref_new,
                        source="price_reference",
                        listing_url=None,
                        similarity=0.5,
                        condition="new",
                    )
                ]
    selected_source = comparisons[0].source if comparisons else "facebook_marketplace"
    return result, comparisons, freshness(session, selected_source)
