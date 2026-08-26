from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.schemas import AnalyzeRequest
from app.services.analysis import _pc_comparisons, analyze
from app.services.ingestion import ListingInput, ingest_listings


def test_pc_condition_filter_is_strict():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest_listings(
            session,
            "tokopedia",
            [
                ListingInput("MSI RTX 3060 12GB Baru", 7000000, "new-url", condition="new"),
                ListingInput("MSI RTX 3060 12GB Second Bekas", 5500000, "second-url", condition="second"),
                ListingInput("ASUS RTX 3060 12GB tanpa label kondisi", 6500000, "implicit-new-url"),
            ],
        )
        second = _pc_comparisons(
            session,
            AnalyzeRequest(mode="pc", query="RTX 3060", price=6000000, component_type="gpu", condition="second"),
        )
        new = _pc_comparisons(
            session,
            AnalyzeRequest(mode="pc", query="RTX 3060", price=6000000, component_type="gpu", condition="new"),
        )
        assert len(second) == 1 and second[0].condition == "second"
        assert len(new) == 2 and all(item.condition == "new" for item in new)


def test_new_condition_has_transparent_reference_fallback_when_catalog_is_empty():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result, comparisons, _, _ = analyze(
            session,
            AnalyzeRequest(mode="pc", query="RTX 4090", price=30000000, component_type="gpu", condition="new"),
        )
        assert comparisons and comparisons[0].source == "price_reference"
        assert result.reference_price > 0
