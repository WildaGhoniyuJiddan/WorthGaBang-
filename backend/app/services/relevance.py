import re
from typing import Optional


_BUILD_WORDS = (
    "pc gaming",
    "gaming pc",
    "pc rakitan",
    "rakit pc",
    "rakitan pc",
    "komputer",
    "desktop",
    "pc mini",
    "mini itx",
    "built up",
    "full set pc",
    "pc full set",
    "paket pc",
    "paket gaming",
    "cpu rakitan",
    "pc build",
    "build pc",
    "hackintosh",
)

_ACCESSORY_WORDS = (
    "fan ",
    "kipas",
    "cooler ",
    "heatsink",
    "radiator",
    "dus ",
    "box only",
    "bracket",
    "cable",
    "kabel",
    "fleksibel",
    "flexible",
    "riser",
    "backplate",
    "sticker",
    "case ",
    "casing",
    "housing",
    "adapter",
    "adaptor",
    "cover ",
    "enclosure",
    "charger",
    "baterai",
    "battery",
    "battrey",
    "batre",
    "keyboard",
    "mouse ",
    "headset",
    "tempered glass",
    "hydrogel",
    "skin ",
    "sleeve",
    "tas ",
    "bag ",
    "lcd ",
    "led lcd",
    "panel lcd",
    "engsel",
    "hinge",
    "touchpad",
    "speaker laptop",
    "sparepart",
    "spare part",
)

# ---------------------------------------------------------------------------
# Taksonomi & Deteksi Laptop Komprehensif (Berdasarkan DAFTAR_LAPTOP_INDONESIA.md)
# ---------------------------------------------------------------------------

_LAPTOP_GENERIC_WORDS = re.compile(
    r"\b(?:laptop|notebook|netbook|macbook|ultrabook|chromebook|2-in-1|two-in-one)\b",
    re.IGNORECASE,
)

# Seri yang secara eksklusif merupakan unit laptop (bukan komponen GPU/CPU/mobo)
_EXCLUSIVE_LAPTOP_SERIES = re.compile(
    r"\b(?:"
    # Dell & Alienware
    r"alienware|aurora\s*(?:1[5678]|\d{2})|dell\s*g1[56]|dell\s*g[357]|xps\s*1[34567]|"
    r"inspiron(?:\s*1[3456])?|latitude(?:\s*\d{4})?|vostro(?:\s*\d{4})?|precision(?:\s*\d{4})?|"
    # Lenovo
    r"legion(?:\s*(?:pro|slim)?\s*\d{1,2}[a-z]*)?|loq(?:\s*\d{1,2}[a-z]*)?|"
    r"ideapad(?:\s*(?:slim|flex|gaming|pro)?\s*\d{1,2}[a-z]*)?|"
    r"yoga(?:\s*(?:slim|pro|book)?\s*\d{1,2}[a-z]*)?|thinkpad(?:\s*[a-z]\d{2,4}[a-z]*)?|thinkbook|"
    # Acer
    r"acer\s*nitro(?:\s*v)?(?:\s*\d{1,2}[a-z]*)?|nitro\s*(?:v\s*\d{1,2}|[57]\b)|swift(?:\s*(?:go|edge|x|\d{1,2}))?|"
    r"aspire(?:\s*(?:lite|vero|pro|\d{1,2}))?|travelmate|spin\s*\d|"
    # HP
    r"victus(?:\s*\d{1,2})?|omen(?:\s*(?:transcend|\d{1,2}))?|"
    r"pavilion(?:\s*(?:plus|aero|gaming|x360|\d{1,2}))?|"
    r"elitebook(?:\s*\d{3,4})?|probook(?:\s*\d{3,4})?|zbook|dragonfly|"
    r"hp\s*1[45]s\b|hp\s*24[05]\b|envy(?:\s*x360|\s*\d{1,2})?|spectre(?:\s*x360|\s*\d{1,2})?|"
    # MSI
    r"katana(?:\s*\d{2})?|cyborg(?:\s*\d{2})?|msi\s*sword|sword\s*1[567]|"
    r"msi\s*crosshair|crosshair\s*1[567]|msi\s*pulse|pulse\s*1[567]|"
    r"gf6[35]\b|thin\s*15\b|bravo\s*15\b|modern\s*1[45]\b|prestige\s*\d{2}\b|"
    r"summit\s*e?\d{2}\b|stealth\s*\d{2}\b|vector\s*g[pe]\b|raider\s*ge\b|titan\s*gt\b|"
    # Apple
    r"macbook(?:\s*(?:air|pro))?|"
    # Brand Lokal Indonesia
    r"pongo(?:\s*\d{3})?|hype\s*\d{1,2}\b|"
    r"workplus|workpro|pixelwar|360\s*stylus|soulmate|"
    # Brand Ekosistem & Impor / Ex-Corporate
    r"matebook|inbook|gt\s*book|redmibook|realme\s*book|"
    r"surface\s*(?:pro|laptop|go|book)|lifebook|let'?s\s*note|toughbook|"
    r"dynabook|portege|tecra|vaio(?:\s*[a-z]{2}\d{2})?|"
    # ASUS
    r"zenbook(?:\s*(?:flip|duo|pro|s))?|vivobook(?:\s*(?:go|pro|s|flip|slate))?|expertbook|"
    r"zephyrus(?:\s*g\d{2})?|rog\s*flow|rog\s*ally|"
    # Others
    r"razer\s*blade|colorful\s*evol"
    r")\b",
    re.IGNORECASE,
)

# Brand gaming dual-use yang membedakan kartu grafis vs model laptop spesifik
_DUAL_USE_LAPTOP_SPECIFIC = re.compile(
    r"\b(?:"
    r"tuf\s*(?:gaming\s*)?(?:a1[4567]|f1[567]|dash\s*f1[567]|[af]\d{2,3})|"
    r"fa\d{3}[a-z]*|fx\d{3}[a-z]*|"
    r"rog\s*strix\s*(?:g1[5-8]|scar|hero|\d{2})|"
    r"predator\s*(?:helios|triton)|helios\s*(?:neo|\d{2})|triton\s*\d{2}|"
    r"aorus\s*(?:1[567]|master\s*1[567])"
    r")\b",
    re.IGNORECASE,
)

# Indikator fisik layar / display (laptop selalu memiliki layar fisik)
_SCREEN_SIZE_RE = re.compile(
    r"\b1[1-7](?:\.[0-9])?\s*(?:[\"”]|inch|\-inch|\s*inci)\b",
    re.IGNORECASE,
)

_SCREEN_FEATURE_RE = re.compile(
    r"\b(?:fhd|qhd|wqhd|2\.8k|2\.5k|3k|4k|oled|ips)\b.*\b(?:120hz|144hz|165hz|240hz|300hz|360hz|touch(?:screen)?)\b|"
    r"\b(?:120hz|144hz|165hz|240hz|300hz|360hz)\b.*\b(?:fhd|qhd|wqhd|2\.8k|2\.5k|3k|4k|oled|ips)\b",
    re.IGNORECASE,
)

# Prosesor mobile (laptop) dengan suffix H/HX/HS/HK/U atau seri mobile 3-5 digit
_MOBILE_CPU_RE = re.compile(
    r"\b(?:"
    r"(?:core\s*(?:ultra\s*)?[3579]|ultra\s*[579]|intel\s*core|i[3579])\s*[- ]?\s*(?:\d{3,5}\s*(?:hx|hs|hk|h|u))\b|"
    r"ryzen\s*(?:ai)?\s*[3579]\s*[- ]?\s*(?:\d{4}[a-z]{0,2}\s*(?:hs|hx|h|u)|\d{3}\b)|"
    r"core\s+ultra|ryzen\s+ai"
    r")",
    re.IGNORECASE,
)

# Penanda spesifikasi sistem lengkap gabungan (RAM + Storage) khas laptop/prebuilt
_SYSTEM_SPEC_RE = re.compile(
    r"\b\d{1,2}\s*gb\s*/\s*\d{1,2}\s*(?:gb)?\s*/\s*\d{3,4}\s*gb\b|"
    r"\b\d{1,2}\s*(?:gb)?\s*/\s*\d{3,4}\s*(?:gb|tb)\b|"
    r"\b(?:8|16|32|64)\s*gb\s+(?:256\s*gb|512\s*gb|1\s*tb|2\s*tb)\b",
    re.IGNORECASE,
)

# Penanda OS / software terpasang pada unit lengkap
_BUNDLED_OS_RE = re.compile(
    r"\b(?:w11|win\s*11|windows\s*11|w10|win\s*10|windows\s*10|ohs\d*|office\s*home)\b",
    re.IGNORECASE,
)

_BUILD_WORDS_RE = re.compile(
    r"\b(?:"
    r"pc\s*gaming|gaming\s*pc|pc\s*rakitan|rakit\s*pc|rakitan\s*pc|"
    r"pc\s*build|build\s*pc|komputer|desktop\s*pc|pc\s*mini|mini\s*itx|"
    r"built\s*up|full\s*set\s*pc|pc\s*full\s*set|paket\s*full\s*set|paket\s*pc|paket\s*gaming|cpu\s*rakitan|"
    r"hackintosh"
    r")\b",
    re.IGNORECASE,
)

# Penanda komponen aktif
_GPU_MARKER_RE = re.compile(
    r"\b(?:rtx|gtx)\s*\d{3,4}\b|\brx\s*\d{3,4}\b|\bvga\b|\bradeon\s*rx\b|\bgeforce\b|\barc\s*a?\d*",
    re.IGNORECASE,
)

_CPU_MARKER_RE = re.compile(
    r"\b(?:"
    r"core\s*(?:ultra\s*)?[3579]|ultra\s*[579]|intel\s*core|i[3579]|"
    r"ryzen\s*(?:ai\s*)?[3579]"
    r")\s*[- ]?\s*\d{3,5}[a-z]{0,3}\b",
    re.IGNORECASE,
)


def is_laptop_listing(title: str, spec_text: str = "") -> bool:
    """Deteksi apakah judul/spek merupakan unit laptop utuh."""
    text = f"{title} {spec_text}".lower()
    if any(word in text for word in _ACCESSORY_WORDS):
        return False
    # Brand kartu grafis lepas yang tidak pernah memproduksi laptop
    if "sapphire" in text:
        return False
    if _LAPTOP_GENERIC_WORDS.search(text):
        return True
    if _EXCLUSIVE_LAPTOP_SERIES.search(text):
        return True
    if _DUAL_USE_LAPTOP_SPECIFIC.search(text):
        return True
    if _SCREEN_SIZE_RE.search(text):
        return True
    if _SCREEN_FEATURE_RE.search(text):
        return True
    if _MOBILE_CPU_RE.search(text) and (_SYSTEM_SPEC_RE.search(text) or _BUNDLED_OS_RE.search(text)):
        return True
    return False


def is_pc_build_listing(title: str) -> bool:
    """Deteksi apakah judul merupakan paket rakitan PC atau sistem desktop utuh."""
    text = (title or "").lower()
    return bool(_BUILD_WORDS_RE.search(text))


def component_type_from_query(query: str) -> str | None:
    """Tentukan tipe komponen dari query pencarian."""
    text = (query or "").lower()
    if is_laptop_listing(text):
        return "laptop"
    if re.search(r"\b(?:rtx|gtx|rx|arc)\s*(?:[ab]?\d{3,4})", text):
        return "gpu"
    if re.search(r"\b(?:ryzen\s*(?:ai\s*)?[3579]|core\s*(?:ultra\s*)?[3579]|ultra\s*[579]|intel\s*core|i[3579])\s*[- ]?\d{3,5}", text):
        return "cpu"
    # Section pasif: RAM (ddr + kapasitas), storage, motherboard.
    if re.search(r"\bram\b|\bmemori\b|\bmemory\b|\bddr[345]\b", text):
        return "ram"
    if re.search(r"\bssd\b|\bhdd\b|\bnvme\b|\bharddisk\b|\bhardisk\b|\bm\.?2\s*(?:sata|nvme)\b", text):
        return "storage"
    if re.search(r"\bmotherboard\b|\bmobo\b", text) or re.search(r"\b[a-z]\d{3,4}\w*-?m?\b", text):
        return "motherboard"
    return None


def is_standalone_component_query(query: str) -> bool:
    text = (query or "").lower()
    return component_type_from_query(text) not in (None, "laptop") and not is_laptop_listing(text)


def _component_signature(value: str, component_type: str | None) -> tuple[str, str] | None:
    text = (value or "").lower()
    if component_type == "gpu":
        # Suffix Ti/Super/XT = produk BEDA ("RTX 4060" != "RTX 4060 Ti", harga bisa 2x)
        match = re.search(r"\b(rtx|gtx|rx|arc)\s*([ab]?\d{3,4})\s*(ti|super|xt)?\b", text)
        if match:
            return "gpu", f"{match.group(1)}{match.group(2)}{match.group(3) or ''}"
    if component_type == "cpu":
        # Suffix huruf (X/F/K/H) = SKU beda ("5600" != "5600X")
        match = re.search(r"\b(ryzen\s*[3579]|core\s*i[3579])\s*-?\s*(\d{4,5})([a-z]{0,2})?\b", text)
        if match:
            return "cpu", re.sub(r"\s+", "", match.group(1)) + match.group(2) + (match.group(3) or "")
    if component_type == "ram":
        ddr = re.search(r"ddr\s*([345])", text)
        gb = re.search(r"(\d{1,2})\s*gb\b", text)
        if ddr and gb:
            return "ram", f"ddr{ddr.group(1)} {gb.group(1)}gb"
    if component_type == "storage":
        kind = "ssd" if re.search(r"\b(ssd|nvme|m\.?2)\b", text) else ("hdd" if re.search(r"\bhdd\b|\bharddisk\b|\bhardisk\b", text) else None)
        if kind:
            gb = re.search(r"(\d{1,3})\s*gb\b", text)
            tb = re.search(r"(\d)\s*tb\b", text)
            size = f"{gb.group(1)}gb" if gb else (f"{tb.group(1)}tb" if tb else None)
            if size:
                return "storage", f"{kind} {size}"
    if component_type == "motherboard":
        chipset = re.search(r"\b([abxzi]\d{3})[a-z]{0,2}\b", text)
        if chipset:
            return "motherboard", chipset.group(1)
    return None


def is_relevant_pc_listing(query: str, title: str, component_type: str | None = None) -> bool:
    """Tolak listing yang tidak relevan dengan query komponen satuan."""
    query_text = (query or "").lower()
    title_text = (title or "").lower()
    resolved_type = component_type or component_type_from_query(query_text)

    query_signature = _component_signature(query_text, resolved_type)
    title_signature = _component_signature(title_text, resolved_type)
    if query_signature and title_signature and query_signature != title_signature:
        return False

    # Aksesori & spare part selalu gugur
    if any(word in title_text for word in _ACCESSORY_WORDS):
        return False

    # Mode LAPTOP
    if resolved_type == "laptop":
        return is_laptop_listing(title_text)

    # Mode KOMPONEN PC SATUAN (GPU, CPU, RAM, Storage, Mobo)
    # 1. Hard-gate: unit laptop TIDAK BOLEH menjadi pembanding komponen PC
    if is_laptop_listing(title_text):
        return False

    # 2. Hard-gate: sistem PC rakitan lengkap TIDAK BOLEH menjadi pembanding komponen PC
    if is_pc_build_listing(title_text):
        return False

    if any(word in title_text for word in ("bundle", "bundling", "paket")):
        return False

    # Filter khusus GPU lepas
    if resolved_type == "gpu":
        # Konflik kapasitas VRAM jika query eksplisit menyebutkan VRAM
        query_vram = re.search(r"\b(\d{1,2})\s*gb\b", query_text)
        title_vram = re.search(r"\b(\d{1,2})\s*gb\b", title_text)
        if query_vram and title_vram and query_vram.group(1) != title_vram.group(1):
            return False

        # Kartu grafis lepas tidak pernah mencantumkan prosesor CPU
        if _CPU_MARKER_RE.search(title_text):
            return False
        # Kartu grafis lepas tidak memiliki ukuran layar fisik
        if _SCREEN_SIZE_RE.search(title_text) or _SCREEN_FEATURE_RE.search(title_text):
            return False
        # Kartu grafis lepas tidak memiliki notasi spec memori/storage ganda sistem
        if _SYSTEM_SPEC_RE.search(title_text):
            return False
        # Kartu grafis lepas tidak dilengkapi sistem operasi terpasang
        if _BUNDLED_OS_RE.search(title_text):
            return False
        # Multi-chipset GPU dalam 1 judul (mis. "RTX5060 / RTX5050") gugur
        matches = re.findall(r"\b(?:rtx|gtx|rx|arc)\s*([ab]?\d{3,4})\s*(ti|super|xt)?\b", title_text)
        if matches:
            distinct_models = {f"{m[0]}{(m[1] or '')}" for m in matches}
            if len(distinct_models) > 1:
                return False

    # Filter khusus CPU lepas
    if resolved_type == "cpu":
        # Prosesor desktop satuan tidak pernah mencantumkan GPU diskret
        if _GPU_MARKER_RE.search(title_text):
            return False
        # Prosesor desktop satuan tidak menggunakan suffix mobile laptop
        if _MOBILE_CPU_RE.search(title_text):
            return False
        if _SCREEN_SIZE_RE.search(title_text) or _SCREEN_FEATURE_RE.search(title_text):
            return False
        if _SYSTEM_SPEC_RE.search(title_text) or _BUNDLED_OS_RE.search(title_text):
            return False

    # Filter khusus komponen pasif (RAM, Storage, Motherboard)
    if resolved_type in {"ram", "storage", "motherboard"}:
        if _GPU_MARKER_RE.search(title_text) or _CPU_MARKER_RE.search(title_text):
            return False
        if re.search(r"\s[+|]\s", title_text):
            return False
        if _SCREEN_SIZE_RE.search(title_text) or _BUNDLED_OS_RE.search(title_text):
            return False
        if resolved_type == "ram" and re.search(
            r"ram\s*\d+\s*gb\b.*\b(?:ssd|nvme|win|fhd|intel|core)\b|\b(?:ssd\d|ssd)\s*\d+\s*[gt]b\b",
            title_text,
        ):
            return False

    return True


def query_variants(query: str, max_variants: int = 5) -> list[str]:
    """Build safe marketplace queries without changing the canonical model."""
    base = " ".join((query or "").split()).strip()
    if not base:
        return []
    component_type = component_type_from_query(base)
    if component_type == "gpu":
        brand_variant = f"Radeon {base}" if base.lower().startswith("rx ") else f"graphics card {base}"
        variants = [base, f"VGA {base}", brand_variant, f"{base} bekas", f"{base} baru", f"graphics card {base}"]
    elif component_type == "cpu":
        variants = [base, f"processor {base}", f"{base} bekas", f"{base} baru", f"CPU {base}"]
    else:
        variants = [base, f"{base} bekas", f"{base} baru"]
    seen: set[str] = set()
    result: list[str] = []
    for variant in variants:
        normalized = " ".join(variant.split())
        key = normalized.lower()
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return result[: max(1, max_variants)]
