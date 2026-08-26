"""Self-check identitas model: query bebas ("RTX 4060 8GB") tidak boleh
dibandingkan dengan varian lain ("RTX 4060 Ti", "5600X" vs "5600").
Run: python -m tests.test_model_identity"""
from app.services.analysis import _model_tokens

REJECT = [
    # (query, judul, component_type) — token model beda = HARUS gugur
    ("RTX 4060 8GB", "VGA MSI GeForce RTX 4060 Ti VENTUS 2X BLACK OC 8GB GDDR6", "gpu"),
    ("RTX 4060", "VGA Zotac RTX 4060 Ti Twin Edge 8GB", "gpu"),
    ("Ryzen 5 5600", "AMD Ryzen 5 5600X tray", "cpu"),
    ("RX 6600", "SAPPHIRE PULSE RX 6600 XT 8GB", "gpu"),
    ("RAM DDR4 16GB", "MEMORY RAM DDR5 ACER PREDATOR DDR5 32GB", "ram"),
    ("SSD NVMe 1TB", "SSD SATA 480GB Kingston A400", "storage"),
    # Mobo: chipset beda = produk beda (Intel vs AMD, generasi beda)
    ("Motherboard B650", "GIGABYTE B760M AORUS ELITE WIFI6E GEN5 DDR5", "motherboard"),
    ("Motherboard B760", "ASUS TUF GAMING B650EM-E WIFI AM5 DDR5", "motherboard"),
]
ACCEPT = [
    ("RTX 4060 8GB", "VGA GALAX GeForce RTX 4060 EX White 1-Click OC 8GB GDDR6", "gpu"),
    ("RTX 4060 Ti", "MSI RTX 4060 Ti VENTUS 2X BLACK OC 16GB", "gpu"),
    ("RX 6600", "Vga Rx 6600 Gigabyte 8Gb Ddr5 Bekas Normal", "gpu"),
    ("Ryzen 5 5600X", "AMD Ryzen 5 5600X box garansi", "cpu"),
    ("Core i5 12400F", "Intel Core i5-12400F tray murah", "cpu"),
    ("SSD NVMe 1TB", "SSD NVMe 1TB Samsung 980 M.2 2280", "storage"),
    ("Motherboard B650", "GIGABYTE B650M AORUS ELITE AX (Socket AM5, B650)", "motherboard"),
    ("B650M", "MSI PRO B650M-B (AM5, AMD B650, DDR5)", "motherboard"),
]

fails = []
for q, title, ct in REJECT:
    req = _model_tokens(q, ct)
    if req and _model_tokens(title, ct) == req:
        fails.append(f"HARUS DITOLAK : {q!r} vs {title!r}")
for q, title, ct in ACCEPT:
    req = _model_tokens(q, ct)
    if not req or _model_tokens(title, ct) != req:
        fails.append(f"HARUS DITERIMA: {q!r} vs {title!r}")

if fails:
    print("FAIL:", len(fails))
    for f in fails:
        print(" ", f)
    raise SystemExit(1)
print(f"OK: {len(REJECT)} reject + {len(ACCEPT)} accept lolos")
