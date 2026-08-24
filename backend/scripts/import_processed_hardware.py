"""Import the processed used-hardware CSVs into the backend SQLite catalog.

The import is idempotent: listing rows are keyed by their source URL and
component rows are upserted by (category, brand, model).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import LaptopUnit, PCComponent, RawListing  # noqa: E402


SOURCE = "facebook_marketplace"


def resolve_data_dir(value: str | None) -> Path:
    configured = Path(value or get_settings().processed_hardware_dir)
    return configured if configured.is_absolute() else BACKEND_ROOT / configured


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_int(value: object) -> int | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        number = int(float(text))
    except ValueError:
        return None
    return number if number > 0 else None


def parse_float(value: object) -> float | None:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_timestamp(value: object) -> datetime:
    text = str(value or "").strip()
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def condition_from_tags(value: object) -> str:
    tags = {part.strip() for part in str(value or "").split(";") if part.strip()}
    if "issue_or_defect" in tags:
        return "issue"
    if "new_or_sealed" in tags and not (tags & {"used_or_second", "like_new"}):
        return "new"
    if tags & {"used_or_second", "like_new", "normal_or_smooth"}:
        return "second"
    return "second"


def listing_hash(row: dict[str, str]) -> str:
    identity = row.get("source_url") or row.get("record_id") or row.get("canonical_title") or row.get("source_title")
    return hashlib.sha256(f"{SOURCE}|{identity}".lower().encode("utf-8")).hexdigest()


def title_for(row: dict[str, str]) -> str:
    return (row.get("canonical_title") or row.get("source_title") or "").strip()[:10000]


def raw_listing_from_row(row: dict[str, str], category: str) -> RawListing:
    title = title_for(row)
    spec_text = (row.get("description") or row.get("source_title") or "").strip()
    price = parse_int(row.get("price_rp"))
    return RawListing(
        source=SOURCE,
        category=category,
        raw_title=title,
        raw_price=price,
        raw_spec_text=spec_text[:10000] if spec_text else None,
        listing_url=(row.get("source_url") or "").strip() or None,
        listing_hash=listing_hash(row),
        condition=condition_from_tags(row.get("condition_tags")),
        scraped_at=parse_timestamp(row.get("scraped_at")),
    )


def laptop_from_row(row: dict[str, str], raw: RawListing) -> LaptopUnit:
    return LaptopUnit(
        raw_listing_id=raw.id,
        brand=(row.get("brand") or "").strip() or None,
        model=title_for(row)[:255] or None,
        cpu=(row.get("cpu_model") or "").strip() or None,
        gpu=(row.get("gpu_model") or "").strip() or None,
        ram_gb=parse_int(row.get("ram_gb")),
        storage_gb=parse_int(row.get("storage_gb")),
        screen_size=parse_float(row.get("screen_size_in")),
        price=parse_int(row.get("price_rp")) or 0,
        condition=condition_from_tags(row.get("condition_tags")),
        source=SOURCE,
        listing_url=raw.listing_url,
        scraped_at=raw.scraped_at,
    )


def component_identity(row: dict[str, str]) -> tuple[str, str | None, str]:
    component_type = (row.get("component_category") or "other").strip() or "other"
    brand = (row.get("brand") or "").strip() or None
    model = (row.get("gpu_model") or row.get("cpu_model") or row.get("canonical_title") or row.get("source_title") or "other").strip()
    return component_type, brand, model[:255]


def import_dataset(data_dir: Path) -> dict[str, int]:
    laptop_rows = [row for row in read_csv(data_dir / "laptop.csv") if row.get("status") == "accepted"]
    component_rows = [row for row in read_csv(data_dir / "komponen_pc.csv") if row.get("status") == "accepted"]
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        existing_raw = {row.listing_hash: row for row in session.scalars(select(RawListing)).all()}
        existing_laptop_ids = set(session.scalars(select(LaptopUnit.raw_listing_id)).all())
        existing_components = {
            (row.component_type, row.brand, row.model): row
            for row in session.scalars(select(PCComponent)).all()
        }

        raw_inserted = 0
        laptop_inserted = 0
        component_prices: dict[tuple[str, str | None, str], list[int]] = defaultdict(list)

        for row in laptop_rows:
            raw = existing_raw.get(listing_hash(row))
            if raw is None:
                raw = raw_listing_from_row(row, "laptop")
                session.add(raw)
                session.flush()
                existing_raw[raw.listing_hash] = raw
                raw_inserted += 1
            if raw.id not in existing_laptop_ids:
                session.add(laptop_from_row(row, raw))
                existing_laptop_ids.add(raw.id)
                laptop_inserted += 1

        for row in component_rows:
            raw = existing_raw.get(listing_hash(row))
            if raw is None:
                raw = raw_listing_from_row(row, "pc")
                session.add(raw)
                session.flush()
                existing_raw[raw.listing_hash] = raw
                raw_inserted += 1
            identity = component_identity(row)
            price = parse_int(row.get("price_rp"))
            if price:
                component_prices[identity].append(price)

        component_upserted = 0
        for identity, prices in component_prices.items():
            component_type, brand, model = identity
            component = existing_components.get(identity)
            if component is None:
                component = PCComponent(component_type=component_type, brand=brand, model=model)
                session.add(component)
                existing_components[identity] = component
            component.avg_price = round(sum(prices) / len(prices))
            component.sample_count = len(prices)
            component_upserted += 1

        session.commit()
        return {
            "laptop_rows": len(laptop_rows),
            "component_rows": len(component_rows),
            "raw_inserted": raw_inserted,
            "laptop_inserted": laptop_inserted,
            "components_upserted": component_upserted,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import processed hardware CSVs into the backend database")
    parser.add_argument("--data-dir", default=None, help="Processed data directory; defaults to backend/data/used_hardware")
    args = parser.parse_args()
    data_dir = resolve_data_dir(args.data_dir)
    required = [data_dir / "laptop.csv", data_dir / "komponen_pc.csv"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing processed data files: " + ", ".join(missing))
    result = import_dataset(data_dir)
    print(f"data_dir={data_dir}")
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
