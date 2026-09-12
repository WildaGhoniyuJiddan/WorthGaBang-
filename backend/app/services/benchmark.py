"""Resolver skor benchmark PassMark + advice "di harga segitu lebih baik X".

Data: app/data/benchmark_scores.json (generator scripts/generate_benchmark_catalog.py,
cron bulanan bareng retail_catalog). Key model lowercase.

Pemakaian di analisis:
  - komponen PC: skor GPU/CPU user vs kandidat katalog -> alternatif konkret.
  - laptop: combo GPU 65% + CPU 35% utk unit user & pembanding; alternatif =
    pembanding sungguhan dgn combo lebih tinggi di harga lebih murah.
"""

import json
import re
from pathlib import Path

_BENCH_PATH = Path(__file__).resolve().parents[1] / "data" / "benchmark_scores.json"
_bench: dict | None = None


def _load() -> dict:
    global _bench
    if _bench is None:
        try:
            _bench = json.loads(_BENCH_PATH.read_text(encoding="utf-8"))
        except Exception:
            _bench = {"cpu": {}, "gpu": {}}
    return _bench


def _sq(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def passmark_score(query: str, component_type: str | None) -> dict | None:
    """Entri PassMark utk model di query. None kalau bukan gpu/cpu / tak ketemu."""
    if component_type not in ("gpu", "cpu"):
        return None
    text = (query or "").lower()
    catalog = _load().get(component_type) or {}
    if not catalog:
        return None

    # 1) exact key ("rtx 4060 ti" -> "geforce rtx 4060 ti" dsb.)
    for probe in (
        f"geforce {text}", f"radeon {text}",
        f"nvidia {text}", f"amd {text}", text,
    ):
        entry = catalog.get(" ".join(probe.split()))
        if entry:
            return entry

    # 2) substring dua arah via squash ('ryzen5 5600x' == 'ryzen 5 5600x')
    qsq = _sq(text)
    best: tuple[int, dict] | None = None
    for key, entry in catalog.items():
        ksq = _sq(key)
        if qsq in ksq or ksq in qsq:
            # ambil yang pendek (paling spesifik menempel query)
            if best is None or len(ksq) < len(_sq(best[1]["name"].lower())):
                best = (len(ksq), entry)
    return best[1] if best else None


def extract_vram_gb(text: str) -> int | None:
    text_low = (text or "").lower()
    m = re.search(r"\b(\d{1,2})\s*gb\b", text_low)
    if m:
        val = int(m.group(1))
        if val in {2, 3, 4, 6, 8, 10, 11, 12, 16, 20, 24}:
            return val
    if "rtx 3060" in text_low and "ti" not in text_low:
        return 12
    if "rx 6700 xt" in text_low or "rx 6750 xt" in text_low:
        return 12
    if "rx 6800" in text_low:
        return 16
    if "rtx 4070" in text_low:
        return 12
    if "rtx 4060" in text_low or "rx 6600" in text_low or "rtx 3050" in text_low or "rtx 2060 super" in text_low:
        return 8
    if "gtx 1660" in text_low or "rtx 2060" in text_low:
        return 6
    if "gtx 1650" in text_low:
        return 4
    return None


def get_tier_label(score: int, component_type: str) -> str:
    if not score:
        return "Standard"
    if component_type == "gpu":
        if score >= 26000:
            return "Enthusiast (4K Ultra Gaming)"
        if score >= 19000:
            return "High End (1440p Ultra)"
        if score >= 13000:
            return "Midrange (1080p Ultra / 1440p Mid)"
        if score >= 7000:
            return "Entry Level (1080p Esports)"
        return "Basic (Office & Casual)"
    elif component_type == "cpu":
        if score >= 32000:
            return "High End (Heavy Productivity & Gaming)"
        if score >= 19000:
            return "Midrange (Solid Gaming & Multitasking)"
        if score >= 11000:
            return "Budget (1080p Gaming & Daily Work)"
        return "Entry Level (Office & Casual)"
    elif component_type == "laptop":
        if score >= 20000:
            return "High End Gaming / Workstation"
        if score >= 13000:
            return "Midrange Gaming / Content Creation"
        if score >= 7500:
            return "Budget Gaming / Fast Productivity"
        return "Ultrabook / Daily Office"
    return "Standard"


def better_alternatives(
    query: str,
    component_type: str,
    price_idr: int,
    usd_to_idr: float,
    max_results: int = 2,
) -> list[dict]:
    """Kandidat sekelas dgn performa/harga lebih baik dr harga penawaran user.

    Syarat kandidat: skor >= 15% di atas skor model user DAN estimasi harga IDR
    <= harga penawaran. Return [{name, score, est_price_idr, gain_percent, vram_gb, tier_label}].
    """
    base = passmark_score(query, component_type)
    if not base or not price_idr:
        return []
    min_score = base["score"] * 1.15
    base_vram = extract_vram_gb(query) if component_type == "gpu" else None

    pool = [
        entry for entry in (_load().get(component_type) or {}).values()
        if entry["score"] >= min_score and entry.get("price_usd")
        and entry["price_usd"] * usd_to_idr * 1.10 <= price_idr
    ]

    # Prioritaskan kandidat yang kapasitas VRAM-nya tidak downgrade jika user punya VRAM besar
    if base_vram and base_vram >= 12:
        vram_kept = [e for e in pool if (extract_vram_gb(e["name"]) or 0) >= base_vram]
        if vram_kept:
            pool = vram_kept

    # paling dekat harga (realistis dibeli), lalu performa tertinggi
    pool.sort(key=lambda e: (e["price_usd"], -e["score"]))
    return [
        {
            "name": entry["name"],
            "score": entry["score"],
            "est_price_idr": int(entry["price_usd"] * usd_to_idr * 1.10),
            "gain_percent": round((entry["score"] / base["score"] - 1) * 100),
            "vram_gb": extract_vram_gb(entry["name"]) if component_type == "gpu" else None,
            "tier_label": get_tier_label(entry["score"], component_type),
        }
        for entry in pool[:max_results]
    ]


# ---------------- Laptop: skor combo GPU+CPU ----------------

_CPU_RE = re.compile(
    r"\b(ryzen(?:\s*ai)?\s*[3579]|core\s*i[3579]|ultra\s*[579])\s*-?\s*(\d{4,5}[a-z]{0,3})\b",
    re.IGNORECASE,
)


def resolve_cpu_laptop(text: str) -> dict | None:
    """CPU laptop -> entri PassMark. Katalog CPU desktop-only, jadi setelah
    nama persis gagal, pakai proksi: keluarga+tier sama (i5/Ryzen 5 dll),
    nomor model terdekat ('Core i5-12450H' -> proksi 'i5-12400')."""
    m = _CPU_RE.search(text or "")
    if not m:
        return None
    full = m.group(0).lower()
    catalog = _load().get("cpu") or {}
    mobile = _load().get("cpu_mobile") or {}

    # 0) katalog MOBILE persis (PassMark punya data CPU laptop sendiri)
    qsq = _sq(full)
    best_m = None
    for key, entry in mobile.items():
        ksq = _sq(key)
        if qsq and (qsq in ksq or ksq in qsq):
            if best_m is None or len(ksq) < len(_sq(best_m["name"].lower())):
                best_m = entry
    if best_m:
        return best_m

    # 1) nama persis / substring di katalog desktop via squash
    qsq = _sq(full)
    best = None
    for key, entry in catalog.items():
        ksq = _sq(key)
        if qsq and (qsq in ksq or ksq in qsq):
            if best is None or len(ksq) < len(_sq(best["name"].lower())):
                best = entry
    if best:
        return best

    # 2) proksi: famili+tier sama, nomor terdekat (mobile & desktop beda penomoran)
    tier = re.search(r"(i[3579]|[3579])", full)
    if not tier:
        return None
    tier_ch = tier.group(1)[-1]
    is_intel = "core" in full or "ultra" in full
    want_num = re.sub(r"[a-z]+$", "", m.group(2).lower())
    if not want_num.isdigit():
        return None

    def _cand(key: str):
        cm = _CPU_RE.search(key)
        if not cm:
            return None
        kfull = cm.group(0).lower()
        ktier = re.search(r"(i[3579]|[3579])", kfull)
        if not ktier or ktier.group(1)[-1] != tier_ch:
            return None
        kintel = "core" in kfull or "ultra" in kfull
        if kintel != is_intel:
            return None
        knum = re.sub(r"[a-z]+$", "", cm.group(2))
        if not knum.isdigit():
            return None
        return int(knum)

    pool = []
    for key, entry in catalog.items():
        knum = _cand(key)
        if knum is not None:
            pool.append((abs(knum - int(want_num)), key, entry))
    if not pool:
        return None
    pool.sort(key=lambda x: (x[0], len(_sq(x[1]))))
    return pool[0][2]


def _is_integrated_gpu(gpu_text: str | None) -> bool:
    if not gpu_text:
        return True
    low = gpu_text.lower().strip()
    if not low:
        return True
    igpu_tokens = [
        "iris", "uhd", "hd graphics", "vega", "radeon graphics",
        "integrated", "shared", "intel graphics", "intel hd",
        "apple", "m1", "m2", "m3", "m4", "snapdragon", "adreno",
    ]
    return any(tok in low for tok in igpu_tokens)


def laptop_combo_score(cpu_text: str | None, gpu_text: str | None) -> dict | None:
    """Skor gabungan unit laptop:
    - Gaming laptop (dGPU): GPU 65% + CPU 35%
    - Ultrabook / non-gaming (iGPU): CPU 75% + GPU 25% (melindungi laptop produktivitas)
    """
    gpu_entry = passmark_score(gpu_text or "", "gpu") if gpu_text else None
    cpu_entry = resolve_cpu_laptop(cpu_text or "") if cpu_text else None
    gscore = (gpu_entry or {}).get("score")
    cscore = (cpu_entry or {}).get("score")
    is_igpu = _is_integrated_gpu(gpu_text)

    if is_igpu:
        # Ultrabook / laptop produktivitas: CPU adalah metrik utama
        if cscore and gscore:
            combo = 0.75 * cscore + 0.25 * gscore
        elif cscore:
            combo = float(cscore)
        elif gscore:
            combo = float(gscore)
        else:
            return None
    else:
        # Gaming laptop dengan GPU diskrit
        if gscore and cscore:
            combo = 0.65 * gscore + 0.35 * cscore
        elif gscore or cscore:
            combo = float(gscore or cscore)
        else:
            return None

    score_val = round(combo)
    return {
        "gpu": gpu_entry,
        "cpu": cpu_entry,
        "score": score_val,
        "is_igpu": is_igpu,
        "tier_label": get_tier_label(score_val, "laptop"),
    }
