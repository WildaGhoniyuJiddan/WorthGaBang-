from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RawListing
from .listing_quality import assess_listing
from .normalizer import normalize_listing
from .parsing import clean_text, detect_category, detect_condition, parse_price, stable_listing_hash


@dataclass
class ListingInput:
    title: str
    price: object
    url: Optional[str] = None
    spec_text: Optional[str] = None
    category: Optional[str] = None
    condition: Optional[str] = None
    scraped_at: Optional[datetime] = None
    description: Optional[str] = None
    seller: Optional[str] = None
    is_official_store: Optional[bool] = None
    sold_count: Optional[int] = None
    rating: Optional[float] = None
    condition_source: Optional[str] = None


@dataclass
class IngestStats:
    """Ringkasan hasil ingest supaya pemanggil bisa melaporkan apa yang dibuang."""

    inserted: int = 0
    enriched: int = 0
    skipped_duplicate: int = 0
    skipped_ex_mining: int = 0
    skipped_other: int = 0


def listing_input_from_record(record) -> "ListingInput":
    """Konversi ListingRecord scraper -> ListingInput.

    Dipakai sebagai SATU-SATUNYA jalur konversi supaya field baru tidak
    pernah lupa diteruskan (bug: deskripsi/seller hilang karena adapter
    lama hanya memetakan judul+harga).
    """
    return ListingInput(
        title=record.title,
        price=record.price,
        url=record.url,
        spec_text=record.spec_text,
        category=record.category,
        condition=record.condition,
        description=getattr(record, "description", None),
        seller=getattr(record, "seller", None),
        is_official_store=getattr(record, "is_official_store", None),
        sold_count=getattr(record, "sold_count", None),
        rating=getattr(record, "rating", None),
        condition_source=getattr(record, "condition_source", None),
    )


# Field yang boleh diperkaya (di-update) pada baris yang sudah ada.
_ENRICHABLE = ("description", "seller", "is_official_store", "sold_count",
               "rating", "condition_source")


def ingest_listings(
    session: Session,
    source: str,
    listings: Iterable[ListingInput],
    *,
    stats: IngestStats | None = None,
) -> int:
    """Simpan listing ke DB. Listing ex-mining DIBUANG, tidak pernah disimpan.

    Filter dilakukan di sini (bukan hanya di scraper) sebagai pengaman
    terakhir: apa pun jalur masuknya — termasuk ingest manual via API —
    harga barang ex-mining tidak boleh dipakai sebagai pembanding.

    Baris yang sudah ada TIDAK dilewati begitu saja: kalau data baru lebih
    kaya (mis. sekarang punya deskripsi), baris lama diperkaya. Ini yang
    membuat backfill data lama bisa jalan lewat scrape ulang.
    """
    counters = stats if stats is not None else IngestStats()
    for item in listings:
        title = clean_text(item.title)
        if not title:
            counters.skipped_other += 1
            continue

        # Gerbang kualitas: periksa judul + deskripsi + spec.
        verdict = assess_listing(
            title,
            clean_text(item.description) if item.description else None,
            clean_text(item.spec_text) if item.spec_text else None,
        )
        if not verdict.is_acceptable:
            if verdict.is_ex_mining:
                counters.skipped_ex_mining += 1
            else:
                counters.skipped_other += 1
            continue

        price = parse_price(item.price)
        # Kondisi: pakai label resmi marketplace kalau ada, lalu sinyal
        # judul/deskripsi, baru fallback.
        condition = (
            item.condition
            or verdict.condition_hint
            or detect_condition(f"{title} {item.description or ''} {item.spec_text or ''}")
        )
        if item.condition_source == "Bekas":
            condition = "second"
        elif item.condition_source == "Baru":
            condition = "new"
        condition = condition or "new"

        listing_hash = stable_listing_hash(source, title, price, item.url)
        existing = session.scalar(
            select(RawListing).where(RawListing.listing_hash == listing_hash)
        )
        if existing:
            # Perkaya baris lama dengan field yang sebelumnya kosong.
            changed = False
            for field in _ENRICHABLE:
                new_value = getattr(item, field, None)
                if new_value is not None and getattr(existing, field, None) is None:
                    setattr(existing, field, new_value)
                    changed = True
            if changed:
                counters.enriched += 1
                normalize_listing(session, existing)
            else:
                counters.skipped_duplicate += 1
            continue

        raw = RawListing(
            source=source,
            category=item.category or detect_category(title, item.spec_text or ""),
            raw_title=title,
            raw_price=price,
            raw_spec_text=clean_text(item.spec_text) if item.spec_text else None,
            description=clean_text(item.description) if item.description else None,
            listing_url=item.url,
            listing_hash=listing_hash,
            condition=condition,
            seller=item.seller,
            is_official_store=item.is_official_store,
            sold_count=item.sold_count,
            rating=item.rating,
            condition_source=item.condition_source,
            scraped_at=item.scraped_at or datetime.now(timezone.utc),
        )
        session.add(raw)
        session.flush()
        normalize_listing(session, raw)
        counters.inserted += 1
    session.commit()
    return counters.inserted
