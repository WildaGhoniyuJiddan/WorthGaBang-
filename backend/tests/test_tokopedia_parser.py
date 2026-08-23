from app.scrapers.tokopedia import _parse_blocks
from app.services.parsing import detect_condition, parse_price

# Fixture: potongan nyata output Jina Reader Tokopedia (Agustus 2026),
# termasuk kasus yang dulu bikin harga sampah (Rp60 dari "Image 60").
SAMPLE = """Title: Jual rtx 4060 | Tokopedia

URL Source: http://www.tokopedia.com/search?st=product&q=rtx%204060

Markdown Content:
[![Image 1: product-image](https://p16-images-sign-sg.tokopedia-static.net/x.webp) COLORFUL EPOCH N14 - LAPTOP | Intel Core i7-13620H | DDR5 16GB | RTX 4060 8GB - Deep Ocean Blue Rp21.699.000 Hemat s.d 3% Pakai Bonus ![Image 2: rating](https://lf-web-assets.tokopedia-static.net/y.svg) 5.0 3 terjual Central Technology Computer Jakarta Pusat](https://www.tokopedia.com/ctcharco/laptop-i7-rtx4060?extParam=ivf%3Dfalse)

[![Image 3: product-image](https://p16-images-sign-sg.tokopedia-static.net/z.webp) VGA Card Zotac RTX 3060 Ti Twin Edge 8GB SECOND LIKE NEW MULUS Rp4.150.000 12 terjual Toko Bekas Nyaman](https://www.tokopedia.com/bekasnyaman/zotac-3060ti-second)

[![Image 5: product-image](https://p16-images-sign-sg.tokopedia-static.net/w.webp) ASUS Dual RTX 4060 OC Edition 8GB GDDR6 Baru Garansi Resmi Rp5.799.000 27 terjual Official Store ASUS](https://www.tokopedia.com/asustore/dual-4060-oc)

garis bawah bukan produk, harus diabaikan Rp123
"""


def test_parse_price_rejects_bare_numbers():
    # Regresi bug utama: prefix "rp" opsional bikin angka liar jadi harga
    assert parse_price("[![Image 64: product-image]") is None
    assert parse_price("RTX 4060") is None
    assert parse_price("Rp21.699.000") == 21_699_000
    assert parse_price("Rp 5.499.999") == 5_499_999


def test_detect_condition():
    assert detect_condition("VGA RTX 3060 2ND MULUS") == "second"
    assert detect_condition("Laptop bekas masih garansi") == "second"
    assert detect_condition("ASUS ROG baru segel") is None


def test_tokopedia_parser_blocks():
    records = _parse_blocks(SAMPLE)
    titles = " || ".join(r.title for r in records)
    prices = [r.price for r in records]
    assert len(records) == 3, f"dapat {len(records)}: {titles}"
    assert 21_699_000 in prices and 4_150_000 in prices and 5_799_000 in prices
    assert all(p >= 100_000 for p in prices), f"harga sampah masih lolos: {prices}"
    assert all(r.url and "tokopedia.com" in r.url for r in records), titles
    second = [r for r in records if r.condition == "second"]
    assert len(second) == 1 and "SECOND" in second[0].title.upper()


def test_tokopedia_parser_drops_laptop_when_scraping_pc_component():
    records = _parse_blocks(SAMPLE, query="RTX 4060", component_type="gpu")
    assert len(records) == 1
    assert "ASUS Dual RTX 4060" in records[0].title
