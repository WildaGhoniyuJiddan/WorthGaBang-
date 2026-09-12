import pytest
from app.db import SessionLocal
from app.schemas import BundleItem, BundleRequest
from app.main import analyze_bundle

def test_bundle_all_items_resolved_and_never_dropped():
    db = SessionLocal()
    payload = BundleRequest(
        bundle_price=2_000_000,
        items=[
            BundleItem(query="Ryzen 5 5600", component_type="cpu"),
            BundleItem(query="XFX Radeon RX 580 8GB GDDR5 - RX-580S85DD6", component_type="gpu"),
        ]
    )
    res = analyze_bundle(payload, db=db)
    
    # 1. Pastikan kedua item ada di breakdown (tidak ada yang hilang!)
    assert len(res.items) == 2, f"Expected 2 items in breakdown, got {len(res.items)}"
    queries = [item.query for item in res.items]
    assert "Ryzen 5 5600" in queries
    assert "XFX Radeon RX 580 8GB GDDR5 - RX-580S85DD6" in queries
    
    # 2. Pastikan kedua item memiliki harga baru dan bekas
    for item in res.items:
        assert item.reference_price > 0, f"Item {item.query} has 0 reference_price"
        assert item.new_reference_price is not None and item.new_reference_price > 0
        assert item.used_reference_price is not None and item.used_reference_price > 0
        
    # 3. Pastikan total penjumlahan benar (kedua komponen, bukan cuma CPU)
    assert res.reference_total >= 4_000_000, f"Expected reference_total >= 4M, got {res.reference_total}"
    assert res.new_reference_total >= 4_000_000
    assert res.used_reference_total >= 2_800_000
    
    # 4. Pastikan verdict akurat (hemat > 50% = worth it)
    assert res.verdict == "worth it"
    assert res.savings_percent > 45.0
    assert res.cross_market_advice is not None
    assert "Total Baru" in res.cross_market_advice
    assert "Total Estimasi Bekas" in res.cross_market_advice


def test_bundle_three_components():
    db = SessionLocal()
    payload = BundleRequest(
        bundle_price=4_000_000,
        items=[
            BundleItem(query="Core i5 12400F", component_type="cpu"),
            BundleItem(query="ASRock B660M Pro RS", component_type="motherboard"),
            BundleItem(query="RAM DDR4 16GB", component_type="ram"),
        ]
    )
    res = analyze_bundle(payload, db=db)
    assert len(res.items) == 3
    assert res.reference_total > 3_500_000
