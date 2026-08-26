import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import LaptopUnit, RawListing, ScrapeRun
from ..schemas import AnalyzeRequest, Comparison, Freshness
from .relevance import component_type_from_query, is_relevant_pc_listing
from .benchmark import better_alternatives, laptop_combo_score, passmark_score
from .scoring import ScoreResult, score_price


def _tokens(value: str) -> set[str]:
    # Separate letters and digits so 'rx6600' and 'rx 6600' both yield {'rx','6600'}
    return {token for token in re.findall(r"[a-z]+|\d+", (value or "").lower()) if len(token) > 1}


_CATEGORY_WORDS = {
    # Kata jenis komponen di query user — hampir tak pernah ada di judul
    # marketplace ("Motherboard B650" vs judul "GIGABYTE B650M ...").
    # Dikeluarkan dari similarity supaya gak mematikan skor.
    "gpu", "vga", "card",
    "cpu", "processor", "prosesor",
    "ram", "memori", "memory",
    "ssd", "hdd", "nvme", "storage", "harddisk", "hardisk",
    "motherboard", "mobo", "mainboard",
}


def _similarity(query: str, title: str) -> float:
    wanted = _tokens(query)
    actual = _tokens(title)
    if not wanted or not actual:
        return 0.0
    wanted -= _CATEGORY_WORDS or set()
    if not wanted:
        return 0.0
    # Token model yang ada di query tapi TIDAK di judul = penalti keras.
    # "rtx 4060 8gb" vs "rtx 4060 ti 8gb": token 'ti' ekstra di judul bukan
    # masalah, tapi sebaliknya judul tanpa token yang diminta user harus gugur.
    missing = wanted - actual
    if missing:
        return round(1.0 - 0.5 * len(missing) / len(wanted), 3) if len(missing) < len(wanted) / 2 else 0.0
    return round(len(wanted & actual) / len(wanted), 3)


def _model_tokens(value: str, component_type: str | None) -> set[str]:
    """Token identitas produk (chipset+suffix+kapasitas). Judul pembanding
    wajib memuat semua token ini, bukan sekadar mirip."""
    text = (value or "").lower()
    tokens: list[str] = []
    m = re.search(r"\b(rtx|gtx|rx)\s*(\d{3,4})\s*(ti|super|xt)?\b", text)
    if m:
        tokens += [m.group(1), m.group(2)] + ([m.group(3)] if m.group(3) else [])
        return set(tokens)
    m = re.search(r"\b(ryzen\s*[3579]|core\s*i[3579])\s*-?\s*(\d{4,5})([a-z]{0,2})?\b", text)
    if m:
        fam = "ryzen" if "ryzen" in m.group(1) else "core"
        tokens += [fam, m.group(2)] + ([m.group(3)] if m.group(3) else [])
        return set(tokens)
    ddr = re.search(r"ddr\s*([345])", text)
    gb = re.search(r"(\d{1,2})\s*gb\b", text)
    if ddr and gb and component_type == "ram":
        return {"ddr" + ddr.group(1), gb.group(1)}
    tb = re.search(r"(\d)\s*tb\b", text)
    if component_type == "storage":
        kind = ("nvme" if re.search(r"\bnvme\b|\bm\.?2\b", text)
                else ("ssd" if re.search(r"\bssd\b", text) else None))
        size = (gb.group(1) if gb else (tb.group(1) if tb else None))
        if kind and size:
            return {kind, size}
    if component_type == "motherboard":
        # Identitas mobo = chipset persis. B650M (mATX) & B650E masih sekelas
        # B650, tapi B760 (Intel) produk beda total.
        chipset = re.search(r"\b([abxzi]\d{3})[a-z]{0,2}\b", text)
        return {chipset.group(1)} if chipset else set()
    return set()


# ponytail: harga BARU referensi (USD street dari PCPartPicker dataset) -> IDR.
# Kurs & diskon retail ID di-hardcode; kalau mau presisi, ambil kurs harian API.
USD_TO_IDR = 16_500
RETAIL_MARKUP = 1.10  # harga retail Indonesia biasanya ~10% di atas USD street

_NEW_PRICE_REF_PATH = Path(__file__).resolve().parents[2] / "app" / "data" / "new_price_reference.json"
_new_price_ref: dict | None = None


def _load_new_price_ref() -> dict:
    global _new_price_ref
    if _new_price_ref is None:
        try:
            _new_price_ref = json.loads(_NEW_PRICE_REF_PATH.read_text(encoding="utf-8"))
        except Exception:
            _new_price_ref = {"gpu": {}, "cpu": {}}
    return _new_price_ref


def _anchor_key(query: str) -> str | None:
    """Key model GPU/CPU dari query; format sama dengan generator anchor komponen retail."""
    q = " ".join((query or "").lower().split())
    m = re.search(r"(rtx|gtx)\s*(\d{3,4})\s*(ti|super)?", q)
    if m:
        return f"{m.group(1)} {m.group(2)}{(' ' + m.group(3)) if m.group(3) else ''}"
    m = re.search(r"rx\s*(\d{4})\s*(xt)?", q)
    if m:
        return f"rx {m.group(1)}{(' xt') if m.group(2) else ''}"
    m = re.search(r"ryzen\s*([3579])\s*((?:9\d{3}|[357]\d{3}))", q)
    if m:
        return f"ryzen {m.group(1)} {m.group(2)}"
    m = re.search(r"core i([3579])\s*-?\s*((?:10|11|12|13|14)\d{3})", q)
    if m:
        return f"core i{m.group(1)} {m.group(2)}"
    return None


def _mobo_anchor(query: str) -> int | None:
    """Harga retail mobo dari katalog EK: match nama paling mirip (overlap token)."""
    cat = _load_retail_catalog().get("motherboard") or []
    qtok = {t for t in re.findall(r"[a-z0-9]+", (query or "").lower()) if len(t) > 1}
    best: tuple[float, int] | None = None
    for prod in cat:
        price = prod.get("price")
        model = (prod.get("model") or "").lower()
        if not isinstance(price, int) or not model:
            continue
        ptok = {t for t in re.findall(r"[a-z0-9]+", model) if len(t) > 1}
        if qtok and ptok and qtok <= ptok:
            overlap = len(qtok & ptok) / len(qtok)
            if best is None or overlap > best[0]:
                best = (overlap, price)
    return best[1] if best else None


def new_price_anchor(query: str, component_type: str | None = None) -> int | None:
    """Harga BARU referensi (IDR) untuk query GPU/CPU/ram/storage, None kalau gak ketemu.

    Prioritas: harga retail IDR real dari sumber komponen retail:
      - gpu/cpu: bucket retail_idr di new_price_reference.json
      - ram/storage: bentuk kanonik di retail_catalog.json (cron bulanan)
    Fallback gpu/cpu: konversi USD street PCPartPicker -> IDR.
    """
    # Section pasif: anchor dari katalog retail kanonik (RAM DDR4 16GB dll).
    ctype = component_type or component_type_from_query(query)
    if ctype in ("ram", "storage"):
        canon = _load_retail_catalog().get(f"{ctype}_canonical") or {}
        key = _canonical_key(query, ctype)
        price = canon.get(key)
        return int(price) if price else None

    ref = _load_new_price_ref()
    if ctype == "motherboard":
        return _mobo_anchor(query)
    key = _anchor_key(query)
    if not key:
        return None

    # ponytail: exact-match saja utk harga retail — "rtx 3060 ti" itu produk BEDA,
    # bukan varian "rtx 3060", jadi tidak boleh ikut median.
    for bucket in ("gpu", "cpu"):
        price = _load_new_price_ref().get("retail_idr", {}).get(bucket, {}).get(key)
        if price:
            return int(price)

    usd = ref.get("gpu", {}).get(key) or ref.get("cpu", {}).get(key)
    if not usd:
        return None
    return int(usd * USD_TO_IDR * RETAIL_MARKUP)


def _is_relevant_pc_listing(query: str, title: str, component_type: str | None) -> bool:
    return is_relevant_pc_listing(query, title, component_type)


_RETAIL_CATALOG_PATH = Path(__file__).resolve().parents[2] / "app" / "data" / "retail_catalog.json"
_retail_catalog: dict | None = None


def _load_retail_catalog() -> dict:
    global _retail_catalog
    if _retail_catalog is None:
        try:
            _retail_catalog = json.loads(_RETAIL_CATALOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            _retail_catalog = {}
    return _retail_catalog


def _canonical_key(value: str, ctype: str) -> str | None:
    """Bentuk kanonik dari query bebas: 'ram ddr4 16gb' -> 'RAM DDR4 16GB'."""
    text = (value or "").lower()
    if ctype == "ram":
        ddr = re.search(r"ddr\s*([345])", text)
        gb = re.search(r"(\d{1,2})\s*gb\b", text)
        if ddr and gb:
            return f"RAM DDR{ddr.group(1)} {gb.group(1)}GB"
        return None
    kind = ("SSD" if re.search(r"\b(ssd|nvme|m\.?2)\b", text)
            else ("HDD" if re.search(r"\bhdd\b|\bharddisk\b|\bhardisk\b", text) else None))
    if not kind:
        return None
    if kind == "SSD":
        kind = "SSD NVMe" if re.search(r"nvme", text) else ("SSD SATA" if re.search(r"sata", text) else "SSD")
    gb = re.search(r"(\d{1,3})\s*gb\b", text)
    tb = re.search(r"(\d)\s*tb\b", text)
    size = f"{gb.group(1)}GB" if gb else (f"{tb.group(1)}TB" if tb else None)
    return f"{kind} {size}" if size else None


def _age_label(seconds: int | None) -> str:
    if seconds is None:
        return "belum ada data"
    if seconds < 60:
        return "baru saja"
    if seconds < 3600:
        return f"{seconds // 60} menit lalu"
    if seconds < 86_400:
        return f"{seconds // 3600} jam lalu"
    return f"{seconds // 86_400} hari lalu"


def _freshness_for_source(session: Session, source: str) -> Freshness:
    run = session.scalar(
        select(ScrapeRun).where(ScrapeRun.source == source).order_by(desc(ScrapeRun.started_at)).limit(1)
    )
    timestamp = run.finished_at if run and run.status == "success" else None
    if timestamp is None:
        timestamp = session.scalar(select(RawListing.scraped_at).where(RawListing.source == source).order_by(desc(RawListing.scraped_at)).limit(1))
    now = datetime.now(timezone.utc)
    if timestamp is None:
        age = None
    else:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age = max(0, int((now - timestamp).total_seconds()))
    return Freshness(
        last_updated_at=timestamp,
        age_seconds=age,
        label=_age_label(age),
        is_stale=age is None or age > get_settings().stale_after_hours * 3600,
        primary_source=source,
    )


def freshness(session: Session, preferred_source: str = "facebook_marketplace") -> Freshness:
    # ponytail: source names match raw_listings values (facebook_marketplace dari
    # ekstensi, tokopedia dari scraper, komponen_retail/notebook_retail dari API EK).
    candidates = ["facebook_marketplace", "tokopedia", "komponen_retail", "notebook_retail"]
    fresh = [_freshness_for_source(session, source) for source in candidates]
    available = [item for item in fresh if item.last_updated_at is not None and not item.is_stale]
    if available:
        selected = next((item for item in available if item.primary_source == preferred_source), available[0])
    else:
        selected = next((item for item in fresh if item.last_updated_at is not None), fresh[0])
    return selected


def all_freshness(session: Session) -> dict[str, Freshness]:
    return {source: _freshness_for_source(session, source) for source in ("facebook_marketplace", "tokopedia")}


def _gpu_sig(text: str) -> str | None:
    """Signature GPU ('RTX 4060 Ti' -> 'rtx4060ti'). None kalau tidak disebut."""
    m = re.search(r"\b(rtx|gtx|rx)\s*(\d{3,4})\s*(ti|super|xt)?\b", (text or "").lower())
    return f"{m.group(1)}{m.group(2)}{m.group(3) or ''}" if m else None


def _gpu_name(text: str) -> str | None:
    """Nama GPU ternormalisasi utk resolver PassMark ('rtx 4060')."""
    m = re.search(r"\b(rtx|gtx|rx)\s*(\d{3,4})\s*(ti|super|xt)?\b", (text or "").lower())
    return f"{m.group(1)} {m.group(2)}{( ' ' + m.group(3)) if m.group(3) else ''}" if m else None


def _cpu_sig(text: str) -> str | None:
    """Signature CPU laptop ('Core i5-12450H' -> 'corei512450h', 'i7 13650HX' -> 'i713650hx')."""
    m = re.search(r"\b(ryzen(?:\s*ai)?\s*[3579]|core\s*i[3579]|ultra\s*[579]|i[3579])\s*-?\s*(\d{4,5}[a-z]{0,3}|[a-z]{1,4}\d{3}[a-z]{0,3})?\b", (text or "").lower())
    if not m:
        return None
    fam = re.sub(r"\s+", "", m.group(1))
    num = m.group(2) or ""
    if not num:
        return None
    return fam + num


def _cpu_name(text: str) -> str | None:
    """Nama CPU utk PassMark ('core i5 12450h')."""
    sig = _cpu_sig(text)
    if not sig:
        return None
    return re.sub(r"(corei|ryzen|ultra)", lambda mm: {"corei": "core i", "ryzen": "ryzen ", "ultra": "ultra "}[mm.group(1)], sig, count=1)


def _pc_comparisons(session: Session, request: AnalyzeRequest) -> list[Comparison]:
    # ponytail: ambil per-sumber (bukan satu jendela global) — kalau satu jendela,
    # sumber yg discrape paling akhir mendorong sumber lain keluar dari limit.
    # Katalog retail EK pakai category = jenis komponen (vga/processor/...),
    # marketplace pakai "pc". Kalau katalog >20k listing, pindahkan filter ke SQL.
    rows = []
    for source, cats in (
        ("komponen_retail", ("vga", "processor", "motherboard", "ram", "ssd", "harddisk")),
        ("tokopedia", ("pc",)),
        ("facebook", ("pc",)),
    ):
        rows += session.scalars(
            select(RawListing).where(
                RawListing.category.in_(cats),
                RawListing.raw_price.is_not(None),
                RawListing.source == source,
            ).order_by(desc(RawListing.scraped_at)).limit(6000)
        ).all()
    scored = [
        (_similarity(request.query, row.raw_title), row)
        for row in rows
        if _is_relevant_pc_listing(request.query, row.raw_title, request.component_type)
    ]
    # Hard gate identitas: judul harus memuat token model persis dari query
    # ("RTX 4060 8GB" gak boleh dibandingkan dengan "RTX 4060 Ti" — produk
    # beda, harga jauh). Ini lebih penting daripada skor kemiripan.
    required = _model_tokens(request.query, request.component_type)
    if required:
        scored = [
            (score, row) for score, row in scored
            if _model_tokens(row.raw_title, request.component_type) == required
        ]
    # butuh kemiripan token tinggi (>=0.75) supaya "RX 6600" tidak membandingkan
    # diri dengan PC build yang iseng mention RX 6600 atau laptop seri lain
    matching = [item for item in scored if item[0] >= 0.75]
    if not matching:
        return []
    if request.condition and request.condition != "any":
        wanted = request.condition
        same = [item for item in matching if (item[1].condition or "new") == wanted]
        # kalau kondisi itu gak ada samsek, jangan paksa pakai lawannya
        matching = same
        if not matching:
            return []
    # outlier guard: median robust, tapi IQR ekstrem tetap bisa narik anchor;
    # buang harga di luar [Q1-1.5xIQR, Q3+1.5xIQR] sebelum pilih pembanding.
    matching.sort(key=lambda item: (item[0], item[1].scraped_at), reverse=True)
    top = matching[:40]
    prices = sorted(item[1].raw_price or 0 for item in top)
    q1 = prices[max(0, len(prices) // 4)]
    q3 = prices[min(len(prices) - 1, (3 * len(prices)) // 4)]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inliers = [item for item in top if lo <= (item[1].raw_price or 0) <= hi]
    top = inliers or top
    anchor = prices[len(prices) // 2]
    # pilih listing yang harganya paling dekat dengan median supaya output
    # comparisons representatif, bukan ekstrem termurah/termahal.
    # Interleave per-sumber: tiap sumber dpt kuota merata lalu di-round-robin,
    # supaya katalog retail gak selalu kalah dari marketplace yg discrape terakhir.
    top.sort(key=lambda item: abs((item[1].raw_price or 0) - anchor))
    by_source: dict[str, list] = {}
    for item in top:
        by_source.setdefault(item[1].source or "lain", []).append(item)
    quota = max(2, (24 + len(by_source) - 1) // len(by_source))
    pools = [pool[:quota] for pool in by_source.values()]
    selected = []
    while any(pools) and len(selected) < 24:
        for pool in pools:
            if pool and len(selected) < 24:
                selected.append(pool.pop(0))
    return [
        Comparison(
            title=row.raw_title,
            price=row.raw_price or 0,
            source=row.source,
            listing_url=row.listing_url,
            similarity=similarity,
            condition=row.condition or "new",
        )
        for similarity, row in selected
    ]


def _cpu_tier(sig: str | None) -> str | None:
    """Tier CPU ('corei712700h' -> '7') utk pencocokan sekelas."""
    if not sig:
        return None
    m = re.search(r"(?:corei|ryzen|ultra|ryzenai)([3579])", sig)
    return m.group(1) if m else None


_MD_JUNK_RE = re.compile(r"\[!\[[^\]]*\]\([^)]*\)]?\([^)]*\)|!\[[^\]]*\]\([^)]*\)|\[Image\s*[^\]]*\]", re.IGNORECASE)


def _clean_title(text: str | None) -> str:
    """Buang sampah markdown/gambar dari judul hasil scrape."""
    cleaned = _MD_JUNK_RE.sub(" ", text or "")
    return " ".join(cleaned.split())[:180]


def _laptop_comparisons(session: Session, request: AnalyzeRequest) -> list[Comparison]:
    rows = session.scalars(
        select(LaptopUnit).where(LaptopUnit.price > 0).order_by(desc(LaptopUnit.scraped_at)).limit(5000)
    ).all()
    # Spek yang diisi user jadi HARD-GATE (ala komponen PC):
    #   - GPU & CPU: token model PERSIS — "RTX 4060" gak boleh kena "RTX 4050".
    #   - RAM & Storage: minimal sama dgn input (16GB boleh pembanding 32GB).
    # Unit tanpa data spek di dimensi yg diminta = gugur (bukan tebak-tebakan).
    want_gpu = _gpu_sig(request.gpu or request.query)
    want_cpu = _cpu_sig(request.cpu)
    # CPU cuma diisi di kolom query? coba ekstrak dari sana (GPU sudah diambil dulu).
    if want_cpu is None and not request.gpu:
        want_cpu = _cpu_sig(request.query)
    min_ram = request.ram_gb or None
    min_storage = request.storage_gb or None
    scored: list[tuple[float, LaptopUnit]] = []
    for row in rows:
        if request.condition and request.condition != "any" and row.condition and row.condition != request.condition:
            continue
        title = f"{row.brand or ''} {row.model or ''} {row.cpu or ''} {row.gpu or ''}"
        got_gpu = _gpu_sig(title)
        got_cpu = _cpu_sig(title)
        # GPU = HARD-GATE: identitas performa utama laptop gaming.
        if want_gpu and got_gpu != want_gpu:
            continue
        # CPU bertingkat: persis > sekelas > LEBIH TINGGI (opsi menarik, diterima)
        # > tak terbaca (penalti) > KELAS DI BAWAH = bukan pembanding wajar.
        cpu_penalty = 0.0
        if want_cpu:
            got_tier = _cpu_tier(got_cpu) if got_cpu else None
            if got_cpu == want_cpu:
                pass
            elif got_tier == _cpu_tier(want_cpu):
                cpu_penalty = 0.15
            elif got_tier and got_tier > _cpu_tier(want_cpu):
                cpu_penalty = 0.2
            elif got_cpu is None:
                cpu_penalty = 0.25
            else:
                continue  # kelas di bawah yang diminta (i5 saat minta i7)
        if min_ram and (row.ram_gb or 0) < min_ram:
            continue
        if min_storage and (row.storage_gb or 0) < min_storage:
            continue
        wanted = _tokens(" ".join(filter(None, [request.brand or "", request.query])))
        actual = _tokens(f"{row.brand or ''} {row.model or ''}")
        similarity = round(len(wanted & actual) / len(wanted), 3) if wanted else 0.3
        similarity = max(0.05, similarity - cpu_penalty)
        scored.append((similarity, row))
    pool = sorted(scored, key=lambda item: (item[0], item[1].scraped_at), reverse=True)
    if not pool:
        return [], {}
    # Interleave per-sumber (retail vs marketplace) biar variatif + dedup judul
    # (listing sama sering terindeks 2-3x dari query berbeda).
    by_source: dict[str, list] = {}
    seen_titles: set[str] = set()
    for item in pool:
        key = item[1].source or "lain"
        title_key = _clean_title(item[1].model or item[1].brand or "Laptop").lower()[:80]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        by_source.setdefault(key, []).append(item)
    quota = max(2, (24 + len(by_source) - 1) // len(by_source))
    pools = [p[:quota] for p in by_source.values()]
    selected = []
    while any(pools) and len(selected) < 24:
        for p in pools:
            if p and len(selected) < 24:
                selected.append(p.pop(0))
    return [
        Comparison(
            title=_clean_title(row.model or row.brand or "Laptop"),
            price=row.price,
            source=row.source,
            listing_url=row.listing_url,
            similarity=similarity,
            condition=row.condition,
        )
        for similarity, row in selected
    ], {
        # teks spek utk resolver benchmark per pembanding terpilih
        _clean_title(row.model or row.brand or "Laptop"): {"cpu": row.cpu, "gpu": row.gpu}
        for _, row in selected
    }


def _laptop_benchmark_advice(request: AnalyzeRequest, comparisons, spec_map: dict, result) -> tuple[str, list[dict]]:
    """Advice PassMark utk laptop: combo GPU+CPU unit user vs pembanding sungguhan.

    Alternatif hanya dari unit nyata di database (bukan katalog global) supaya
    harga & ketersediaannya real. Return (recommendation_tambahan, alternatives).
    """
    if result.verdict not in ("kemahalan", "ada opsi lebih baik"):
        return "", []
    user_combo = laptop_combo_score(
        request.cpu or request.query,
        request.gpu or request.query,
    )
    if not user_combo:
        return "", []
    candidates = []
    for c in comparisons:
        spec = spec_map.get(c.title) or {}
        combo = laptop_combo_score(spec.get("cpu"), spec.get("gpu"))
        if combo and c.price <= request.price:
            candidates.append({
                "title": c.title,
                "price": c.price,
                "combo": combo,
            })
    min_score = user_combo["score"] * 1.15
    better = [x for x in candidates if x["combo"]["score"] >= min_score]
    better.sort(key=lambda x: x["combo"]["score"], reverse=True)
    alts = [
        {
            "name": x["title"],
            "score": x["combo"]["score"],
            "est_price_idr": x["price"],
            "gain_percent": round((x["combo"]["score"] / user_combo["score"] - 1) * 100),
        }
        for x in better[:2]
    ]
    if not alts:
        return "", []
    best = alts[0]
    advice = (
        f"Di harga segitu lebih baik {best['name']}: performa +{best['gain_percent']}% "
        f"(dijual Rp{best['est_price_idr']:,}, skor combo {best['score']:,} vs {user_combo['score']:,})."
    ).replace(",", ".")
    return advice, alts


def _benchmark_advice(request: AnalyzeRequest, result) -> tuple[str, list[dict]]:
    """Advice PassMark utk verdict jelek: "di harga segitu lebih baik X (+N%)".

    Return (recommendation_tambahan, alternatives). Kosong kalau model gak
    ketemu di katalog benchmark atau tidak ada kandidat yang layak.
    """
    ctype = request.component_type or component_type_from_query(request.query)
    if result.verdict not in ("kemahalan", "ada opsi lebih baik"):
        return "", []
    alts = better_alternatives(request.query, ctype, request.price, USD_TO_IDR)
    if not alts:
        return "", []
    best = alts[0]
    advice = (
        f"Di harga segitu lebih baik {best['name']}: performa +{best['gain_percent']}% "
        f"(est. Rp{best['est_price_idr']:,}) dengan skor PassMark {best['score']:,}."
    ).replace(",", ".")
    return advice, alts


def analyze(session: Session, request: AnalyzeRequest):
    if request.mode == "pc":
        comparisons = _pc_comparisons(session, request)
        spec_map = {}
    else:
        comparisons, spec_map = _laptop_comparisons(session, request)
    result = score_price(request.price, [comparison.price for comparison in comparisons])
    # fallback anchor harga BARU dari katalog referensi (buildcores+PCPartPicker)
    # kalau listing second yang relevan gak cukup untuk kasih verdict.
    if (result.verdict == "data terbatas" or not comparisons) and request.condition != "second":
        ref_new = new_price_anchor(request.query, request.component_type)
        if ref_new:
            result = score_price(request.price, [ref_new])
            if not comparisons:
                comparisons = [
                    Comparison(
                        title=f"Reference harga baru {request.query} (katalog retail, bukan listing marketplace)",
                        price=ref_new,
                        source="price_reference",
                        listing_url=None,
                        similarity=0.5,
                        condition="new",
                    )
                ]
    # Sumber utama = sumber paling banyak di pembanding (bukan cuma baris pertama).
    if comparisons:
        counts: dict[str, int] = {}
        for c in comparisons:
            counts[c.source] = counts.get(c.source, 0) + 1
        selected_source = max(counts, key=counts.get)
    else:
        selected_source = "tokopedia"
    # Sinyal benchmark PassMark: kalau harga jelek, kasih alternatif konkret.
    if request.mode == "laptop":
        advice, alternatives = _laptop_benchmark_advice(request, comparisons, spec_map, result)
    else:
        advice, alternatives = _benchmark_advice(request, result)
    if advice:
        result = ScoreResult(
            score=result.score,
            verdict=result.verdict,
            recommendation=f"{result.recommendation} {advice}",
            reference_price=result.reference_price,
            delta_percent=result.delta_percent,
        )
    return result, comparisons, freshness(session, selected_source), alternatives
