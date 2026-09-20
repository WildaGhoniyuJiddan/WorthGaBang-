from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .models import ScrapeRun
from .scrapers import FacebookMarketplaceScraper, Scraper, ShopeeScraper, TokopediaScraper
from .services.ingestion import (
    IngestStats,
    ListingInput,
    ingest_listings,
    listing_input_from_record,
)


def scraper_for(source: str) -> Scraper:
    settings = get_settings()
    timeout = settings.scrape_timeout_seconds
    if source == "tokopedia":
        return TokopediaScraper(
            timeout=timeout,
            pages=settings.tokopedia_pages,
            max_variants=settings.tokopedia_query_variants,
            max_records=settings.tokopedia_max_records,
            request_delay=settings.tokopedia_request_delay_seconds,
        )
    if source == "shopee":
        return ShopeeScraper(cookie=settings.shopee_cookie, timeout=timeout)
    if source == "facebook_marketplace":
        return FacebookMarketplaceScraper(cookie=settings.facebook_cookie, timeout=timeout)
    if source == "komponen_retail":
        from .scrapers.komponen_retail import KomponenRetailScraper

        return KomponenRetailScraper(timeout=timeout)
    if source == "notebook_retail":
        from .scrapers.notebook_retail import NotebookRetailScraper

        return NotebookRetailScraper(timeout=timeout)
    raise ValueError(f"Sumber scraper tidak dikenal: {source}")


def run_source(
    source: str,
    query: str,
    schedule: str = "manual",
    is_fallback: bool = False,
    scraper: Scraper | None = None,
) -> ScrapeRun:
    db: Session = SessionLocal()
    run = ScrapeRun(source=source, schedule=schedule, status="running", is_fallback=is_fallback)
    db.add(run)
    db.commit()
    try:
        records = (scraper or scraper_for(source)).fetch(query)
        stats = IngestStats()
        inserted = ingest_listings(
            db,
            source,
            [listing_input_from_record(record) for record in records],
            stats=stats,
        )
        run.status = "success"
        run.item_count = inserted
        # Catat berapa listing ex-mining yang dibuang supaya bisa diaudit.
        if stats.skipped_ex_mining:
            run.error_message = f"dibuang ex-mining: {stats.skipped_ex_mining}"
    except Exception as exc:
        db.rollback()
        run = db.merge(run)
        run.status = "failed"
        run.error_message = str(exc)[:2000]
    finally:
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.close()
    return run


def run_cycle(query: str | None = None) -> dict:
    query = query or get_settings().query_list[0]
    result = {"query": query, "runs": [], "fallback_source": None}
    for source in ("tokopedia", "shopee"):
        result["runs"].append(run_source(source, query, schedule="manual"))

    facebook_run = run_source("facebook_marketplace", query, schedule="manual")
    result["runs"].append(facebook_run)
    if facebook_run.status != "success":
        tokopedia_run = result["runs"][0]
        if tokopedia_run.status == "success":
            result["fallback_source"] = "tokopedia"
            with SessionLocal() as db:
                persisted = db.get(ScrapeRun, tokopedia_run.id)
                if persisted:
                    persisted.is_fallback = True
                    db.commit()
    return result


def run_all_queries() -> list[dict]:
    return [run_cycle(query) for query in get_settings().query_list]


def run_weekly_queries() -> list[ScrapeRun]:
    runs = []
    for query in get_settings().query_list:
        for source in ("tokopedia", "shopee"):
            runs.append(run_source(source, query, schedule="weekly"))
    return runs


def run_daily_facebook() -> list[ScrapeRun]:
    return [run_source("facebook_marketplace", query, schedule="daily") for query in get_settings().query_list]


# ponytail: harga retail bergerak lambat — cukup refresh sebulan sekali tiap tanggal 1.
def run_monthly_komponen_retail() -> list[ScrapeRun]:
    runs = [run_source("komponen_retail", query, schedule="monthly") for query in get_settings().query_list]
    _regenerate_retail_catalog()
    _regenerate_benchmark_catalog()
    return runs


def _regenerate_retail_catalog() -> None:
    """Regenerate app/data/retail_catalog.json (pool saran kondisi BARU)."""
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "generate_retail_catalog.py"
    try:
        subprocess.run([sys.executable, str(script)], check=True, timeout=600)
    except Exception as exc:  # jangan bunuh scheduler; cukup catat
        print(f"[monthly] regenerate retail_catalog gagal: {exc}")


def _regenerate_benchmark_catalog() -> None:
    """Regenerate app/data/benchmark_scores.json (skor PassMark)."""
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "generate_benchmark_catalog.py"
    try:
        subprocess.run([sys.executable, str(script)], check=True, timeout=600)
    except Exception as exc:  # jangan bunuh scheduler; cukup catat
        print(f"[monthly] regenerate benchmark_scores gagal: {exc}")


# ---------------------------------------------------------------------------
# Dua pipeline pengumpulan harga BARU, proses terpisah (bisa jalan paralel):
#   run_pipeline_pc     -> katalog komponen retail penuh + marketplace GPU/CPU
#   run_pipeline_laptop -> katalog notebook retail + marketplace seri laptop
# ---------------------------------------------------------------------------

def _query_list(section: str) -> list[str]:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "app" / "data" / "query_list.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get(section) or []


def _ingest_records(source: str, query: str, records: list) -> int:
    """Ingest langsung tanpa ScrapeRun (dipakai sweep katalog penuh)."""
    db: Session = SessionLocal()
    try:
        inserted = ingest_listings(
            db,
            source,
            [listing_input_from_record(r) for r in records],
        )
        return inserted
    finally:
        db.close()


def run_pipeline_pc(progress=print) -> dict:
    """PROSES 1 — komponen PC baru:
    1. Sweep katalog retail penuh per kategori (ribuan item, bukan cuma query).
    2. Tokopedia utk tiap query GPU/CPU (varian pasar).
    """
    result = {"pipeline": "pc", "catalog": {}, "marketplace": []}

    # 1a. Katalog retail penuh: satu request per kategori = SEMUA produknya.
    for category in ("vga", "processor", "motherboard", "ram", "ssd", "harddisk"):
        try:
            scraper = scraper_for("komponen_retail")
            records = scraper._post("simulation", {"RSTGE": category, "MSTGE": category}).get("result") or []
            rows = []
            for item in records:
                prices = item.get("PPRCZ") or []
                price = prices[0] if prices else None
                name = (item.get("PNAME") or "").strip()
                if name and isinstance(price, int) and price >= 10_000:
                    rows.append(ListingInput(
                        title=name[:500], price=price,
                        url=f"https://www.enterkomputer.com/?p={item.get('PCODE')}",
                        spec_text=item.get("PDTLS") or None,
                        category=item.get("KNAME") or category, condition="new",
                    ))
            inserted = _ingest_records("komponen_retail", category, rows)
            result["catalog"][category] = {"fetched": len(rows), "inserted": inserted}
            progress(f"[pc] {category}: {len(rows)} item, {inserted} baru")
        except Exception as exc:
            result["catalog"][category] = {"error": str(exc)[:300]}
            progress(f"[pc] {category} GAGAL: {exc}")

    # 1b. Marketplace utk query GPU/CPU kanonik.
    for query in [*_query_list("gpu"), *_query_list("cpu")]:
        run = run_source("tokopedia", query, schedule="pipeline_pc")
        result["marketplace"].append({"query": query, "status": run.status, "items": run.item_count})
        progress(f"[pc] tokopedia '{query}': {run.status} ({run.item_count})")
    return result


def run_pipeline_laptop(progress=print) -> dict:
    """PROSES 2 — laptop baru:
    1. Katalog notebook retail penuh (800+ unit).
    2. Tokopedia utk tiap seri laptop populer.
    """
    result = {"pipeline": "laptop", "catalog": {}, "marketplace": []}

    # 2a. Katalog notebook retail penuh.
    try:
        scraper = scraper_for("notebook_retail")
        records = scraper.fetch("notebook")
        inserted = _ingest_records("notebook_retail", "notebook", [
            ListingInput(
                title=r.title, price=r.price, url=r.url,
                spec_text=r.spec_text, category=r.category, condition=r.condition,
            )
            for r in records
        ])
        result["catalog"]["notebook"] = {"fetched": len(records), "inserted": inserted}
        progress(f"[laptop] notebook: {len(records)} unit, {inserted} baru")
    except Exception as exc:
        result["catalog"]["notebook"] = {"error": str(exc)[:300]}
        progress(f"[laptop] notebook GAGAL: {exc}")

    # 2b. Marketplace utk tiap seri laptop.
    for query in _query_list("laptop"):
        run = run_source("tokopedia", query, schedule="pipeline_laptop")
        result["marketplace"].append({"query": query, "status": run.status, "items": run.item_count})
        progress(f"[laptop] tokopedia '{query}': {run.status} ({run.item_count})")
    return result
