from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .models import ScrapeRun
from .scrapers import FacebookMarketplaceScraper, Scraper, ShopeeScraper, TokopediaScraper
from .services.ingestion import ListingInput, ingest_listings


def scraper_for(source: str) -> Scraper:
    settings = get_settings()
    timeout = settings.scrape_timeout_seconds
    if source == "tokopedia":
        return TokopediaScraper(timeout=timeout)
    if source == "shopee":
        return ShopeeScraper(cookie=settings.shopee_cookie, timeout=timeout)
    if source == "facebook":
        return FacebookMarketplaceScraper(cookie=settings.facebook_cookie, timeout=timeout)
    raise ValueError(f"Sumber scraper tidak dikenal: {source}")


def run_source(source: str, query: str, schedule: str = "manual", is_fallback: bool = False) -> ScrapeRun:
    db: Session = SessionLocal()
    run = ScrapeRun(source=source, schedule=schedule, status="running", is_fallback=is_fallback)
    db.add(run)
    db.commit()
    try:
        records = scraper_for(source).fetch(query)
        inserted = ingest_listings(
            db,
            source,
            [
                ListingInput(
                    title=record.title,
                    price=record.price,
                    url=record.url,
                    spec_text=record.spec_text,
                    category=record.category,
                    condition=record.condition,
                )
                for record in records
            ],
        )
        run.status = "success"
        run.item_count = inserted
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

    facebook_run = run_source("facebook", query, schedule="manual")
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
    return [run_source("facebook", query, schedule="daily") for query in get_settings().query_list]
