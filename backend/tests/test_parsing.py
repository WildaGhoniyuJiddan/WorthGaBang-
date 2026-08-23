from app.services.parsing import detect_category, parse_price, stable_listing_hash


def test_parse_indonesian_prices():
    assert parse_price("Rp 5.499.999") == 5_499_999
    assert parse_price("8,5 juta") == 8_500_000


def test_detect_category():
    assert detect_category("RTX 4060 8GB") == "pc"
    assert detect_category("Laptop ASUS RTX 4060 16GB") == "laptop"


def test_listing_hash_is_stable():
    assert stable_listing_hash("tokopedia", "RTX 4060", 10, "url") == stable_listing_hash("tokopedia", "RTX 4060", 10, "url")

