"""Sweep katalog retail (enterkomputer) — komponen PC + notebook.
Bagian 1a/2a dari run_pipeline_pc/laptop, tanpa bagian Tokopedia
(Tokopedia-nya lagi jalan di batch terpisah).
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import get_settings  # noqa: E402
from app.jobs import _ingest_records, scraper_for  # noqa: E402
from app.services.ingestion import ListingInput  # noqa: E402


def sweep_komponen():
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
            print(f"[komponen] {category}: fetched={len(rows)} baru={inserted}", flush=True)
        except Exception as exc:
            print(f"[komponen] {category} GAGAL: {str(exc)[:300]}", flush=True)


def sweep_notebook():
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
        print(f"[notebook] fetched={len(records)} baru={inserted}", flush=True)
    except Exception as exc:
        print(f"[notebook] GAGAL: {str(exc)[:300]}", flush=True)


if __name__ == "__main__":
    get_settings()
    sweep_komponen()
    sweep_notebook()
    print("SWEEP RETAIL SELESAI", flush=True)
