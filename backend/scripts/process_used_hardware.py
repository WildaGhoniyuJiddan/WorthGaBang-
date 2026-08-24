from __future__ import annotations

import argparse
import csv
import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


OUTPUT_COLUMNS = [
    "record_id",
    "status",
    "source_file",
    "source_site",
    "search_keyword",
    "canonical_title",
    "source_title",
    "description",
    "product_type",
    "component_category",
    "classification_confidence",
    "classification_reason",
    "condition_tags",
    "brand",
    "gpu_model",
    "cpu_model",
    "ram_gb",
    "storage_gb",
    "vram_gb",
    "screen_size_in",
    "price_rp",
    "price_text_raw",
    "price_missing",
    "keyword_mismatch",
    "possible_duplicate_title_price",
    "quality_flags",
    "source_url",
    "scraped_at",
]


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = BACKEND_ROOT / "data" / "raw"
DEFAULT_OUTPUT_DIR = BACKEND_ROOT / "data" / "used_hardware"


LAPTOP_PATTERNS = [
    r"\blaptop\b",
    r"\bnotebook\b",
    r"\bmacbook\b",
    r"\bchromebook\b",
    r"\bultrabook\b",
    r"\bthinkpad\b",
    r"\bideapad\b",
    r"\bvivobook\b",
    r"\bzenbook\b",
    r"\binspiron\b",
    r"\blatitude\b",
    r"\belitebook\b",
    r"\bprobook\b",
    r"\bpavilion\b",
    r"\bomen\b",
    r"\bvictus\b",
    r"\baspire\b",
    r"\bswift\b",
    r"\bpredator\b",
    r"\bnitro\b",
    r"\blegion\b",
    r"\blegion\d{1,2}\b",
    r"\bloq\b",
    r"\bloq\d{1,2}\b",
    r"\bzephyrus\b",
    r"\brog\s+(?:strix|flow|ally)\b",
    r"\brog\s+(?:scar\s+)?g\d{2,4}[a-z]{0,3}\b",
    r"\brog\s+(?:gl|gx|ga|g)\s*\d{2,4}[a-z]{0,3}\b",
    r"\bideapad\b",
    r"\bmatebook\b",
    r"\bmagicbook\b",
    r"\bsurface\b",
    r"\brazer\s+blade\b",
    r"\balienware\s+[mx]\d{2}\b",
    r"\b(?:axioo\s+)?pongo\b",
    r"\btuf\s+(?:gaming\s+)?[af]\d{2,5}\b",
    r"\b(?:fx|fa|an|ga|gx)\d{3,5}(?:-\d{1,3})?[a-z]{0,3}\b",
    r"\b(?:fx|fa|an|ga|gx)\s*\d{3,5}(?:-\d{1,3})?[a-z]{0,3}\b",
    r"\b(?:katana|cyborg|raider|vector|sword|pulse|stealth|bravo)\b",
    r"\bgf\d{2,3}\b",
    r"\bvictus\d{1,2}\b",
    r"\b(?:asus\s+)?pro\s+\d{1,2}x\b",
]

FULLSET_PATTERNS = [
    r"\bpc\s*/?\s*(?:komputer\s+)?(?:gaming|rakitan|rendering|editing|fullset|office|desain|siap|murah|gahar)\b",
    r"\b(?:jual|dijual|wts|jual cepat)\s+(?:pc|komputer)\b",
    r"^\s*pc\b",
    r"\bkomputer\b",
    r"\bdesktop\b",
    r"\bsetup\s+pc\b",
    r"\bmini\s*pc\b",
    r"\bworkstation\b",
    r"\ball\s*[- ]?in\s*[- ]?one\b",
]

GPU_PATTERN = re.compile(
    r"\b(?:vga|gpu|geforce|radeon|graphics\s*(?:card)?|kartu\s+grafis)\b"
    r"|\b(?:rtx|gtx|rx)\s*\d{3,4}\b"
    r"|\b(?:intel\s+)?arc\s+[ab]\s*\d{3}\b",
    re.IGNORECASE,
)
GPU_MODEL_PATTERN = re.compile(
    r"\b(?:nvidia\s+)?(?:rtx|gtx|rx)\s*\d{3,4}(?:\s*(?:ti|super|xt|gre|oc))?\b"
    r"|\b(?:intel\s+)?arc\s+[ab]\s*\d{3}\b",
    re.IGNORECASE,
)
CPU_PATTERN = re.compile(
    r"\b(?:processor|proci|cpu|ryzen|pentium|celeron|xeon)\b"
    r"|\bcore\s+i[3579]\b"
    r"|\bi[3579]\s*[- ]?\s*\d{4,5}\b",
    re.IGNORECASE,
)
CPU_MODEL_PATTERNS = [
    re.compile(r"\bRyzen\s*[3579]\s*[- ]?\s*\d{3,4}[A-Za-z]*\b", re.IGNORECASE),
    re.compile(r"\bCore\s+Ultra\s+\d+\s*[A-Za-z]*\b", re.IGNORECASE),
    re.compile(r"\bCore\s+i[3579]\s*[- ]?\s*\d{4,5}[A-Za-z]*\b", re.IGNORECASE),
    re.compile(r"\bi[3579]\s*[- ]?\s*\d{4,5}[A-Za-z]*\b", re.IGNORECASE),
]
BOARD_PATTERN = re.compile(
    r"\b(?:mobo|motherboard|b450|b550|b650|a520|h610|b660|b760|z690|z790|x570|x670)\b",
    re.IGNORECASE,
)
RAM_PATTERN = re.compile(r"\b(?:ram|memory|ddr[345])\b", re.IGNORECASE)
STORAGE_PATTERN = re.compile(
    r"\b(?:ssd|nvme|hdd|hard\s*disk|harddisk|storage)\b", re.IGNORECASE
)
PSU_PATTERN = re.compile(r"\b(?:psu|power\s+supply)\b", re.IGNORECASE)
CASE_PATTERN = re.compile(r"\b(?:casing|pc\s+case)\b", re.IGNORECASE)
COOLING_PATTERN = re.compile(
    r"\b(?:cooler|heatsink|hsf|aio|water\s*cool(?:ing)?)\b", re.IGNORECASE
)
MONITOR_PATTERN = re.compile(r"\b(?:monitor|lcd|led)\b", re.IGNORECASE)
NONCOMPUTER_PATTERN = re.compile(
    r"\b(?:kamera|camera|canon|sony\s+a\d+|flash(?:sale|kamera)?|"
    r"iphone|ipad|android|handphone|hp\s+android|printer|televisi|tv|"
    r"motor|mobil|sepatu|sandal|parfum|brankas|sofa|kursi|furniture|"
    r"tas|baju|pakaian|helm|perhiasan|stroller|mainan)\b",
    re.IGNORECASE,
)
QUERY_MARKER_PATTERN = re.compile(r"^\s*selesai\s+query\s*:", re.IGNORECASE)


def clean_text(value: str | None) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\ufffd", "").replace("\u00a0", " ")
    value = value.replace("—", " - ").replace("–", " - ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def canonical_title(source_title: str, keyword: str) -> tuple[str, bool]:
    title = clean_text(source_title)
    if QUERY_MARKER_PATTERN.search(title):
        return "", True
    kw = re.escape(clean_text(keyword))
    title = re.sub(rf"^\s*{kw}\s*(?:[-:|]+)\s*", "", title, flags=re.IGNORECASE)
    return title.strip(" -|:"), False


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def parse_price(price_text: str) -> int | None:
    digits = re.sub(r"[^0-9]", "", clean_text(price_text))
    return int(digits) if digits else None


def first_match(patterns: list[re.Pattern[str]], text: str) -> str:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return clean_text(match.group(0))
    return ""


def normalize_model(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"\s+", " ", value)
    return value.upper()


def extract_number_with_unit(pattern: re.Pattern[str], text: str) -> float | None:
    match = pattern.search(text)
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) if match.lastindex and match.lastindex >= 2 else "gb").lower()
    if unit == "tb":
        number *= 1024
    return int(number) if number.is_integer() else number


def extract_specs(text: str) -> dict[str, str | int | float]:
    gpu_model = GPU_MODEL_PATTERN.search(text)
    cpu_model = first_match(CPU_MODEL_PATTERNS, text)

    ram = extract_number_with_unit(
        re.compile(r"\bram\s*[/:-]?\s*(\d{1,3})\s*(?:gb|g)?\b", re.IGNORECASE), text
    )
    if ram is None:
        ram = extract_number_with_unit(
            re.compile(r"\b(\d{1,3})\s*(?:gb|g)\s*(?:ram|memory)\b", re.IGNORECASE), text
        )
    if ram is None:
        ram = extract_number_with_unit(
            re.compile(r"\b(\d{1,3})\s*(?:gb|g)\s*ddr[345]\b", re.IGNORECASE), text
        )

    storage = extract_number_with_unit(
        re.compile(
            r"\b(?:ssd|nvme|hdd|hard\s*disk|harddisk|storage)\s*[/:-]?\s*(\d+(?:\.\d+)?)\s*(tb|gb|g)\b",
            re.IGNORECASE,
        ),
        text,
    )
    if storage is None:
        storage = extract_number_with_unit(
            re.compile(
                r"\b(\d+(?:\.\d+)?)\s*(tb|gb|g)\s*(?:ssd|nvme|hdd|hard\s*disk|harddisk)\b",
                re.IGNORECASE,
            ),
            text,
        )
    if storage is None:
        slash_match = re.search(r"\b\d{1,3}\s*/\s*(\d+(?:\.\d+)?)\s*(tb|gb|g)\b", text, re.IGNORECASE)
        if slash_match:
            storage = float(slash_match.group(1)) * (1024 if slash_match.group(2).lower() == "tb" else 1)
            storage = int(storage) if storage.is_integer() else storage

    screen_match = re.search(
        r"\b(1\d(?:\.\d)?)\s*(?:inch|inci|in)\b|\b(1\d\.\d)\s*[\"”]",
        text,
        re.IGNORECASE,
    )
    screen = next((group for group in screen_match.groups() if group), "") if screen_match else ""

    vram_match = re.search(r"\b(\d{1,2})\s*(?:gb|g)\s*(?:vram|gddr)\b|\bvram\s*(\d{1,2})\s*(?:gb|g)", text, re.IGNORECASE)
    vram = next((group for group in vram_match.groups() if group), "") if vram_match else ""

    return {
        "gpu_model": normalize_model(gpu_model.group(0)) if gpu_model else "",
        "cpu_model": normalize_model(cpu_model),
        "ram_gb": ram if ram is not None else "",
        "storage_gb": storage if storage is not None else "",
        "vram_gb": int(vram) if vram.isdigit() else "",
        "screen_size_in": screen,
    }


def extract_brand(text: str) -> str:
    brands = [
        "ASUS",
        "ACER",
        "LENOVO",
        "HP",
        "DELL",
        "MSI",
        "GIGABYTE",
        "ZOTAC",
        "SAPPHIRE",
        "PALIT",
        "COLORFUL",
        "EVGA",
        "ASROCK",
        "POWERCOLOR",
        "INNO3D",
        "GALAX",
        "AORUS",
        "AXIOO",
        "ADVAN",
        "APPLE",
        "HUAWEI",
        "FUJITSU",
        "TOSHIBA",
        "SONY",
    ]
    for brand in brands:
        if re.search(rf"\b{re.escape(brand)}\b", text, re.IGNORECASE):
            return brand
    return ""


def condition_tags(text: str) -> str:
    tags: list[str] = []
    rules = [
        ("new_or_sealed", r"\b(?:baru|new|segel|sealed)\b"),
        ("used_or_second", r"\b(?:bekas|second|secondhand|used)\b"),
        ("like_new", r"\blike\s+new\b"),
        ("normal_or_smooth", r"\b(?:normal|mulus|istimewa)\b"),
        ("issue_or_defect", r"\b(?:minus|no\s+display|mati|matot|rusak|servis|non\s+display)\b"),
        ("warranty", r"\b(?:garansi|warranty)\b"),
        ("negotiable", r"\b(?:nego|negotiable)\b"),
    ]
    for tag, pattern in rules:
        if re.search(pattern, text, re.IGNORECASE):
            tags.append(tag)
    return ";".join(tags) if tags else "unknown"


def keyword_mismatch(keyword: str, title: str) -> bool:
    if not title:
        return True
    keyword_numbers = re.findall(r"\d{3,5}", keyword)
    title_norm = normalized_key(title)
    if keyword_numbers and any(number in title_norm for number in keyword_numbers):
        return False
    keyword_tokens = [token.lower() for token in re.findall(r"[a-z]+", keyword.lower()) if len(token) > 2]
    return not any(token in title.lower() for token in keyword_tokens)


def classify(keyword: str, source_title: str, description: str) -> dict[str, str]:
    title, query_marker = canonical_title(source_title, keyword)
    text = clean_text(" ".join(part for part in [title, description] if part)).lower()
    laptop_signal = any(re.search(pattern, text, re.IGNORECASE) for pattern in LAPTOP_PATTERNS)
    tuf_mobile_signal = bool(
        re.search(r"\btuf\s+gaming\b", text, re.IGNORECASE)
        and re.search(r"\b\d{3,5}(?:h|hs|hx|u|y)\b", text, re.IGNORECASE)
    )
    laptop_signal = laptop_signal or tuf_mobile_signal
    fullset_signal = any(re.search(pattern, text, re.IGNORECASE) for pattern in FULLSET_PATTERNS)
    gpu_signal = bool(GPU_PATTERN.search(text))
    cpu_signal = bool(CPU_PATTERN.search(text))
    board_signal = bool(BOARD_PATTERN.search(text))
    ram_signal = bool(RAM_PATTERN.search(text))
    storage_signal = bool(STORAGE_PATTERN.search(text))
    psu_signal = bool(PSU_PATTERN.search(text))
    case_signal = bool(CASE_PATTERN.search(text))
    cooling_signal = bool(COOLING_PATTERN.search(text))
    monitor_signal = bool(MONITOR_PATTERN.search(text))
    noncomputer_signal = bool(NONCOMPUTER_PATTERN.search(text))
    specs = extract_specs(text)
    target_is_gpu = bool(re.search(r"\b(?:rtx|gtx|rx|arc)\b", keyword, re.IGNORECASE))
    target_is_cpu = bool(re.search(r"\b(?:ryzen|core|intel)\b", keyword, re.IGNORECASE))

    status = "accepted"
    product_type = ""
    category = ""
    confidence = "high"
    reason = ""

    if query_marker:
        status = "review"
        product_type = "review"
        reason = "query_marker_row"
        confidence = "low"
    elif noncomputer_signal and not (laptop_signal or fullset_signal or gpu_signal or cpu_signal or board_signal or ram_signal or storage_signal):
        status = "excluded"
        product_type = "other"
        reason = "noncomputer_signal"
        confidence = "high"
    elif laptop_signal:
        product_type = "laptop"
        category = "laptop"
        reason = "laptop_signal"
        if noncomputer_signal:
            reason += ";mixed_noncomputer_signal"
            confidence = "medium"
    elif fullset_signal:
        product_type = "pc_fullset"
        category = "pc_fullset"
        reason = "pc_fullset_signal"
        if noncomputer_signal:
            reason += ";mixed_noncomputer_signal"
            confidence = "medium"
    else:
        categories: list[str] = []
        if gpu_signal or target_is_gpu:
            categories.append("gpu")
        if cpu_signal or target_is_cpu:
            categories.append("cpu")
        if board_signal:
            categories.append("motherboard")
        if ram_signal:
            categories.append("ram")
        if storage_signal:
            categories.append("storage")
        if psu_signal:
            categories.append("psu")
        if case_signal:
            categories.append("case")
        if cooling_signal:
            categories.append("cooling")
        if monitor_signal:
            categories.append("monitor")

        if categories:
            product_type = "pc_component"
            category = "bundle" if len(categories) > 1 and re.search(r"\b(?:paket|bundle|combo|plus|\+)\b", text) else categories[0]
            reason = "component_signal:" + ";".join(categories)
            if len(categories) > 1 and category != "bundle":
                reason += ";multi_component"
                confidence = "medium"
            if noncomputer_signal:
                reason += ";mixed_noncomputer_signal"
                confidence = "medium"
        elif target_is_gpu or target_is_cpu:
            product_type = "pc_component"
            category = "gpu" if target_is_gpu else "cpu"
            reason = "keyword_model_fallback"
            confidence = "medium"
        else:
            status = "review"
            product_type = "review"
            reason = "no_computer_signal"
            confidence = "low"

    if status == "accepted" and not title:
        status = "review"
        product_type = "review"
        category = ""
        reason = "empty_canonical_title"
        confidence = "low"

    return {
        "status": status,
        "product_type": product_type,
        "component_category": category,
        "classification_confidence": confidence,
        "classification_reason": reason,
        "canonical_title": title,
        "query_marker": "true" if query_marker else "false",
        "keyword_mismatch": "true" if keyword_mismatch(keyword, title) else "false",
        **{key: str(value) for key, value in specs.items()},
        "condition_tags": condition_tags(text),
        "brand": extract_brand(text),
    }


def make_record(row: dict[str, str], source_file: str, duplicate_keys: Counter[tuple[str, str]]) -> dict[str, str]:
    keyword = clean_text(row.get("keyword"))
    source_title = clean_text(row.get("name"))
    description = clean_text(row.get("description"))
    result = classify(keyword, source_title, description)
    price_text = clean_text(row.get("price_text"))
    price = parse_price(price_text)
    title_key = normalized_key(result["canonical_title"])
    duplicate_key = (title_key, str(price or ""))
    possible_duplicate = bool(title_key and duplicate_keys[duplicate_key] > 1)
    source_url = clean_text(row.get("url"))
    record_id = "FBM-" + hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:12].upper()

    flags: list[str] = []
    if not price_text:
        flags.append("price_missing")
    if result["keyword_mismatch"] == "true":
        flags.append("keyword_mismatch")
    if possible_duplicate:
        flags.append("possible_duplicate_title_price")
    if result["query_marker"] == "true":
        flags.append("query_marker")
    if result["status"] == "review":
        flags.append("manual_review_required")
    if result["status"] == "excluded":
        flags.append("excluded_noncomputer")
    if result["classification_confidence"] == "medium":
        flags.append("medium_confidence")
    if result["classification_reason"].endswith("mixed_noncomputer_signal") or ";mixed_noncomputer_signal" in result["classification_reason"]:
        flags.append("mixed_noncomputer_signal")

    record = {key: "" for key in OUTPUT_COLUMNS}
    record.update(
        {
            "record_id": record_id,
            "status": result["status"],
            "source_file": source_file,
            "source_site": clean_text(row.get("site")),
            "search_keyword": keyword,
            "canonical_title": result["canonical_title"],
            "source_title": source_title,
            "description": description,
            "product_type": result["product_type"],
            "component_category": result["component_category"],
            "classification_confidence": result["classification_confidence"],
            "classification_reason": result["classification_reason"],
            "condition_tags": result["condition_tags"],
            "brand": result["brand"],
            "gpu_model": result["gpu_model"],
            "cpu_model": result["cpu_model"],
            "ram_gb": result["ram_gb"],
            "storage_gb": result["storage_gb"],
            "vram_gb": result["vram_gb"],
            "screen_size_in": result["screen_size_in"],
            "price_rp": price if price is not None else "",
            "price_text_raw": price_text,
            "price_missing": "true" if price is None else "false",
            "keyword_mismatch": result["keyword_mismatch"],
            "possible_duplicate_title_price": "true" if possible_duplicate else "false",
            "quality_flags": ";".join(flags),
            "source_url": source_url,
            "scraped_at": clean_text(row.get("scraped_at")),
        }
    )
    return record


def read_marketplace(source_path: Path) -> list[dict[str, str]]:
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_feed_summary(source_path: Path) -> dict[str, str]:
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    row = rows[1] if len(rows) > 1 else []
    fields = {
        "source_file": source_path.name,
        "source_site": row[0] if len(row) > 0 else "",
        "feed_keyword": row[1] if len(row) > 1 else "",
        "summary_text": clean_text(row[2]) if len(row) > 2 else "",
        "scan_stats_raw": clean_text(row[9]) if len(row) > 9 else "",
        "source_url": row[10] if len(row) > 10 else "",
        "scraped_at": row[13] if len(row) > 13 else "",
        "header_columns": "1",
        "row_columns": str(len(row)),
        "format_issue": "header_mismatch" if len(row) != 1 else "none",
    }
    stat_labels = {"scanned_posts": "discan", "questions": "pertanyaan", "questions_pc": "pertanyaan_pc"}
    for key, label in stat_labels.items():
        match = re.search(rf"{label}\s*=\s*(\d+)", fields["scan_stats_raw"], re.IGNORECASE)
        fields[key] = match.group(1) if match else ""
    return fields


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_summary(records: list[dict[str, str]], feed_summary: dict[str, str], source_rows: int) -> list[dict[str, str]]:
    counts = Counter(record["status"] for record in records)
    by_type = Counter(record["product_type"] for record in records if record["status"] == "accepted")
    by_category = Counter(record["component_category"] for record in records if record["status"] == "accepted")
    metrics = [
        ("source_marketplace_rows", str(source_rows), "Baris data dari file Marketplace mentah"),
        ("accepted_rows", str(counts["accepted"]), "Baris yang lolos klasifikasi otomatis"),
        ("review_rows", str(counts["review"]), "Baris yang perlu pemeriksaan manual"),
        ("excluded_rows", str(counts["excluded"]), "Baris yang terindikasi bukan hardware PC/laptop"),
        ("laptop_rows", str(by_type["laptop"]), "Dataset laptop"),
        ("pc_component_rows", str(by_type["pc_component"]), "Dataset komponen PC"),
        ("pc_fullset_rows", str(by_type["pc_fullset"]), "PC rakitan/fullset dipisahkan dari komponen"),
        ("price_missing_rows", str(sum(record["price_missing"] == "true" for record in records)), "Harga tidak tersedia di sumber"),
        ("keyword_mismatch_rows", str(sum(record["keyword_mismatch"] == "true" for record in records)), "Judul tidak memuat nomor model keyword pencarian"),
        ("possible_duplicate_rows", str(sum(record["possible_duplicate_title_price"] == "true" for record in records)), "Judul normalisasi + harga sama; tidak dihapus, hanya ditandai"),
        ("feed_scanned_posts", feed_summary.get("scanned_posts", ""), "Ringkasan dari file feed yang formatnya tidak konsisten"),
        ("feed_questions", feed_summary.get("questions", ""), "Pertanyaan yang terdeteksi pada feed"),
    ]
    for category, count in sorted(by_category.items()):
        metrics.append((f"accepted_category_{category}", str(count), "Kategori turunan pada listing accepted"))
    return [{"metric": metric, "value": value, "notes": notes} for metric, value, notes in metrics]


def build_dictionary() -> list[dict[str, str]]:
    definitions = {
        "record_id": ("ID stabil dari URL sumber", "text"),
        "status": ("Status pemrosesan", "accepted | review | excluded"),
        "source_file": ("Nama file sumber", "text"),
        "source_site": ("Situs asal", "text"),
        "search_keyword": ("Keyword yang dipakai crawler; bukan jaminan isi listing", "text"),
        "canonical_title": ("Judul yang sudah dibersihkan dari prefix keyword", "text"),
        "source_title": ("Judul mentah dari sumber", "text"),
        "description": ("Deskripsi listing", "text"),
        "product_type": ("Pemisahan utama dataset", "laptop | pc_component | pc_fullset | review | other"),
        "component_category": ("Kategori komponen", "gpu | cpu | motherboard | ram | storage | psu | case | cooling | monitor | bundle"),
        "classification_confidence": ("Keyakinan heuristik klasifikasi", "high | medium | low"),
        "classification_reason": ("Sinyal yang dipakai untuk klasifikasi", "text"),
        "condition_tags": ("Tag kondisi yang terbaca dari judul/deskripsi", "semicolon-separated"),
        "brand": ("Brand yang terbaca", "text"),
        "gpu_model": ("Model GPU yang terbaca", "text"),
        "cpu_model": ("Model CPU yang terbaca", "text"),
        "ram_gb": ("Kapasitas RAM dalam GB bila terbaca", "number"),
        "storage_gb": ("Kapasitas penyimpanan dalam GB bila terbaca", "number"),
        "vram_gb": ("VRAM dalam GB bila terbaca", "number"),
        "screen_size_in": ("Ukuran layar dalam inci bila terbaca", "number"),
        "price_rp": ("Harga numerik dalam rupiah", "number"),
        "price_text_raw": ("Harga mentah", "text"),
        "price_missing": ("Flag harga kosong", "true | false"),
        "keyword_mismatch": ("Flag keyword pencarian tidak cocok dengan judul", "true | false"),
        "possible_duplicate_title_price": ("Flag judul normalisasi + harga berulang", "true | false"),
        "quality_flags": ("Flag kualitas yang digabung dengan titik koma", "semicolon-separated"),
        "source_url": ("URL listing asli", "url"),
        "scraped_at": ("Waktu scraping", "ISO-8601 text"),
    }
    return [
        {"column": column, "description": description, "type_or_values": type_or_values}
        for column, (description, type_or_values) in definitions.items()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean and split used PC/laptop listings.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    marketplace_files = sorted(args.input_dir.glob("facebook_marketplace_*.csv"))
    feed_files = sorted(args.input_dir.glob("facebook_feed_*.csv"))
    if not marketplace_files:
        raise SystemExit("No facebook_marketplace_*.csv file found")

    source_path = marketplace_files[-1]
    raw_rows = read_marketplace(source_path)
    duplicate_keys = Counter()
    for row in raw_rows:
        title, _ = canonical_title(row.get("name", ""), row.get("keyword", ""))
        duplicate_keys[(normalized_key(title), str(parse_price(row.get("price_text", "")) or ""))] += 1

    records = [make_record(row, source_path.name, duplicate_keys) for row in raw_rows]
    feed_summary = read_feed_summary(feed_files[-1]) if feed_files else {
        "source_file": "",
        "format_issue": "missing",
        "scanned_posts": "",
        "questions": "",
        "questions_pc": "",
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "semua_listing_terklasifikasi.csv", records, OUTPUT_COLUMNS)
    write_csv(args.output_dir / "laptop.csv", [record for record in records if record["status"] == "accepted" and record["product_type"] == "laptop"], OUTPUT_COLUMNS)
    write_csv(args.output_dir / "komponen_pc.csv", [record for record in records if record["status"] == "accepted" and record["product_type"] == "pc_component"], OUTPUT_COLUMNS)
    write_csv(args.output_dir / "pc_fullset.csv", [record for record in records if record["status"] == "accepted" and record["product_type"] == "pc_fullset"], OUTPUT_COLUMNS)
    write_csv(args.output_dir / "perlu_review.csv", [record for record in records if record["status"] == "review"], OUTPUT_COLUMNS)
    write_csv(args.output_dir / "excluded_non_hardware.csv", [record for record in records if record["status"] == "excluded"], OUTPUT_COLUMNS)
    write_csv(args.output_dir / "duplikat_potensial.csv", [record for record in records if record["possible_duplicate_title_price"] == "true"], OUTPUT_COLUMNS)
    write_csv(args.output_dir / "feed_summary.csv", [feed_summary], list(feed_summary.keys()))
    write_csv(args.output_dir / "summary.csv", build_summary(records, feed_summary, len(raw_rows)), ["metric", "value", "notes"])
    write_csv(args.output_dir / "data_dictionary.csv", build_dictionary(), ["column", "description", "type_or_values"])

    readme = f"""# Dataset hardware bekas hasil olahan

Sumber utama: `{source_path.name}` ({len(raw_rows):,} baris).

File keluaran utama:

- `laptop.csv`: listing laptop yang terdeteksi.
- `komponen_pc.csv`: komponen PC seperti GPU, CPU, motherboard, RAM, storage, PSU, dan bundle.
- `pc_fullset.csv`: PC rakitan/desktop/fullset; sengaja dipisahkan dari komponen.
- `perlu_review.csv`: baris query marker atau sinyal klasifikasi yang belum cukup kuat.
- `excluded_non_hardware.csv`: baris yang terindikasi bukan hardware PC/laptop.
- `semua_listing_terklasifikasi.csv`: seluruh baris sumber dengan status klasifikasi.
- `duplikat_potensial.csv`: judul normalisasi + harga yang berulang; tidak dihapus otomatis.
- `summary.csv`, `data_dictionary.csv`, `feed_summary.csv`: ringkasan, kamus kolom, dan audit file feed.

Catatan kualitas:

- `search_keyword` adalah keyword crawler dan sering tidak cocok dengan barang pada judul; gunakan `keyword_mismatch` sebagai filter kualitas.
- Harga diambil dari `price_text` dan dikonversi ke `price_rp`; baris sumber tanpa harga ditandai `price_missing=true`.
- URL dipakai untuk membuat `record_id`. Tidak ada URL duplikat yang dibuang pada sumber ini.
- Klasifikasi berbasis heuristik judul/deskripsi; baris `review` perlu cek manual sebelum dipakai sebagai ground truth.
- File `facebook_feed_*.csv` bukan tabel listing yang valid karena header-nya hanya satu kolom; isinya disimpan sebagai `feed_summary.csv`.
"""
    (args.output_dir / "README.md").write_text(readme, encoding="utf-8")

    print(f"source_rows={len(raw_rows)}")
    print("status_counts=" + str(Counter(record["status"] for record in records)))
    print("product_type_counts=" + str(Counter(record["product_type"] for record in records if record["status"] == "accepted")))
    print("output_dir=" + str(args.output_dir))


if __name__ == "__main__":
    main()
