from app.services.scoring import score_price


def test_below_market_is_worth_it():
    result = score_price(8_000_000, [10_000_000, 10_500_000, 9_500_000])
    assert result.verdict == "worth it"
    assert result.score > 90


def test_high_price_is_expensive():
    result = score_price(14_000_000, [10_000_000, 10_500_000, 9_500_000])
    assert result.verdict == "kemahalan"
    assert result.reference_price == 10_000_000


def test_missing_comparisons_is_explicit():
    result = score_price(5_000_000, [])
    assert result.verdict == "data terbatas"
    assert result.reference_price == 5_000_000

