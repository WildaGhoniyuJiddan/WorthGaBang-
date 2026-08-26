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


def better_alternatives(
    query: str,
    component_type: str,
    price_idr: int,
    usd_to_idr: float,
    max_results: int = 2,
) -> list[dict]:
    """Kandidat sekelas dgn performa/harga lebih baik dr harga penawaran user.

    Syarat kandidat: skor >= 15% di atas skor model user DAN estimasi harga IDR
    <= harga penawaran. Return [{name, score, est_price_idr, gain_percent}].
    """
    base = passmark_score(query, component_type)
    if not base or not price_idr:
        return []
    min_score = base["score"] * 1.15
    pool = [
        entry for entry in (_load().get(component_type) or {}).values()
        if entry["score"] >= min_score and entry.get("price_usd")
        and entry["price_usd"] * usd_to_idr * 1.10 <= price_idr
    ]
    # paling dekat harga (realistis dibeli), lalu performa tertinggi
    pool.sort(key=lambda e: (e["price_usd"], -e["score"]))
    return [
        {
            "name": entry["name"],
            "score": entry["score"],
            "est_price_idr": int(entry["price_usd"] * usd_to_idr * 1.10),
            "gain_percent": round((entry["score"] / base["score"] - 1) * 100),
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


def laptop_combo_score(cpu_text: str | None, gpu_text: str | None) -> dict | None:
    """Skor gabungan unit laptop: GPU 65% + CPU 35% (PassMark).

    Return {"gpu": entri|None, "cpu": entri|None, "score": int} atau None kalau
    GPU & CPU sama-sama tidak dikenali.
    """
    gpu_entry = passmark_score(gpu_text or "", "gpu") if gpu_text else None
    cpu_entry = resolve_cpu_laptop(cpu_text or "") if cpu_text else None
    gscore = (gpu_entry or {}).get("score")
    cscore = (cpu_entry or {}).get("score")
    if gscore and cscore:
        combo = 0.65 * gscore + 0.35 * cscore
    elif gscore or cscore:
        combo = float(gscore or cscore)
    else:
        return None
    return {"gpu": gpu_entry, "cpu": cpu_entry, "score": round(combo)}
