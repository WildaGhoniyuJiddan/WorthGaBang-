"""Refresh Tokopedia catalog with controlled query expansion and pagination.

Examples:
    python scripts/refresh_tokopedia.py --scope pc --pages 2 --variants 3
    python scripts/refresh_tokopedia.py --query "RTX 3060" --pages 3 --variants 5
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.jobs import run_source
from app.scrapers.tokopedia import TokopediaScraper
from app.services.relevance import is_standalone_component_query


def select_queries(scope: str, exact_query: str | None, limit: int | None) -> list[str]:
    if exact_query:
        return [exact_query]
    settings = get_settings()
    if scope == "pc":
        queries = [query for query in settings.query_list if is_standalone_component_query(query)]
    else:
        queries = settings.query_list
    return queries[:limit] if limit else queries


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh HargaPas Tokopedia catalog")
    parser.add_argument("--scope", choices=("pc", "all"), default="pc")
    parser.add_argument("--query", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--pages", type=int, default=None)
    parser.add_argument("--variants", type=int, default=None)
    parser.add_argument("--delay", type=float, default=None)
    args = parser.parse_args()

    settings = get_settings()
    queries = select_queries(args.scope, args.query, args.limit)
    scraper = TokopediaScraper(
        timeout=settings.scrape_timeout_seconds,
        pages=args.pages or settings.tokopedia_pages,
        max_variants=args.variants or settings.tokopedia_query_variants,
        max_records=settings.tokopedia_max_records,
        request_delay=args.delay if args.delay is not None else settings.tokopedia_request_delay_seconds,
    )
    summary = {"queries": len(queries), "success": 0, "failed": 0, "inserted": 0, "runs": []}
    started = time.time()
    for index, query in enumerate(queries, start=1):
        run = run_source("tokopedia", query, schedule="manual", scraper=scraper)
        if run.status == "success":
            summary["success"] += 1
            summary["inserted"] += run.item_count or 0
        else:
            summary["failed"] += 1
        summary["runs"].append({"query": query, "status": run.status, "items": run.item_count, "error": run.error_message})
        print(f"[{index}/{len(queries)}] {query:<18} {run.status:<7} inserted={run.item_count or 0} error={(run.error_message or '')[:80]}", flush=True)
    summary["elapsed_seconds"] = round(time.time() - started, 1)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
