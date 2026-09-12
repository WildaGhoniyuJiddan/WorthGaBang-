import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import LaptopUnit, RawListing
from app.schemas import AnalyzeRequest
from app.services.analysis import analyze, _pc_comparisons
from app.services.benchmark import (
    extract_vram_gb,
    get_tier_label,
    laptop_combo_score,
    better_alternatives,
)
from app.services.scoring import score_price


def test_vram_extraction():
    assert extract_vram_gb("MSI GeForce RTX 3060 Ventus 12GB") == 12
    assert extract_vram_gb("ZOTAC RTX 4060 Twin Edge 8GB") == 8
    assert extract_vram_gb("RTX 3060") == 12  # default rule
    assert extract_vram_gb("RX 6700 XT") == 12
    assert extract_vram_gb("RX 6800") == 16


def test_tier_labels():
    # GPU tiers
    assert "Enthusiast" in get_tier_label(27000, "gpu")
    assert "High End" in get_tier_label(21000, "gpu")
    assert "Midrange" in get_tier_label(15000, "gpu")
    assert "Entry Level" in get_tier_label(8500, "gpu")

    # CPU tiers
    assert "High End" in get_tier_label(35000, "cpu")
    assert "Midrange" in get_tier_label(22000, "cpu")
    assert "Budget" in get_tier_label(13000, "cpu")


def test_laptop_igpu_protection():
    # Ultrabook dengan iGPU (misal Core i7-1355U / Iris Xe)
    score_igpu = laptop_combo_score("Core i7-1355U", "Intel Iris Xe")
    assert score_igpu is not None
    assert score_igpu["is_igpu"] is True
    # iGPU combo harus memprioritaskan CPU (75%) bukan GPU rendah (65%)
    assert score_igpu["score"] > 8000

    # Gaming laptop dengan dGPU (RTX 4060)
    score_dgpu = laptop_combo_score("Ryzen 7 7735HS", "RTX 4060")
    assert score_dgpu is not None
    assert score_dgpu["is_igpu"] is False


def test_fair_price_bands():
    prices = [3000000, 3200000, 3400000, 3600000, 4000000]
    res = score_price(3300000, prices)
    assert res.fair_price_low > 0
    assert res.fair_price_high >= res.fair_price_low
    assert res.reference_price == 3400000


def test_facebook_marketplace_source_included():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        listing_fb = RawListing(
            source="facebook_marketplace",
            category="pc",
            raw_title="ASUS Dual RTX 3060 12GB Bekas Mulus",
            raw_price=3200000,
            listing_url="https://facebook.com/marketplace/item/123",
            listing_hash="hash_fb_123",
            condition="second",
            scraped_at=now,
        )
        session.add(listing_fb)
        session.commit()

        comps = _pc_comparisons(
            session,
            AnalyzeRequest(mode="pc", query="RTX 3060 12GB", price=3200000, component_type="gpu", condition="second"),
        )
        assert len(comps) >= 1
        assert comps[0].source == "facebook_marketplace"
