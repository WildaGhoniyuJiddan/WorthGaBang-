import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Base, SessionLocal, engine
from app.services.ingestion import ListingInput, ingest_listings


def main() -> None:
    Base.metadata.create_all(bind=engine)
    root = Path(__file__).resolve().parents[2]
    tokopedia_file = root / "tokped_jina_products.json"
    products = json.loads(tokopedia_file.read_text(encoding="utf-8")) if tokopedia_file.exists() else []
    listings = [
        ListingInput(title=item.get("name", ""), price=item.get("price_rp"), url=item.get("url"))
        for item in products
    ]
    listings.extend(
        [
            ListingInput("ASUS ROG Strix G15 Ryzen 5 5600H RTX 3060 16GB 512GB SSD", 14500000, "https://example.com/demo-laptop-1", category="laptop"),
            ListingInput("Lenovo Legion 5 Core i5 12400H RTX 4060 16GB 512GB SSD", 18900000, "https://example.com/demo-laptop-2", category="laptop"),
            ListingInput("Acer Nitro V Core i5 13420H RTX 4050 16GB 512GB SSD", 12500000, "https://example.com/demo-laptop-3", category="laptop"),
        ]
    )
    with SessionLocal() as session:
        inserted = ingest_listings(session, "tokopedia", listings)
    print(f"Seeded {inserted} demo listings")


if __name__ == "__main__":
    main()
