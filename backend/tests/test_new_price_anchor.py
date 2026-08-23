from app.services.analysis import new_price_anchor


def test_gpu_anchors():
    assert 3_000_000 < new_price_anchor("RX 6600") < 4_500_000
    assert new_price_anchor("rtx3060") == new_price_anchor("RTX 3060")
    assert new_price_anchor("RTX 4060 Ti") > new_price_anchor("RTX 3050")


def test_cpu_and_miss():
    assert new_price_anchor("AMD Ryzen 5 5600") > 1_500_000
    assert new_price_anchor("kulkas dua pintu") is None
