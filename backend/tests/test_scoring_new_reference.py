from app.services.scoring import score_price


def test_used_item_near_new_price_is_expensive():
    # Barang bekas di rasio ~0.95 (mis. 9.500.000 vs referensi baru 10.000.000)
    # harus divonis "kemahalan", bukan "wajar" (karena lebih baik beli baru bergaransi).
    result = score_price(9_500_000, [10_000_000], is_new_reference=True)
    assert result.verdict == "kemahalan"
    assert result.score <= 50
    assert "harga baru" in result.recommendation.lower()


def test_new_reference_tiers():
    ref = 10_000_000

    # ratio <= 0.65 -> worth it
    res_worth = score_price(6_000_000, [ref], is_new_reference=True)
    assert res_worth.verdict == "worth it"
    assert res_worth.score >= 90

    # ratio 0.66 - 0.80 -> wajar
    res_wajar = score_price(7_500_000, [ref], is_new_reference=True)
    assert res_wajar.verdict == "wajar"

    # ratio 0.81 - 0.90 -> ada opsi lebih baik (mendekati harga baru)
    res_better_opts = score_price(8_500_000, [ref], is_new_reference=True)
    assert res_better_opts.verdict == "ada opsi lebih baik"

    # ratio > 0.90 -> kemahalan
    res_expensive = score_price(9_500_000, [ref], is_new_reference=True)
    assert res_expensive.verdict == "kemahalan"


def test_used_reference_default_remains_unchanged():
    # Jalur default (pembanding listing bekas biasa): 9.5jt vs median 10jt tetap "wajar"
    result = score_price(9_500_000, [10_000_000])
    assert result.verdict == "wajar"
