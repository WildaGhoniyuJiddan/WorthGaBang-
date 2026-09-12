from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class ScoreResult:
    score: float
    verdict: str
    recommendation: str
    reference_price: int
    delta_percent: float
    fair_price_low: int = 0
    fair_price_high: int = 0
    tier_label: str | None = None


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def score_price(price: int, reference_prices: list[int], is_new_reference: bool = False) -> ScoreResult:
    usable = [value for value in reference_prices if value and value > 0]
    if not usable:
        return ScoreResult(50.0, "data terbatas", "Belum cukup pembanding untuk memberi rekomendasi kuat.", price, 0.0, price, price)

    usable_sorted = sorted(usable)
    reference = int(median(usable_sorted))
    ratio = price / reference
    delta_percent = round((ratio - 1) * 100, 1)

    if is_new_reference:
        # ponytail: band ketat untuk referensi HARGA BARU (retail / konversi USD).
        # Barang bekas di 95% harga baru jelas kemahalan (mending beli baru bergaransi).
        fair_low = int(reference * 0.65)
        fair_high = int(reference * 0.80)
        if ratio <= 0.65:
            verdict = "worth it"
            recommendation = "Harga berada jauh di bawah estimasi harga baru dan layak dipertimbangkan."
            score = 90 + min(10, (0.65 - ratio) * 30)
        elif ratio <= 0.80:
            verdict = "wajar"
            recommendation = "Harga berada di rentang wajar dibanding estimasi harga baru."
            score = 75 + ((0.80 - ratio) / 0.15) * 15
        elif ratio <= 0.90:
            verdict = "ada opsi lebih baik"
            recommendation = "Harga mendekati estimasi harga baru; pertimbangkan beli baru bergaransi atau cari opsi lain."
            score = 60 + ((0.90 - ratio) / 0.10) * 15
        else:
            verdict = "kemahalan"
            recommendation = "Harga terlalu dekat atau melebihi estimasi harga baru; sangat disarankan beli baru bergaransi."
            score = 50 - (ratio - 0.90) * 80
    else:
        if len(usable_sorted) >= 4:
            fair_low = usable_sorted[len(usable_sorted) // 4]
            fair_high = usable_sorted[(3 * len(usable_sorted)) // 4]
        else:
            fair_low = int(reference * 0.90)
            fair_high = int(reference * 1.10)

        if ratio <= 0.90:
            verdict = "worth it"
            recommendation = "Harga berada di bawah median pasar dan layak dipertimbangkan."
            score = 90 + min(10, (0.90 - ratio) * 30)
        elif ratio <= 1.10:
            verdict = "wajar"
            recommendation = "Harga masih berada di rentang wajar berdasarkan pembanding yang tersedia."
            score = 80 - abs(ratio - 1) * 100
        elif ratio <= 1.25:
            verdict = "ada opsi lebih baik"
            recommendation = "Ada pembanding dengan harga lebih rendah; pertimbangkan negosiasi atau opsi lain."
            score = 65 - (ratio - 1.10) * 100
        else:
            verdict = "kemahalan"
            recommendation = "Harga berada cukup jauh di atas median pasar."
            score = 50 - (ratio - 1.25) * 80

    return ScoreResult(
        round(_clamp(score), 1),
        verdict,
        recommendation,
        reference,
        delta_percent,
        fair_low,
        fair_high,
    )

