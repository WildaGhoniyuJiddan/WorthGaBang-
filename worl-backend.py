"""
WorL backend v3 — auto-save CSV tiap kali ada data masuk.
Folder output: D:/Projek/WorL/worl-extension/hasil/ (satu CSV per sesi/mode).
Endpoint tetap:
  POST /collect
  GET  /products
  GET  /export.csv (opsional, masih jalan)
"""
import csv
import io
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

DB = "worl_scraped.db"
HASIL_DIR = r"D:\Projek\WorL\worl-extension\hasil"

COLUMNS = [
    "id", "site", "keyword", "name", "price_rp", "price_text",
    "author", "time_text", "comments", "shares",
    "description", "url", "page_url", "type", "scraped_at",
]


def init_db():
    con = sqlite3.connect(DB)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site TEXT, keyword TEXT, name TEXT,
            price_rp INTEGER, price_text TEXT,
            author TEXT, time_text TEXT, comments TEXT, shares TEXT,
            description TEXT,
            url TEXT, page_url TEXT,
            type TEXT DEFAULT 'product',
            is_question INTEGER,
            group_name TEXT,
            scraped_at TEXT
        )
        """
    )
    cols = [r[1] for r in con.execute("PRAGMA table_info(products)")]
    for col in ("author", "time_text", "comments", "shares", "description", "type", "is_question", "group_name"):
        if col not in cols:
            con.execute(f"ALTER TABLE products ADD COLUMN {col} {'INTEGER' if col == 'is_question' else 'TEXT'}")
    con.commit()
    con.close()


def parse_price_rp(text):
    m = re.search(r"Rp\s?([\d.,]+)", text or "")
    if not m:
        return None
    digits = re.sub(r"[.,]", "", m.group(1))
    return int(digits) if digits.isdigit() else None


def safe_name(s):
    return re.sub(r"[^a-zA-Z0-9-_]", "_", s or "")[:40] or "all"


def append_csv(site, keyword, items):
    """Tambah baris ke CSV sesi hari ini di folder hasil. Return path."""
    import os

    os.makedirs(HASIL_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    fname = f"{safe_name(site)}_{today}.csv"
    path = f"{HASIL_DIR}\\{fname}"

    existing_urls = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            existing_urls = {row.get("url") for row in csv.DictReader(f)}

    new_rows = []
    for it in items:
        u = it.get("url") or ""
        if u and u in existing_urls:
            continue  # anti dobel dalam file yang sama
        new_rows.append({
            "site": site,
            "keyword": keyword,
            "name": (it.get("name") or "").replace("\n", " "),
            "price_rp": parse_price_rp(it.get("price_text")),
            "price_text": it.get("price_text"),
            "author": it.get("author"),
            "time_text": it.get("time_text"),
            "comments": it.get("comments"),
            "shares": it.get("shares"),
            "description": (it.get("description") or "").replace("\r\n", " ").replace("\n", " "),
            "url": u,
            "is_question": it.get("is_question", ""),
            "group": it.get("group", ""),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        })

    if not new_rows:
        return path, 0

    file_exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8-sig", newline="") as f:  # BOM utk Excel
        w = csv.DictWriter(f, fieldnames=list(new_rows[0].keys()))
        if not file_exists:
            w.writeheader()
        w.writerows(new_rows)
    return path, len(new_rows)


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path != "/collect":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        # 1) simpan ke SQLite
        con = sqlite3.connect(DB)
        n_db = 0
        for it in data.get("items", []):
            con.execute(
                """INSERT INTO products
                   (site,keyword,name,price_rp,price_text,author,time_text,comments,shares,
                    description,url,page_url,type,is_question,group_name,scraped_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    data.get("site"), data.get("keyword"), it.get("name"),
                    parse_price_rp(it.get("price_text")), it.get("price_text"),
                    it.get("author"), it.get("time_text"), it.get("comments"), it.get("shares"),
                    it.get("description"), it.get("url"), data.get("page_url"),
                    data.get("type", "product"),
                    1 if it.get("is_question") else None,
                    it.get("group"),
                    data.get("scraped_at") or datetime.now(timezone.utc).isoformat(),
                ),
            )
            n_db += 1
        con.commit()
        con.close()

        # 2) langsung append ke CSV di folder hasil
        try:
            path, n_csv = append_csv(data.get("site"), data.get("keyword"), data.get("items", []))
            print(f"[collect] {data.get('site')} '{data.get('keyword')}' db+{n_db} | csv+{n_csv} -> {path}")
        except Exception as e:
            print(f"[collect] DB ok ({n_db}) tapi CSV gagal: {e}")
            path = "(csv error)"

        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps({"saved": n_db, "csv": path}).encode())

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/products":
            qs = parse_qs(parsed.query)
            sql = "SELECT * FROM products"
            cond, params = [], []
            if "site" in qs:
                cond.append("site LIKE ?")
                params.append(qs["site"][0] + "%")
            if cond:
                sql += " WHERE " + " AND ".join(cond)
            sql += " ORDER BY id DESC LIMIT 2000"
            con = sqlite3.connect(DB)
            con.row_factory = sqlite3.Row
            rows = [dict(r) for r in con.execute(sql, params)]
            con.close()
            body = json.dumps(rows, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/export.csv":
            qs = parse_qs(parsed.query)
            sql = "SELECT * FROM products ORDER BY id"
            con = sqlite3.connect(DB)
            con.row_factory = sqlite3.Row
            rows = [dict(r) for r in con.execute(sql)]
            con.close()
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(buf.getvalue().encode("utf-8-sig"))
            return

        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    init_db()
    print(f"WorL backend v3 jalan. Hasil CSV otomatis ke: {HASIL_DIR}")
    HTTPServer(("127.0.0.1", 8787), Handler).serve_forever()
