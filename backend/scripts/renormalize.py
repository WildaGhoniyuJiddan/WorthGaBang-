"""Re-normalize ulang semua raw listing ke pc_components/laptop_units dengan
aturan canonical model terbaru. Aman dijalankan berulang (upsert per raw)."""
import sys
from pathlib import Path

sys.path.insert(0, ".")

from sqlalchemy import text as sa_text

from app.db import SessionLocal
from app.models import PCComponent
from app.services.normalizer import normalize_pending


def main() -> None:
    db = SessionLocal()
    deleted = db.query(PCComponent).delete()
    db.commit()
    print(f"pc_components lama dibersihkan: {deleted}")
    count = normalize_pending(db)
    print(f"re-normalize selesai: {count} raw listings diproses")
    # sisakan 1 row per (component_type, model): avg_price identik antar-brand,
    # analyze tidak memakai brand dari tabel katalog
    dupes = db.execute(sa_text(
        "select id from pc_components where id not in "
        "(select min(id) from pc_components group by component_type, model)"
    )).fetchall()
    ids = [row[0] for row in dupes]
    if ids:
        db.query(PCComponent).filter(PCComponent.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    print(f"duplicate per-model dibuang: {len(ids)}")
    total = db.query(PCComponent).count()
    print("pc_components sekarang:", total)
    db.close()


if __name__ == "__main__":
    main()
