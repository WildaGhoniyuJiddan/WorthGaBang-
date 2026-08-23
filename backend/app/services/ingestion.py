from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RawListing
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


def ingest_listings(session: Session, source: str, listings: Iterable[ListingInput]) -> int:
    inserted = 0
    for item in listings:
        title = clean_text(item.title)
        if not title:
            continue
        price = parse_price(item.price)
        condition = item.condition or detect_condition(f"{title} {item.spec_text or ''}")
        listing_hash = stable_listing_hash(source, title, price, item.url)
        exists = session.scalar(select(RawListing.id).where(RawListing.listing_hash == listing_hash))
        if exists:
            continue
        raw = RawListing(
            source=source,
            category=item.category or detect_category(title, item.spec_text or ""),
            raw_title=title,
            raw_price=price,
            raw_spec_text=clean_text(item.spec_text) if item.spec_text else None,
            listing_url=item.url,
            listing_hash=listing_hash,
            condition=condition,
            scraped_at=item.scraped_at or datetime.now(timezone.utc),
        )
        session.add(raw)
        session.flush()
        normalize_listing(session, raw)
        inserted += 1
    session.commit()
    return inserted

