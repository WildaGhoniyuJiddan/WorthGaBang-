"""Sweep manual semua query di SCRAPE_QUERIES ke 3 sumber, lalu ringkas hasil."""
import sys
import time

sys.path.insert(0, ".")  # ponytail: dijalankan dari backend/, biar `app` ketemu

from app.config import get_settings
from app.jobs import run_all_queries


def main() -> None:
    settings = get_settings()
    print(f"Query list ({len(settings.query_list)}): {settings.query_list}", flush=True)
    start = time.time()
    results = run_all_queries()
    ok = fail = inserted = 0
    for cycle in results:
        for run in cycle["runs"]:
            status = run.status
            if status == "success":
                ok += 1
                inserted += run.item_count or 0
            else:
                fail += 1
            print(
                f"[{cycle['query']:<18}] {run.source:<9} {status:<7} "
                f"items={run.item_count} err={(run.error_message or '')[:60]}",
                flush=True,
            )
    print(f"\nSELESAI {time.time()-start:.0f}s: {ok} run sukses, {fail} gagal, {inserted} listing baru", flush=True)


if __name__ == "__main__":
    main()
