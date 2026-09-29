"""Seed demo computer stores (B4 LBS) from app/data/stores_jakarta.csv.

Usage:
    cd backend && python -m app.seed_stores [--csv app/data/stores_jakarta.csv]

Idempotent: matches existing rows by (name, city) and updates them.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Store  # noqa: E402

DEFAULT_CSV = Path(__file__).resolve().parent / "data" / "stores_jakarta.csv"


def seed(csv_path: Path) -> tuple[int, int]:
    inserted = updated = 0
    with SessionLocal() as db:
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = (row.get("name") or "").strip()
                city = (row.get("city") or "Jakarta").strip()
                if not name:
                    continue
                existing = db.scalar(
                    select(Store).where(Store.name == name, Store.city == city)
                )
                values = {
                    "address": (row.get("address") or "").strip() or None,
                    "lat": float(row["lat"]),
                    "lng": float(row["lng"]),
                    "prices_json": (row.get("prices_json") or "").strip() or None,
                }
                if existing:
                    for k, v in values.items():
                        setattr(existing, k, v)
                    updated += 1
                else:
                    db.add(Store(name=name, city=city, **values))
                    inserted += 1
        db.commit()
    return inserted, updated


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    args = ap.parse_args()
    inserted, updated = seed(Path(args.csv))
    print(f"stores seed: {inserted} inserted, {updated} updated")


if __name__ == "__main__":
    main()
