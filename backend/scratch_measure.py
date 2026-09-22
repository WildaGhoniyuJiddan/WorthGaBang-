import os
import dotenv

dotenv.load_dotenv(".env")
url = os.environ["DATABASE_URL"]
import sqlalchemy as sa

e = sa.create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 20})
q = lambda sql: e.connect().execute(sa.text(sql)).fetchall()

with e.connect() as c:
    print("== ukuran baris penuh (semua kolom incl. description/spec) ==")
    for src, cat, lim in [
        ("komponen_retail", "vga|processor|motherboard|ram|ssd|harddisk", 6000),
        ("tokopedia", "pc", 6000),
        ("facebook|facebook_marketplace", "pc", 6000),
    ]:
        r = c.execute(sa.text(f"""
            SELECT count(*) n, (sum(octet_length(t.*::text))/1048576)::numeric(10,2) mb
            FROM (SELECT * FROM raw_listings
                  WHERE source = ANY(STRING_TO_ARRAY('{src}','|'))
                    AND category = ANY(STRING_TO_ARRAY('{cat}','|'))
                    AND raw_price >= 50000
                  ORDER BY scraped_at DESC LIMIT {lim}) t
        """)).fetchone()
        print(f"  _pc_comparisons src={src}: {r.n} rows = {r.mb} MB (full entity)")

    r = c.execute(sa.text("""
        SELECT count(*) n, (sum(octet_length(t.*::text))/1048576)::numeric(10,2) mb
        FROM (SELECT * FROM laptop_units ORDER BY scraped_at DESC LIMIT 4000) t
    """)).fetchone()
    print(f"  _laptop_comparisons main: {r.n} rows = {r.mb} MB")

    r = c.execute(sa.text("""
        SELECT count(*) n, (sum(octet_length(t.*::text))/1048576)::numeric(10,2) mb
        FROM (SELECT raw_title, raw_price FROM raw_listings WHERE category='pc' AND raw_price>50000
              ORDER BY scraped_at DESC LIMIT 4000) t
    """)).fetchone()
    print(f"  suggest _market_prices: {r.n} rows = {r.mb} MB (2 kolom)")

    r = c.execute(sa.text("""
        SELECT count(*) n, (sum(octet_length(t.*::text))/1048576)::numeric(10,2) mb
        FROM (SELECT raw_title, raw_price FROM raw_listings
              ORDER BY scraped_at DESC LIMIT 2000) t
    """)).fetchone()
    print(f"  suggest listing pool 2000: {r.n} rows = {r.mb} MB")

    print("== jumlah request tercatat ==")
    for row in c.execute(sa.text("""
        SELECT date_trunc('day', created_at)::date d, count(*)
        FROM analysis_logs GROUP BY 1 ORDER BY 1 DESC LIMIT 14
    """)).fetchall():
        print("  analyze", row)
    for row in c.execute(sa.text("""
        SELECT date_trunc('day', started_at)::date d, count(*), sum(item_count)
        FROM scrape_runs GROUP BY 1 ORDER BY 1 DESC LIMIT 14
    """)).fetchall():
        print("  scrape", row)
    print("== kolom teks besar di raw_listings ==")
    for row in c.execute(sa.text("""
        SELECT (sum(octet_length(description))/1048576)::numeric(10,1) desc_mb,
               (sum(octet_length(coalesce(raw_spec_text,'')))/1048576)::numeric(10,1) spec_mb,
               (sum(octet_length(raw_title))/1048576)::numeric(10,1) title_mb,
               (sum(octet_length(coalesce(listing_url,'')))/1048576)::numeric(10,1) url_mb
        FROM raw_listings
    """)).fetchall():
        print(" ", row)
