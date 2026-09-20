"""Ekstraksi halaman detail produk Tokopedia TANPA Jina / browser.

Temuan riset (diuji langsung, bukan asumsi):
    GET langsung ke URL produk dengan User-Agent browser mengembalikan
    HTML lengkap (~250 KB) berisi data terstruktur Tokopedia, termasuk
    deskripsi produk, kondisi resmi, dan status toko.

Ini jauh lebih cepat dan stabil daripada lewat r.jina.ai:
    - Jina  : ~3.5 s/produk, sering HTTP 500 kalau kena rate limit.
    - Direct: ~0.6-0.8 s/produk, tidak terlihat kena rate limit.

Bukti field yang tersedia di HTML mentah:
    <div data-testid="lblPDPDescriptionProduk">...deskripsi...</div>
    "condition":"USED" | "NEW"     -> kondisi resmi dari Tokopedia
    "shopName":"..."               -> nama toko
    "countSold":N, "countReview":N -> aktivitas penjualan
    "isActive":true|false          -> status toko masih aktif atau tidak

Semua diambil dengan regex + html.unescape. TIDAK memakai parser HTML berat
supaya fungsi ini tetap bisa jalan di lingkungan serverless Vercel.
"""

from __future__ import annotations

import html
import json
import re
from typing import Optional

# UA browser asli. UA bot justru ditolak/di-deface oleh Tokopedia.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)

_DESC_RE = re.compile(
    r'data-testid="lblPDPDescriptionProduk"[^>]*>(.*?)</div>', re.S | re.I
)
_CONDITION_RE = re.compile(r'"condition"\s*:\s*"(NEW|USED)"', re.I)
_SHOP_NAME_RE = re.compile(r'"shopName"\s*:\s*"((?:[^"\\]|\\.)*)"')
_SOLD_RE = re.compile(r'"countSold"\s*:\s*"?(\d+)"?')
_REVIEW_RE = re.compile(r'"countReview"\s*:\s*"?(\d+)"?')
_ACTIVE_RE = re.compile(r'"isActive"\s*:\s*(true|false)', re.I)
_RATING_RE = re.compile(r'"rating"\s*:\s*"?([\d.]+)"?')
_CATEGORY_RE = re.compile(r'"categoryName"\s*:\s*"((?:[^"\\]|\\.)*)"')
_URL_RE = re.compile(r'"url"\s*:\s*"(https://www\.tokopedia\.com/[^"]+)"')


def _clean_html_text(chunk: str) -> str:
    """Ubah potongan HTML deskripsi jadi teks biasa yang bisa di-regex."""
    text = re.sub(r"<br\s*/?>", "\n", chunk, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _json_str(raw: str) -> Optional[str]:
    try:
        return json.loads('"' + raw + '"')
    except Exception:
        return raw


def extract_detail(body: str) -> dict:
    """Ambil data kualitas dari HTML halaman detail produk Tokopedia.

    Mengembalikan dict dengan kunci yang hanya muncul kalau datanya ada,
    sehingga pemanggil bisa membedakan "kosong" dari "tidak tersedia".

    CATATAN PENTING soal ``isActive``: field itu BUKAN status toko. Dari
    pemeriksaan nyata, ``isActive`` menempel pada objek promo/campaign
    ("endDate", "hideGimmick") dan pada objek preorder ("preorderInDays").
    Karena itu field ini SENGAJA tidak dipakai sebagai sinyal toko aktif —
    memakainya akan salah menandai toko sehat sebagai mati.
    """
    if not body:
        return {}
    info: dict = {}

    match = _DESC_RE.search(body)
    if match:
        desc = _clean_html_text(match.group(1))
        if desc:
            info["description"] = desc[:6000]

    match = _CONDITION_RE.search(body)
    if match:
        info["condition_source"] = "Bekas" if match.group(1).upper() == "USED" else "Baru"
        info["condition_enum"] = match.group(1).upper()

    match = _SHOP_NAME_RE.search(body)
    if match:
        name = _json_str(match.group(1))
        if name:
            info["seller"] = name.strip()[:255]

    match = _SOLD_RE.search(body)
    if match:
        info["sold_count"] = int(match.group(1))

    match = _REVIEW_RE.search(body)
    if match:
        info["review_count"] = int(match.group(1))

    match = _ACTIVE_RE.search(body)
    if match:
        info["shop_active"] = match.group(1).lower() == "true"

    match = _RATING_RE.search(body)
    if match:
        try:
            info["rating"] = float(match.group(1))
        except ValueError:
            pass

    match = _CATEGORY_RE.search(body)
    if match:
        cat = _json_str(match.group(1))
        if cat:
            info["category_name"] = cat.strip()[:120]

    return info


def looks_like_dead_listing(body: str) -> bool:
    """Deteksi halaman produk yang sudah tidak dijual (410/404/de-listed)."""
    if not body:
        return True
    lowered = body.lower()
    if "lblpdpdescriptionproduk" in lowered:
        return False
    markers = (
        "produk tidak ditemukan",
        "produk telah dihapus",
        "produk sudah tidak aktif",
        "halaman tidak ditemukan",
        "not found",
    )
    return any(marker in lowered for marker in markers)
