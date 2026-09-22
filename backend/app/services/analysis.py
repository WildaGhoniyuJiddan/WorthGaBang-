import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import LaptopUnit, RawListing, ScrapeRun
from ..schemas import AnalyzeRequest, Comparison, Freshness
from .relevance import component_type_from_query, is_relevant_pc_listing
from .benchmark import better_alternatives, get_tier_label, laptop_combo_score, passmark_score
from .scoring import ScoreResult, score_price


def _age_penalty(scraped_at: datetime | None, now: datetime) -> float:
    if not scraped_at:
        return 0.0
    if scraped_at.tzinfo is None:
        scraped_at = scraped_at.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - scraped_at).total_seconds() / 86400.0)
    if days <= 30:
        return 0.0
    elif days <= 60:
        return 0.04
    else:
        return min(0.12, 0.04 + 0.04 * ((days - 60) / 30))


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
    m = re.search(r"\b(rtx|gtx|rx|arc)\s*([ab]?\d{3,4})\s*(ti|super|xt)?\b", text)
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


def _matches_model_tokens(row_tokens: set[str], required_tokens: set[str]) -> bool:
    """Periksa kesesuaian token model. Jika query menyebut kapasitas (misal 4gb),
    listing pembanding wajib mencantumkan kapasitas yang sama persis.
    Jika query tidak menyebut kapasitas, varian kapasitas apa pun diterima."""
    if not required_tokens:
        return True
    req_vram = {t for t in required_tokens if re.match(r"^\d{1,2}gb$", t)}
    if req_vram:
        return row_tokens == required_tokens
    row_core = {t for t in row_tokens if not re.match(r"^\d{1,2}gb$", t)}
    return row_core == required_tokens


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
    m = re.search(r"\b(rtx|gtx)\s*(\d{3,4})\s*(ti|super)?\b", q)
    if m:
        return f"{m.group(1)} {m.group(2)}{(' ' + m.group(3)) if m.group(3) else ''}"
    m = re.search(r"\brx\s*(\d{3,4})\s*(xt)?\b", q)
    if m:
        return f"rx {m.group(1)}{(' xt') if m.group(2) else ''}"
    m = re.search(r"\bryzen\s*([3579])\s*((?:9\d{3}|[357]\d{3}|\d{4}))\b", q)
    if m:
        return f"ryzen {m.group(1)} {m.group(2)}"
    m = re.search(r"\bcore\s*i([3579])\s*-?\s*((?:10|11|12|13|14)\d{3}|\d{4})\b", q)
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
    sources = ("facebook_marketplace", "facebook") if source in ("facebook_marketplace", "facebook") else (source,)
    run = session.scalar(
        select(ScrapeRun).where(ScrapeRun.source.in_(sources)).order_by(desc(ScrapeRun.started_at)).limit(1)
    )
    timestamp = run.finished_at if run and run.status == "success" else None
    if timestamp is None:
        timestamp = session.scalar(select(RawListing.scraped_at).where(RawListing.source.in_(sources)).order_by(desc(RawListing.scraped_at)).limit(1))
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
    """Signature CPU laptop ('Core i5-12450H' -> 'corei512450h', 'i7 13650HX' -> 'corei713650hx')."""
    m = re.search(r"\b(ryzen(?:\s*ai)?\s*[3579]|core\s*i[3579]|ultra\s*[579]|i[3579])\s*-?\s*(\d{4,5}[a-z]{0,3}|[a-z]{1,4}\d{3}[a-z]{0,3})?\b", (text or "").lower())
    if not m:
        return None
    raw_fam = re.sub(r"\s+", "", m.group(1))
    if re.match(r"^i[3579]$", raw_fam):
        raw_fam = "core" + raw_fam
    num = m.group(2) or ""
    if not num:
        return None
    return raw_fam + num


def _cpu_name(text: str) -> str | None:
    """Nama CPU utk PassMark ('core i5 12450h')."""
    sig = _cpu_sig(text)
    if not sig:
        return None
    return re.sub(r"(corei|ryzen|ultra)", lambda mm: {"corei": "core i", "ryzen": "ryzen ", "ultra": "ultra "}[mm.group(1)], sig, count=1)


def _is_external_link_allowed(source: str | None, url: str | None) -> bool:
    """Hanya sediakan link eksternal jika berasal dari marketplace online riil (Tokopedia, FB, dll).

    Data dari katalog retail Enterkomputer, API benchmark, atau referensi internal
    tidak diberi link ke luar.
    """
    if not url:
        return False
    src = (source or "").lower()
    if src in ("komponen_retail", "notebook_retail", "price_reference", "data", "benchmark", "enterkomputer"):
        return False
    if "enterkomputer" in url.lower():
        return False
    return True


def _pc_comparisons(session: Session, request: AnalyzeRequest) -> list[Comparison]:
    ctype = request.component_type or component_type_from_query(request.query)

    retail_cats = {
        "gpu": ("vga",),
        "cpu": ("processor",),
        "motherboard": ("motherboard",),
        "ram": ("ram",),
        "storage": ("ssd", "harddisk"),
    }.get(ctype, ("vga", "processor", "motherboard", "ram", "ssd", "harddisk"))

    # Cari token angka/model utama dari query user (misal '580', '4060', '12400', '5600')
    m_num = re.search(r"\b(\d{3,5})\b", request.query)
    model_num = m_num.group(1) if m_num else None

    # Bangun filter SQL yang efisien melintasi seluruh database
    all_cats = ("pc", "vga", "processor", "motherboard", "ram", "ssd", "harddisk", "laptop")
    all_sources = ("komponen_retail", "tokopedia", "facebook", "facebook_marketplace")

    base_query = select(RawListing).where(
        RawListing.raw_price >= 50_000,
        RawListing.raw_price <= 150_000_000,
        (RawListing.condition != "issue") | (RawListing.condition.is_(None)),
        RawListing.source.in_(all_sources),
        RawListing.category.in_(all_cats),
    )

    if model_num:
        base_query = base_query.where(
            or_(
                RawListing.raw_title.ilike(f"%{model_num}%"),
                RawListing.raw_spec_text.ilike(f"%{model_num}%"),
            )
        )
    elif ctype in ("ram", "storage"):
        canon = _canonical_key(request.query, ctype)
        if canon:
            toks = [t for t in canon.lower().split() if len(t) >= 2]
            for t in toks:
                base_query = base_query.where(RawListing.raw_title.ilike(f"%{t}%"))

    rows = session.scalars(base_query.order_by(desc(RawListing.scraped_at)).limit(3000)).all()

    # Jika pencarian targeted sedikit atau tidak ada token angka, fallback ke limit 1000 per sumber
    if len(rows) < 10 and not model_num:
        fallback_rows = []
        for sources, cats in (
            (("komponen_retail",), retail_cats),
            (("tokopedia",), ("pc",)),
            (("facebook", "facebook_marketplace"), ("pc",)),
        ):
            fallback_rows += session.scalars(
                select(RawListing).where(
                    RawListing.category.in_(cats),
                    RawListing.raw_price >= 50_000,
                    RawListing.raw_price <= 150_000_000,
                    (RawListing.condition != "issue") | (RawListing.condition.is_(None)),
                    RawListing.source.in_(sources),
                ).order_by(desc(RawListing.scraped_at)).limit(1000)
            ).all()
        rows = list({r.id: r for r in (list(rows) + fallback_rows)}.values())

    now = datetime.now(timezone.utc)
    required = _model_tokens(request.query, ctype)

    # Scoring & filtering
    scored_exact = []
    scored_family = []

    for row in rows:
        clean_t = _clean_title(row.raw_title)
        if not _is_relevant_pc_listing(request.query, clean_t, ctype):
            continue
        sim = max(0.05, _similarity(request.query, clean_t) - _age_penalty(row.scraped_at, now))
        row_toks = _model_tokens(clean_t, ctype)

        if _matches_model_tokens(row_toks, required):
            scored_exact.append((sim, row, clean_t))
        elif required and (row_toks - {t for t in row_toks if re.match(r"^\d{1,2}gb$", t)}) == (required - {t for t in required if re.match(r"^\d{1,2}gb$", t)}):
            # Model sekeluarga tapi kapasitas VRAM beda (misal query 4GB dapat 8GB)
            scored_family.append((max(0.05, sim * 0.88), row, clean_t))

    # Filter kemiripan >= 0.75 untuk exact
    matching_exact = [item for item in scored_exact if item[0] >= 0.75]
    matching_family = [item for item in scored_family if item[0] >= 0.65]

    # Pisahkan per kondisi
    wanted_cond = request.condition
    if wanted_cond and wanted_cond != "any":
        exact_cond = [item for item in matching_exact if (item[1].condition or "new") == wanted_cond]
        family_cond = [item for item in matching_family if (item[1].condition or "new") == wanted_cond]
        other_cond = [item for item in matching_exact if (item[1].condition or "new") != wanted_cond]
    else:
        exact_cond = matching_exact
        family_cond = matching_family
        other_cond = []

    # Dedup berdasarkan kesamaan judul dan harga
    def _dedup_items(items):
        seen = set()
        deduped = []
        for sim, r, title in items:
            key = (r.source, title[:60].lower(), r.raw_price)
            if key in seen:
                continue
            seen.add(key)
            deduped.append((sim, r, title))
        return deduped

    exact_cond = _dedup_items(exact_cond)
    family_cond = _dedup_items(family_cond)
    other_cond = _dedup_items(other_cond)

    # Outlier filter pada exact_cond
    def _filter_outliers(items):
        if len(items) < 4:
            return items
        prices = sorted(it[1].raw_price or 0 for it in items)
        q1 = prices[len(prices) // 4]
        q3 = prices[(3 * len(prices)) // 4]
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        inliers = [it for it in items if lo <= (it[1].raw_price or 0) <= hi]
        return inliers or items

    clean_exact = _filter_outliers(exact_cond)
    clean_family = _filter_outliers(family_cond)

    # Kumpulkan pembanding: utamakan exact match
    pool = list(clean_exact)

    # JAMIN MINIMAL 10 PEMBANDING REAL
    # Jika exact match < 10, isi dengan family_cond yang memiliki kondisi yang sama
    if len(pool) < 10 and clean_family:
        needed = 10 - len(pool)
        pool += clean_family[:needed]

    # Hanya isi dengan other_cond jika user TIDAK memilih kondisi spesifik (misal 'any')
    if (not wanted_cond or wanted_cond == "any") and len(pool) < 10 and other_cond:
        needed = 10 - len(pool)
        pool += other_cond[:needed]

    if not pool:
        return []

    # Urutkan berdasarkan kemiripan tertinggi dan kedekatan dengan median
    prices = sorted(item[1].raw_price or 0 for item in pool)
    anchor = prices[len(prices) // 2]
    pool.sort(key=lambda item: (item[0], -abs((item[1].raw_price or 0) - anchor)), reverse=True)

    # Pastikan distribusi sumber seimbang jika ada banyak sumber,
    # namun TIDAK memotong pool hingga di bawah 10 jika data tersedia!
    by_source: dict[str, list] = {}
    for item in pool:
        by_source.setdefault(item[1].source or "lain", []).append(item)

    selected = []
    # Target minimal 10, maksimal 24
    max_target = max(10, min(24, len(pool)))
    quota = max(3, (max_target + len(by_source) - 1) // len(by_source))
    source_pools = [p[:quota] for p in by_source.values()]
    while any(source_pools) and len(selected) < max_target:
        for p in source_pools:
            if p and len(selected) < max_target:
                selected.append(p.pop(0))

    # Jika round-robin menyisakan kuota dan total masih < 10 sedangkan pool punya sisa item:
    if len(selected) < 10 and len(pool) >= 10:
        seen_ids = {it[1].id for it in selected}
        for it in pool:
            if it[1].id not in seen_ids:
                selected.append(it)
                seen_ids.add(it[1].id)
                if len(selected) >= 10:
                    break

    return [
        Comparison(
            title=_clean_title(row.raw_title),
            price=row.raw_price or 0,
            source=row.source,
            listing_url=row.listing_url if _is_external_link_allowed(row.source, row.listing_url) else None,
            similarity=similarity,
            condition=row.condition or "new",
        )
        for similarity, row, _ in selected
    ]


def resolve_bundle_item_prices(session: Session, query: str, component_type: str | None = None) -> tuple[int, int | None, int | None]:
    """Resolusi harga baru & bekas untuk 1 item bundle dari database & katalog retail.

    Return: (reference_price, new_reference_price, used_reference_price)
    """
    ctype = component_type or component_type_from_query(query)

    # 1. Cek anchor harga baru retail (PCPartPicker/Buildcores/Retail catalog)
    anchor = new_price_anchor(query, ctype)

    # 2. Cek pembanding di database (RawListing)
    req = AnalyzeRequest(
        mode="pc",
        query=query,
        price=1,
        component_type=ctype,
        condition="any",
    )
    comps = _pc_comparisons(session, req)
    new_prices = [c.price for c in comps if (c.condition or "new") == "new" and c.price > 0]
    used_prices = [c.price for c in comps if c.condition == "second" and c.price > 0]

    # 3. Fallback pencocokan langsung di database jika comps kosong dan anchor belum ada
    if not new_prices and not anchor:
        tokens = _model_tokens(query, ctype)
        if tokens:
            cats = ("vga", "processor", "motherboard", "ram", "ssd", "harddisk", "pc")
            direct_rows = session.scalars(
                select(RawListing).where(
                    RawListing.category.in_(cats),
                    RawListing.raw_price >= 50_000,
                ).limit(3000)
            ).all()
            for r in direct_rows:
                if r.raw_price and r.raw_price > 0:
                    rt = (r.raw_title or "").lower()
                    if all(t in rt for t in tokens) and is_relevant_pc_listing(query, r.raw_title, ctype):
                        if r.condition == "second":
                            used_prices.append(r.raw_price)
                        else:
                            new_prices.append(r.raw_price)

    new_ref = anchor or (int(sorted(new_prices)[len(new_prices) // 2]) if new_prices else None)
    used_ref = int(sorted(used_prices)[len(used_prices) // 2]) if used_prices else None

    # Jika harga bekas tidak ada di listing, estimasikan rasio depresiasi hardware wajar (70% dari harga baru)
    if used_ref is None and new_ref:
        used_ref = int(new_ref * 0.70)
    elif new_ref is None and used_ref:
        new_ref = int(used_ref / 0.70)

    # Primary reference default ke harga baru jika ada, atau bekas jika hanya ada bekas, atau 0
    ref_primary = new_ref or used_ref or 0
    return ref_primary, new_ref, used_ref


def _cpu_tier(sig: str | None) -> str | None:
    """Tier CPU ('corei712700h' -> '7') utk pencocokan sekelas."""
    if not sig:
        return None
    m = re.search(r"(?:corei|ryzen|ultra|ryzenai|i)([3579])", sig)
    return m.group(1) if m else None


_MD_JUNK_RE = re.compile(r"\[!\[[^\]]*\]\([^)]*\)]?\([^)]*\)|!\[[^\]]*\]\([^)]*\)|\[Image\s*[^\]]*\]", re.IGNORECASE)


def _clean_title(text: str | None) -> str:
    """Buang sampah markdown/gambar dan prefix query dari judul hasil scrape."""
    raw = text or ""
    raw = re.sub(r"^[^\u2014\ufffc]+[\u2014\ufffc]\s*", "", raw).strip() or raw
    cleaned = _MD_JUNK_RE.sub(" ", raw)
    return " ".join(cleaned.split())[:180]


def _extract_storage_from_text(text: str) -> int | None:
    t = (text or "").lower()
    m_tb = re.search(r"(\d)\s*tb\b", t)
    if m_tb:
        return int(m_tb.group(1)) * 1000
    m_slash = re.search(r"\b\d{1,2}\s*/\s*(\d{3,4})\b", t)
    if m_slash:
        return int(m_slash.group(1))
    m_ssd = re.search(r"\b(128|256|512|1000|1024)\s*(?:gb)?\s*(?:ssd|nvme|storage|rom)?\b", t)
    if m_ssd:
        return int(m_ssd.group(1))
    return None


def _extract_ram_from_text(text: str) -> int | None:
    t = (text or "").lower()
    m_ram = re.search(r"\bram\s*(\d{1,2})\s*gb\b", t)
    if m_ram:
        return int(m_ram.group(1))
    m_ddr = re.search(r"(\d{1,2})\s*gb\s*(?:ddr|ram|memory)\b", t)
    if m_ddr:
        return int(m_ddr.group(1))
    m_slash = re.search(r"\b(\d{1,2})\s*/\s*\d{3,4}\b", t)
    if m_slash:
        return int(m_slash.group(1))
    return None


def _laptop_comparisons(session: Session, request: AnalyzeRequest) -> tuple[list[Comparison], dict]:
    want_gpu = _gpu_sig(request.gpu or request.query)
    want_cpu = _cpu_sig(request.cpu)
    if want_cpu is None and not request.gpu:
        want_cpu = _cpu_sig(request.query)

    gpu_num_match = re.search(r"\b(\d{3,4})\b", request.gpu or request.query or "")
    gpu_num = gpu_num_match.group(1) if gpu_num_match else None

    GENERIC_WORDS = {"laptop", "notebook", "gaming", "pro", "plus", "max", "ultra", "inch", "ti", "super", "intel", "amd"}
    query_tokens = [t for t in _tokens(f"{request.brand or ''} {request.query}") if t not in GENERIC_WORDS and len(t) >= 3]

    conds = []
    if gpu_num:
        conds.append(LaptopUnit.gpu.ilike(f"%{gpu_num}%"))
        conds.append(LaptopUnit.model.ilike(f"%{gpu_num}%"))
    for t in query_tokens:
        conds.append(LaptopUnit.model.ilike(f"%{t}%"))
        conds.append(LaptopUnit.brand.ilike(f"%{t}%"))

    rows: list[LaptopUnit] = []
    if conds:
        stmt = select(LaptopUnit).where(
            LaptopUnit.price >= 500_000,
            LaptopUnit.price <= 150_000_000,
            (LaptopUnit.condition != "issue") | (LaptopUnit.condition.is_(None)),
            or_(*conds),
        ).order_by(desc(LaptopUnit.scraped_at)).limit(1500)
        rows = list(session.scalars(stmt).all())

    if len(rows) < 30:
        seen_ids = {r.id for r in rows}
        for src in ("notebook_retail", "tokopedia"):
            extra = session.scalars(
                select(LaptopUnit).where(
                    LaptopUnit.price >= 500_000,
                    LaptopUnit.price <= 150_000_000,
                    (LaptopUnit.condition != "issue") | (LaptopUnit.condition.is_(None)),
                    LaptopUnit.source == src,
                ).order_by(desc(LaptopUnit.scraped_at)).limit(800)
            ).all()
            for r in extra:
                if r.id not in seen_ids:
                    rows.append(r)
                    seen_ids.add(r.id)

    min_ram = request.ram_gb or None
    min_storage = request.storage_gb or None
    scored_new: list[tuple[float, LaptopUnit]] = []
    scored_used: list[tuple[float, LaptopUnit]] = []
    now = datetime.now(timezone.utc)
    wanted = _tokens(" ".join(filter(None, [request.brand or "", request.query])))
    brand_prefix = (request.query.lower().split()[0] if request.query else (request.brand or "").lower())

    for row in rows:
        title = f"{row.brand or ''} {row.model or ''} {row.cpu or ''} {row.gpu or ''}"
        if not _is_relevant_pc_listing(request.query, title, "laptop"):
            continue
        got_gpu = _gpu_sig(title)
        got_cpu = _cpu_sig(title)

        # GPU = identitas performa utama laptop gaming.
        if want_gpu and got_gpu != want_gpu:
            continue

        cpu_penalty = 0.0
        if want_cpu:
            got_tier = _cpu_tier(got_cpu) if got_cpu else None
            want_tier = _cpu_tier(want_cpu)
            if got_cpu == want_cpu:
                pass
            elif got_tier is not None and got_tier == want_tier:
                cpu_penalty = 0.10
            elif got_tier is not None and want_tier is not None and got_tier > want_tier:
                cpu_penalty = 0.15
            elif got_cpu is None:
                cpu_penalty = 0.20
            else:
                continue  # kelas di bawah yang diminta

        effective_ram = row.ram_gb or _extract_ram_from_text(title)
        effective_storage = row.storage_gb or _extract_storage_from_text(title)
        spec_penalty = 0.0
        if min_ram:
            if effective_ram is not None and effective_ram < min_ram:
                if effective_ram <= min_ram // 2:
                    continue
                spec_penalty += 0.10
            elif effective_ram is None:
                spec_penalty += 0.05

        if min_storage:
            if effective_storage is not None and effective_storage < min_storage:
                if effective_storage <= min_storage // 2:
                    continue
                spec_penalty += 0.10
            elif effective_storage is None:
                spec_penalty += 0.05

        actual = _tokens(f"{row.brand or ''} {row.model or ''}")
        if wanted:
            overlap = len(wanted & actual)
            overlap_sim = round(overlap / len(wanted), 3)
            # Baseline kemiripan: jika GPU sama persis, baseline minimal 0.50
            base = 0.50 if (want_gpu and got_gpu == want_gpu) else 0.30
            raw_sim = max(base, overlap_sim)
            if brand_prefix and brand_prefix in actual:
                raw_sim = min(1.0, raw_sim + 0.15)
            for qt in query_tokens:
                if qt in actual:
                    raw_sim = min(1.0, raw_sim + 0.20)
                    break
        else:
            raw_sim = 0.5

        similarity = max(0.05, raw_sim - cpu_penalty - spec_penalty - _age_penalty(row.scraped_at, now))
        if row.condition == "second":
            scored_used.append((similarity, row))
        else:
            scored_new.append((similarity, row))

    if not scored_new and not scored_used:
        return [], {}

    def _process_laptop_pool(candidates: list[tuple[float, LaptopUnit]], limit_count: int) -> list[tuple[float, LaptopUnit]]:
        if not candidates:
            return []
        candidates.sort(key=lambda item: (item[0], item[1].scraped_at), reverse=True)
        high_sim = [item for item in candidates if item[0] >= 0.4]
        pool = high_sim if len(high_sim) >= 3 else candidates
        top_candidates = pool[:50]
        prices = sorted(item[1].price or 0 for item in top_candidates if item[1].price)
        if len(prices) >= 4:
            q1 = prices[len(prices) // 4]
            q3 = prices[(3 * len(prices)) // 4]
            iqr = q3 - q1
            lo, hi = max(500_000, q1 - 1.5 * iqr), q3 + 1.5 * iqr
            inliers = [item for item in top_candidates if lo <= (item[1].price or 0) <= hi]
            top_candidates = inliers or top_candidates

        by_source: dict[str, list] = {}
        seen_titles: set[str] = set()
        for item in top_candidates:
            key = item[1].source or "lain"
            title_key = _clean_title(item[1].model or item[1].brand or "Laptop").lower()[:80]
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            by_source.setdefault(key, []).append(item)

        total_items = sum(len(v) for v in by_source.values())
        if total_items < limit_count:
            for item in candidates:
                key = item[1].source or "lain"
                title_key = _clean_title(item[1].model or item[1].brand or "Laptop").lower()[:80]
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    by_source.setdefault(key, []).append(item)
                    if sum(len(v) for v in by_source.values()) >= limit_count:
                        break

        quota = max(2, (limit_count + len(by_source) - 1) // len(by_source))
        pools = [p[:quota] for p in by_source.values()]
        selected_items = []
        while any(pools) and len(selected_items) < limit_count:
            for p in pools:
                if p and len(selected_items) < limit_count:
                    selected_items.append(p.pop(0))
        return selected_items

    if request.condition == "new":
        sel_new = _process_laptop_pool(scored_new, 16)
        sel_used = _process_laptop_pool(scored_used, 8)
        selected = sel_new + sel_used if sel_new else _process_laptop_pool(scored_used + scored_new, 24)
    elif request.condition == "second":
        sel_used = _process_laptop_pool(scored_used, 16)
        sel_new = _process_laptop_pool(scored_new, 8)
        selected = sel_used + sel_new if sel_used else _process_laptop_pool(scored_new + scored_used, 24)
    else:
        sel_new = _process_laptop_pool(scored_new, 12)
        sel_used = _process_laptop_pool(scored_used, 12)
        selected = sel_new + sel_used if (sel_new or sel_used) else _process_laptop_pool(scored_new + scored_used, 24)

    return [
        Comparison(
            title=_clean_title(row.model or row.brand or "Laptop"),
            price=row.price,
            source=row.source,
            listing_url=row.listing_url if _is_external_link_allowed(row.source, row.listing_url) else None,
            similarity=similarity,
            condition=row.condition or "new",
        )
        for similarity, row in selected
    ], {
        _clean_title(row.model or row.brand or "Laptop"): {"cpu": row.cpu, "gpu": row.gpu}
        for _, row in selected
    }


def _generate_cross_market_advice(
    condition: str | None,
    price: int,
    new_ref: int | None,
    used_ref: int | None,
    query: str,
    mode: str,
) -> str | None:
    price_fmt = f"Rp{price:,}".replace(",", ".")
    new_fmt = f"Rp{new_ref:,}".replace(",", ".") if new_ref else None
    used_fmt = f"Rp{used_ref:,}".replace(",", ".") if used_ref else None

    if condition == "new":
        if new_ref and used_ref:
            pct_savings = round(((new_ref - used_ref) / new_ref) * 100)
            return (
                f"🏷️ Di pasar baru, median referensi adalah {new_fmt}. "
                f"📦 Sebagai opsi alternatif, unit sekelas di pasar bekas beredar sekitar {used_fmt} (hemat ~{pct_savings}%). "
                f"Dengan budget {price_fmt}, di pasar bekas Anda juga berpotensi mendapatkan unit ber-tier performa lebih tinggi."
            )
        elif new_ref:
            return f"🏷️ Di pasar baru, harga referensi retail terpantau di kisaran {new_fmt}."
        elif used_ref:
            return f"📦 Data retail baru terbatas. Sebagai perbandingan, di pasar bekas beredar sekitar {used_fmt}."

    elif condition == "second":
        if used_ref and new_ref:
            if price < new_ref:
                pct_savings = round(((new_ref - price) / new_ref) * 100)
                return (
                    f"📦 Di pasar bekas, harga referensi sekelas adalah {used_fmt}. "
                    f"🏷️ Dibandingkan harga retail baru ({new_fmt}), tawaran bekas seharga {price_fmt} menghemat sekitar {pct_savings}%. "
                    f"Pastikan cek kesehatan fisik, suhu termal, dan fungsi komponen sebelum bertransaksi."
                )
            else:
                return (
                    f"📦 Di pasar bekas, harga referensi sekelas adalah {used_fmt}. "
                    f"⚠️ Perhatian: tawaran bekas {price_fmt} mendekati atau melebihi harga unit baru ({new_fmt}). "
                    f"Sangat disarankan membeli unit baru retail untuk jaminan garansi resmi."
                )
        elif used_ref:
            return f"📦 Di pasar bekas, unit/komponen sekelas terpantau di kisaran {used_fmt}."
        elif new_ref:
            return f"🏷️ Data pasar bekas terbatas. Sebagai perbandingan, unit baru di retail dibanderol sekitar {new_fmt}."

    else:
        if new_ref and used_ref:
            pct_savings = round(((new_ref - used_ref) / new_ref) * 100)
            return (
                f"🏷️ Pasar Baru: referensi {new_fmt} | 📦 Pasar Bekas: referensi {used_fmt} (selisih ~{pct_savings}%). "
                f"Sesuaikan pilihan dengan prioritas garansi resmi vs efisiensi budget."
            )
    return None


def _laptop_benchmark_advice(request: AnalyzeRequest, comparisons, spec_map: dict, result) -> tuple[str, list[dict]]:
    """Advice PassMark utk laptop: combo GPU+CPU unit user vs pembanding sungguhan.

    Alternatif hanya dari unit nyata di database (bukan katalog global) supaya
    harga & ketersediaannya real. Return (recommendation_tambahan, alternatives).
    """
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
    est_price_str = f"{best['est_price_idr']:,}".replace(",", ".")
    score_str = f"{best['score']:,}".replace(",", ".")
    user_score_str = f"{user_combo['score']:,}".replace(",", ".")
    if result.verdict in ("worth it", "wajar"):
        advice = (
            f"Ada alternatif unit dengan performa lebih tinggi di kisaran harga serupa: {best['name']} "
            f"(performa +{best['gain_percent']}%, dijual Rp{est_price_str}, skor combo {score_str} vs {user_score_str})."
        )
    else:
        advice = (
            f"Di harga segitu lebih baik {best['name']}: performa +{best['gain_percent']}% "
            f"(dijual Rp{est_price_str}, skor combo {score_str} vs {user_score_str})."
        )
    return advice, alts


def _benchmark_advice(request: AnalyzeRequest, result) -> tuple[str, list[dict]]:
    """Advice PassMark: "di harga segitu lebih baik X (+N%)" atau info alternatif performa.

    Return (recommendation_tambahan, alternatives). Kosong kalau model gak
    ketemu di katalog benchmark atau tidak ada kandidat yang layak.
    """
    ctype = request.component_type or component_type_from_query(request.query)
    alts = better_alternatives(request.query, ctype, request.price, USD_TO_IDR)
    if not alts:
        return "", []
    best = alts[0]
    est_price_str = f"{best['est_price_idr']:,}".replace(",", ".")
    score_str = f"{best['score']:,}".replace(",", ".")
    if result.verdict in ("worth it", "wajar"):
        advice = (
            f"Ada alternatif dengan performa lebih tinggi di kisaran harga serupa: {best['name']} "
            f"(performa +{best['gain_percent']}%, est. Rp{est_price_str}, skor PassMark {score_str})."
        )
    else:
        advice = (
            f"Di harga segitu lebih baik {best['name']}: performa +{best['gain_percent']}% "
            f"(est. Rp{est_price_str}) dengan skor PassMark {score_str}."
        )
    return advice, alts


def analyze(session: Session, request: AnalyzeRequest):
    tier_label = None
    if request.mode == "pc":
        comparisons = _pc_comparisons(session, request)
        spec_map = {}
        ctype = request.component_type or component_type_from_query(request.query)
        base = passmark_score(request.query, ctype)
        if base and base.get("score"):
            tier_label = get_tier_label(base["score"], ctype)
    else:
        comparisons, spec_map = _laptop_comparisons(session, request)
        user_combo = laptop_combo_score(
            request.cpu or request.query,
            request.gpu or request.query,
        )
        if user_combo:
            tier_label = user_combo.get("tier_label")

    # Dual-market reference calculation
    new_comps = [c for c in comparisons if (c.condition or "new") == "new"]
    used_comps = [c for c in comparisons if c.condition == "second"]

    new_prices = [c.price for c in new_comps if c.price]
    used_prices = [c.price for c in used_comps if c.price]

    new_ref = int(sorted(new_prices)[len(new_prices) // 2]) if new_prices else None
    used_ref = int(sorted(used_prices)[len(used_prices) // 2]) if used_prices else None

    # Tentukan harga pembanding primer berdasarkan preferensi kondisi user
    if request.condition == "new" and len(new_prices) >= 2:
        primary_prices = new_prices
    elif request.condition == "second" and len(used_prices) >= 2:
        primary_prices = used_prices
    else:
        primary_prices = [c.price for c in comparisons if c.price]

    result = score_price(request.price, primary_prices)

    # fallback anchor harga BARU dari katalog referensi (buildcores+PCPartPicker)
    # kalau listing second yang relevan gak cukup untuk kasih verdict.
    if (result.verdict == "data terbatas" or not comparisons) and request.condition != "second":
        ref_new = new_price_anchor(request.query, request.component_type)
        if ref_new:
            result = score_price(request.price, [ref_new], is_new_reference=True)
            new_ref = new_ref or ref_new
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

    # Generate cross-market intelligence advice
    cross_advice = _generate_cross_market_advice(
        condition=request.condition,
        price=request.price,
        new_ref=new_ref,
        used_ref=used_ref,
        query=request.query,
        mode=request.mode,
    )

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

    full_rec = result.recommendation
    if advice:
        full_rec = f"{full_rec} {advice}"

    result = ScoreResult(
        score=result.score,
        verdict=result.verdict,
        recommendation=full_rec,
        reference_price=result.reference_price,
        delta_percent=result.delta_percent,
        fair_price_low=result.fair_price_low,
        fair_price_high=result.fair_price_high,
        tier_label=tier_label,
        new_reference_price=new_ref,
        used_reference_price=used_ref,
        cross_market_advice=cross_advice,
    )

    return result, comparisons, freshness(session, selected_source), alternatives
