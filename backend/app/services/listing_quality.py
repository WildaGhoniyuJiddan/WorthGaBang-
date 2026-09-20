"""Aturan kualitas listing untuk pembanding harga (WorL).

Modul ini adalah SATU-SATUNYA sumber kebenaran untuk memutuskan apakah sebuah
listing layak dipakai sebagai pembanding harga.

Aturan bisnis (dari pemilik produk):
1. Barang bekas punya ciri utama di JUDUL dan DESKRIPSI: "like new",
   "pemakaian 1 tahun", "mulus", "fullset", dll. Karena itu deskripsi WAJIB
   ikut diperiksa, bukan hanya judul.
2. Listing dengan kata "ex mining" TIDAK BOLEH dipakai sebagai pembanding
   harga — harga GPU ex-mining jauh di bawah pasar sehingga merusak
   perhitungan harga wajar.
3. Listing dengan "ex gaming", "ex editing", "ex desain", dll BOLEH dipakai —
   yang dilarang HANYA "mining" (dan turunannya). Ini karena ekspose beban
   kerja gaming/editing tidak seberat 24/7 mining.
4. Harga dari toko Tokopedia yang sudah tidak aktif tidak relevan karena
   harganya tidak pernah diperbarui.

PENTING — desain konservatif:
Filter "mining" sengaja dibuat SEMPIT dan spesifik (frasa "ex mining",
"bekas mining", dsb), BUKAN sekadar substring "mining". Alasannya: kata
"mining" bisa muncul di konteks yang tidak relevan (mis. "mining rig case",
nama game, atau "non-mining"). Kita hanya membuang yang benar-benar
menyatakan barang pernah dipakai mining.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# 1. HARD REJECT: barang eks-mining
# ---------------------------------------------------------------------------
# Frasa yang secara eksplisit menyatakan unit pernah dipakai untuk mining.
# Ditulis sebagai frasa (bukan kata tunggal) supaya tidak salah tangkap.
EX_MINING_PATTERNS: tuple[str, ...] = (
    r"ex[\s\-_.]*mining",
    r"eks[\s\-_.]*mining",
    r"bekas[\s\-_.]*mining",
    r"mantan[\s\-_.]*mining",
    r"purna[\s\-_.]*mining",
    r"used[\s\-_.]*for[\s\-_.]*mining",
    r"ex[\s\-_.]*miner",
    r"eks[\s\-_.]*miner",
    r"mining[\s\-_.]*rig",
    r"rig[\s\-_.]*mining",
    r"ex[\s\-_.]*mining[\s\-_.]*rig",
    r"kartu[\s\-_.]*mining",
    r"vga[\s\-_.]*mining",
    r"gpu[\s\-_.]*mining",
    r"tambang[\s\-_.]*crypto",
    r"ex[\s\-_.]*tambang",
    r"crypto[\s\-_.]*mining",
    r"sisa[\s\-_.]*mining",
    r"pemakaian[\s\-_.]*mining",
    r"dipakai[\s\-_.]*mining",
    r"untuk[\s\-_.]*mining",
    r"24[\s\-_.]*jam[\s\-_.]*(nonstop|non[\s\-_.]*stop)[\s\-_.]*mining",
)

_EX_MINING_RE = re.compile("|".join(f"(?:{p})" for p in EX_MINING_PATTERNS), re.IGNORECASE)

# Kasus khusus: "non-mining" / "bukan ex mining" adalah KLAIM POSITIF.
# Kalau muncul, jangan buang listing-nya.
_NEGATION_PATTERNS: tuple[str, ...] = (
    r"non[\s\-_.]*mining",
    r"bukan[\s\-_.]*(ex|eks|bekas)[\s\-_.]*mining",
    r"no[\s\-_.]*mining",
    r"never[\s\-_.]*mining",
    r"tidak[\s\-_.]*pernah[\s\-_.]*mining",
    r"bukan[\s\-_.]*barang[\s\-_.]*mining",
)
_NEGATION_RE = re.compile("|".join(f"(?:{p})" for p in _NEGATION_PATTERNS), re.IGNORECASE)


# ---------------------------------------------------------------------------
# 2. ALLOW-LIST: "ex gaming" / "ex editing" dan sejenisnya BOLEH dipakai
# ---------------------------------------------------------------------------
# Ini bukan filter yang membuang, tapi sinyal bahwa unit berasal dari
# pemakaian wajar (bukan mining). Dipakai untuk (a) memberi konteks ke
# pengguna, (b) memastikan kita tidak salah buang karena kata "ex".
ALLOWED_EX_USAGE_PATTERNS: tuple[str, ...] = (
    r"ex[\s\-_.]*gaming",
    r"eks[\s\-_.]*gaming",
    r"bekas[\s\-_.]*gaming",
    r"ex[\s\-_.]*editing",
    r"eks[\s\-_.]*editing",
    r"bekas[\s\-_.]*editing",
    r"ex[\s\-_.]*desain",
    r"ex[\s\-_.]*design",
    r"ex[\s\-_.]*kantor",
    r"ex[\s\-_.]*office",
    r"ex[\s\-_.]*render",
    r"ex[\s\-_.]*streaming",
    r"ex[\s\-_.]*mahasiswa",
    r"ex[\s\-_.]*personal",
    r"ex[\s\-_.]*pribadi",
    r"ex[\s\-_.]*game",
)
_ALLOWED_EX_RE = re.compile("|".join(f"(?:{p})" for p in ALLOWED_EX_USAGE_PATTERNS), re.IGNORECASE)


# ---------------------------------------------------------------------------
# 3. Sinyal kondisi bekas (dipakai untuk pengayaan, bukan pembuangan)
# ---------------------------------------------------------------------------
USED_HINT_PATTERNS: tuple[str, ...] = (
    r"like[\s\-_.]*new",
    r"mulus",
    r"pemakaian\s+\d+\s*(tahun|thn|bulan|bln)",
    r"dipakai\s+\d+\s*(tahun|thn|bulan|bln)",
    r"pemakaian\s+(sebentar|singkat|jarang)",
    r"jarang\s+dipakai",
    r"bekas",
    r"second",
    r"2nd",
    r"preloved",
    r"fullset",
    r"full[\s\-_.]*set",
    r"minus",
    r"ada\s+minus",
    r"garansi\s+(habis|expired|mati)",
    r"no[\s\-_.]*garansi",
    r"tanpa\s+garansi",
)
_USED_HINT_RE = re.compile("|".join(f"(?:{p})" for p in USED_HINT_PATTERNS), re.IGNORECASE)

# Sinyal barang BARU.
NEW_HINT_PATTERNS: tuple[str, ...] = (
    r"\bbaru\b",
    r"brand[\s\-_.]*new",
    r"bnib",
    r"segel",
    r"masih[\s\-_.]*segel",
    r"garansi\s+resmi",
    r"garansi\s+\d+\s*(tahun|thn|bulan|bln)",
    r"unboxed",
    r"new[\s\-_.]*in[\s\-_.]*box",
)
_NEW_HINT_RE = re.compile("|".join(f"(?:{p})" for p in NEW_HINT_PATTERNS), re.IGNORECASE)


@dataclass
class ListingQuality:
    """Hasil penilaian kualitas sebuah listing."""

    is_acceptable: bool
    reject_reason: Optional[str] = None
    condition_hint: Optional[str] = None          # "new" | "second" | None
    usage_context: Optional[str] = None           # "ex gaming" | "ex editing" | None
    matched_terms: list[str] = field(default_factory=list)

    @property
    def is_ex_mining(self) -> bool:
        return self.reject_reason == "ex_mining"


def _haystack(*parts: Optional[str]) -> str:
    """Gabungkan judul + deskripsi + spec jadi satu teks untuk diperiksa.

    Normalisasi ringan: buang karakter kontrol & rapikan spasi, supaya
    "ex  mining" dan "ex-mining" sama-sama tertangkap.
    """
    chunks: list[str] = []
    for part in parts:
        if not part:
            continue
        text = str(part).replace("\u00a0", " ")
        text = re.sub(r"[\r\n\t]+", " ", text)
        chunks.append(text)
    return re.sub(r"\s+", " ", " ".join(chunks)).strip()


def detect_ex_mining(*parts: Optional[str]) -> Optional[str]:
    """Kembalikan frasa ex-mining yang cocok, atau None kalau bersih.

    Menghormati negasi ("non mining", "bukan ex mining") — kalau negasi
    ditemukan, listing dianggap bersih.
    """
    text = _haystack(*parts)
    if not text:
        return None
    if _NEGATION_RE.search(text):
        return None
    match = _EX_MINING_RE.search(text)
    return match.group(0).strip() if match else None


def detect_allowed_ex_usage(*parts: Optional[str]) -> Optional[str]:
    """Deteksi 'ex gaming' / 'ex editing' / dll yang BOLEH lolos."""
    text = _haystack(*parts)
    if not text:
        return None
    match = _ALLOWED_EX_RE.search(text)
    return match.group(0).strip() if match else None


def detect_used_hint(*parts: Optional[str]) -> list[str]:
    """Kumpulkan frasa yang menandakan barang bekas."""
    text = _haystack(*parts)
    if not text:
        return []
    return sorted({m.group(0).strip().lower() for m in _USED_HINT_RE.finditer(text)})


def detect_new_hint(*parts: Optional[str]) -> list[str]:
    """Kumpulkan frasa yang menandakan barang baru."""
    text = _haystack(*parts)
    if not text:
        return []
    return sorted({m.group(0).strip().lower() for m in _NEW_HINT_RE.finditer(text)})


def classify_condition(title: Optional[str], description: Optional[str] = None,
                       spec_text: Optional[str] = None) -> tuple[Optional[str], list[str]]:
    """Tentukan kondisi (new/second) berdasarkan judul + deskripsi + spec.

    Prioritas: sinyal bekas menang atas sinyal baru, karena penjual biasanya
    menulis "baru" untuk menarik perhatian tapi menyebut kondisi asli
    ("like new", "bekas") di deskripsi. Ini konservatif: kalau ragu, anggap
    bekas supaya pembanding harga tidak terlalu optimistis.
    """
    used = detect_used_hint(title, description, spec_text)
    new = detect_new_hint(title, description, spec_text)
    if used:
        return "second", used + new
    if new:
        return "new", new
    return None, []


def assess_listing(
    title: Optional[str],
    description: Optional[str] = None,
    spec_text: Optional[str] = None,
    *,
    require_condition_evidence: bool = False,
) -> ListingQuality:
    """Penilaian utama: apakah listing layak jadi pembanding harga.

    ``require_condition_evidence``: kalau True, listing tanpa sinyal kondisi
    apa pun ditolak (dipakai kalau pemilik produk ingin data paling bersih).
    Default False supaya kita tidak kehilangan terlalu banyak data.
    """
    mining = detect_ex_mining(title, description, spec_text)
    if mining:
        return ListingQuality(
            is_acceptable=False,
            reject_reason="ex_mining",
            matched_terms=[mining],
        )

    usage = detect_allowed_ex_usage(title, description, spec_text)
    condition, hints = classify_condition(title, description, spec_text)

    if require_condition_evidence and condition is None:
        return ListingQuality(
            is_acceptable=False,
            reject_reason="no_condition_evidence",
            usage_context=usage,
        )

    return ListingQuality(
        is_acceptable=True,
        condition_hint=condition,
        usage_context=usage,
        matched_terms=hints,
    )


def filter_acceptable(records: Iterable, *, title_attr: str = "title",
                      desc_attr: str = "spec_text") -> tuple[list, list]:
    """Pisahkan records jadi (lolos, dibuang) memakai :func:`assess_listing`.

    Mengembalikan tuple ``(accepted, rejected)`` di mana ``rejected`` berisi
    pasangan ``(record, ListingQuality)`` supaya pemanggil bisa mencatat
    alasan pembuangan.
    """
    accepted: list = []
    rejected: list[tuple[object, ListingQuality]] = []
    for record in records:
        verdict = assess_listing(
            getattr(record, title_attr, None),
            getattr(record, desc_attr, None),
        )
        if verdict.is_acceptable:
            accepted.append(record)
        else:
            rejected.append((record, verdict))
    return accepted, rejected
