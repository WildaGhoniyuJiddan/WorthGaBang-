from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import LaptopUnit, RawListing
from app.schemas import AnalyzeRequest
from app.services.analysis import analyze
from app.services.ingestion import ListingInput, ingest_listings


def test_pc_benchmark_advice_on_wajar_or_worth_it():
    # Model seperti GTX 1650 di harga 3.200.000 bisa jadi "worth it" dibanding
    # listing pasarnya (mis. 3.500.000), tapi di benchmark ada alternatif jauh
    # lebih kencang (mis. GTX 1070 / RX 5600) di rentang harga serupa.
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest_listings(
            session,
            "tokopedia",
            [
                ListingInput("ZOTAC GeForce GTX 1650 4GB DDR6", 3500000, "url-1"),
                ListingInput("MSI GeForce GTX 1650 4GB Gaming", 3600000, "url-2"),
                ListingInput("ASUS GeForce GTX 1650 4GB Phoenix", 3550000, "url-3"),
            ],
        )
        result, comparisons, _, alternatives = analyze(
            session,
            AnalyzeRequest(mode="pc", query="GTX 1650", price=3200000, component_type="gpu"),
        )
        assert result.verdict in ("worth it", "wajar")
        assert len(alternatives) > 0
        assert "Ada alternatif dengan performa lebih tinggi di kisaran harga serupa" in result.recommendation


def test_pc_benchmark_advice_on_expensive_retains_framing():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest_listings(
            session,
            "tokopedia",
            [
                ListingInput("ZOTAC GeForce GTX 1650 4GB DDR6", 2500000, "url-1"),
                ListingInput("MSI GeForce GTX 1650 4GB Gaming", 2600000, "url-2"),
            ],
        )
        result, comparisons, _, alternatives = analyze(
            session,
            AnalyzeRequest(mode="pc", query="GTX 1650", price=4500000, component_type="gpu"),
        )
        assert result.verdict == "kemahalan"
        assert len(alternatives) > 0
        assert "Di harga segitu lebih baik" in result.recommendation


def test_laptop_benchmark_advice_on_wajar_verdict():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        raw1 = RawListing(
            source="tokopedia",
            category="laptop",
            raw_title="Lenovo IdeaPad Slim 3 Core i3-1215U",
            raw_price=6000000,
            listing_url="url-1",
            listing_hash="hash-1",
            condition="second",
            scraped_at=now,
        )
        raw2 = RawListing(
            source="tokopedia",
            category="laptop",
            raw_title="Lenovo IdeaPad Gaming 3 Ryzen 5 5600H RTX 3050",
            raw_price=5800000,
            listing_url="url-2",
            listing_hash="hash-2",
            condition="second",
            scraped_at=now,
        )
        session.add_all([raw1, raw2])
        session.flush()

        unit1 = LaptopUnit(
            raw_listing_id=raw1.id,
            brand="Lenovo",
            model="IdeaPad Slim 3",
            cpu="Core i3-1215U",
            gpu=None,
            ram_gb=8,
            storage_gb=512,
            price=6000000,
            condition="second",
            source="tokopedia",
            scraped_at=now,
        )
        unit2 = LaptopUnit(
            raw_listing_id=raw2.id,
            brand="Lenovo",
            model="IdeaPad Gaming 3",
            cpu="Ryzen 5 5600H",
            gpu="RTX 3050",
            ram_gb=16,
            storage_gb=512,
            price=5800000,
            condition="second",
            source="tokopedia",
            scraped_at=now,
        )
        session.add_all([unit1, unit2])
        session.commit()

        result, comparisons, _, alternatives = analyze(
            session,
            AnalyzeRequest(
                mode="laptop",
                query="IdeaPad",
                price=6000000,
                cpu="Core i3-1215U",
            ),
        )
        assert result.verdict == "wajar"
        assert len(alternatives) > 0
        assert "Ada alternatif unit dengan performa lebih tinggi" in result.recommendation
