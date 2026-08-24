"""Self-check scraper komponen retail: pemetaan kategori, match_score, dan fetch real.

Jalankan: python tests/test_komponen_retail.py  (atau pytest tests/)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.scrapers.komponen_retail import KomponenRetailScraper, category_for_query, match_score


def test_komponen_retail_scraper() -> None:
    # kategori mapping
    assert category_for_query("RTX 3060 bekas") == "vga"
    assert category_for_query("ryzen 5 5600") == "processor"
    assert category_for_query("core i5 12400F baru") == "processor"
    assert category_for_query("samsung ssd 1tb") == "ssd"
    assert category_for_query("laptop gaming murah") is None

    # match_score: nomor model wajib match
    assert match_score("rtx 3060", "MSI GeForce RTX 3060 Ventus 2X") == 1.0
    assert match_score("rtx 3060", "MSI GeForce RTX 5080 Gaming Trio") == 0.0
    assert match_score("rtx 3060 ti", "Zotac RTX 3060 Ti Twin Edge") == 1.0
    assert match_score("core i5 12400", "Intel Core i5-12400F Box") > 0.5
    assert match_score("ryzen 5 5600", "AMD Ryzen 7 5800X") == 0.0

    # fetch real ke API sumber (butuh jaringan)
    records = KomponenRetailScraper(max_records=10).fetch("RTX 3060")
    assert records, "fetch RTX 3060 harus mengembalikan hasil"
    for record in records:
        assert record.price and record.price >= 100_000, f"harga aneh: {record}"
        assert "3060" in record.title.lower().replace("-", "").replace(" ", "") or "3060" in record.title
    print(f"OK: {len(records)} listing RTX 3060 dari API komponen retail")
    for r in records[:3]:
        print(f"  {r.title[:60]} = Rp{r.price:,}")


if __name__ == "__main__":
    test_komponen_retail_scraper()
