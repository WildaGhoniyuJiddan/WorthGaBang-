import pytest
from app.db import SessionLocal
from app.schemas import AnalyzeRequest
from app.services.analysis import analyze

def test_acer_aspire_7_pro_comparisons():
    db = SessionLocal()
    req = AnalyzeRequest(
        mode="laptop",
        query="Acer Aspire 7 Pro",
        price=14_000_000,
        condition="new",
        cpu="i5-13420H",
        gpu="RTX 3050",
        ram_gb=16,
        storage_gb=512,
    )
    result, comparisons, freshness, alternatives = analyze(db, req)
    
    # Harus punya banyak pembanding berkualitas
    assert len(comparisons) >= 5, f"Expected at least 5 comparisons, got {len(comparisons)}"
    
    # Median harus masuk akal (antara 12jt - 16.5jt untuk laptop baru RTX 3050)
    assert 12_000_000 <= result.reference_price <= 16_500_000, f"Unreasonable reference price: {result.reference_price}"
    
    # Pembanding teratas harus memuat produk Acer Aspire
    top_titles = " ".join([c.title.lower() for c in comparisons[:3]])
    assert "aspire" in top_titles or "acer" in top_titles, f"Top comparisons should be Acer/Aspire, got: {top_titles}"
    
    # Verdict untuk harga 14jt di antara pasar 12.5-16.5jt harus wajar / worth it
    assert result.verdict in ("wajar", "worth it"), f"Unexpected verdict: {result.verdict}"

    # Dual-market intelligence assertions:
    assert result.new_reference_price is not None, "new_reference_price should be computed"
    assert 12_000_000 <= result.new_reference_price <= 16_500_000, f"Unreasonable new_reference_price: {result.new_reference_price}"
    
    assert result.used_reference_price is not None, "used_reference_price should be computed"
    assert 8_000_000 <= result.used_reference_price <= 13_500_000, f"Unreasonable used_reference_price: {result.used_reference_price}"
    
    assert result.cross_market_advice is not None, "cross_market_advice should be provided"
    assert "pasar baru" in result.cross_market_advice.lower(), "cross_market_advice should mention new market"
    assert "pasar bekas" in result.cross_market_advice.lower(), "cross_market_advice should mention used market"

    # Pembanding harus memiliki tag kondisi ('new' dan 'second')
    conditions = set(c.condition for c in comparisons)
    assert "new" in conditions, "Should have 'new' comparisons"
    assert "second" in conditions, "Should have 'second' comparisons"


def test_acer_used_laptop_evaluation():
    db = SessionLocal()
    req = AnalyzeRequest(
        mode="laptop",
        query="Acer Nitro 5",
        price=10_000_000,
        condition="second",
        gpu="RTX 3050",
    )
    result, comparisons, freshness, alternatives = analyze(db, req)
    
    assert len(comparisons) >= 3
    # Harus di-evaluasi terhadap pasar bekas
    assert result.used_reference_price is not None
    assert result.verdict in ("wajar", "worth it")
    assert result.cross_market_advice is not None
    assert "pasar bekas" in result.cross_market_advice.lower()
