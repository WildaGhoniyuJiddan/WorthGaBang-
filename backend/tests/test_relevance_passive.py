"""Self-check relevance pasif sections: RAM/storage/motherboard tidak boleh
dapat pembanding dari judul VGA/CPU/laptop/build. Run: python -m tests.test_relevance_passive"""
from app.services.relevance import is_relevant_pc_listing as rel

RAM_Q = "RAM DDR4 16GB"
SSD_Q = "SSD NVMe 1TB"
HDD_Q = "HDD 2TB"
MOBO_Q = "Motherboard B650"

MUST_REJECT = [
    # (query, title) — semua ini HARUS ditolak
    (RAM_Q, "SAPPHIRE PULSE AMD Radeon RX 9070 XT 16GB DDR6 GPU"),
    (RAM_Q, "Terlaris ASUS TUF GAMING RX 6950 XT OC 16GB DDR6 256BIT RADEON VGA"),
    (RAM_Q, "ASRock Deskmeet MINI X600 AMD Ryzen 5 7600 + RAM 16GB DDR5 + SSD 512GB"),
    (RAM_Q, "ADVAN Workpro Lite Intel Core i3 1215U RAM32GB SSD1TB 14 FHD WIN11"),
    (RAM_Q, "External GPU (eGPU) Gaming Box Thunderbolt + VGA AMD RADEON RX 9060 XT"),
    (SSD_Q, "PC BUILD AMD RYZEN 7 8700F - 32GB DDR5 - SSD 1TB NVME - VGA RTX 4060 TI"),
    (SSD_Q, "ASUS D500SD Core i7 12700 1TB HDD + 256GB SSD 8GB DDR4 Desktop PC"),
    (HDD_Q, "ASUS D500SD 781200033W Core i7 12700 1TB HDD + 256GB SSD 8GB DDR4"),
    (MOBO_Q, "Terlaris! New! AMD Ryzen 7 7700 R7 7700 CPU + MSI B650M GAMING WIFI Motherboard"),
    (MOBO_Q, "PC GAMING AMD Ryzen 7 9700X + B650E + RAM 32GB + SSD 1TB + RTX 4060 TI OC"),
    # RAM beda gen/kapasitas juga harus gugur
    (RAM_Q, "MEMORY RAM DDR5 ACER PREDATOR VESTA II RGB DDR5 32GB (2x16GB) 6000Mhz"),
]

MUST_ACCEPT = [
    (RAM_Q, "RAM DDR4 16GB Kingston Fury Beast 3200MHz"),
    (RAM_Q, "Memory RAM DDR4 16GB (2x8GB) Corsair Vengeance LPX second mulus"),
    (SSD_Q, "SSD NVMe 1TB Samsung 980 M.2 2280 PCIe 3.0"),
    (HDD_Q, "HDD 2TB WD Purple bekas 90% sehat"),
    (MOBO_Q, "Motherboard B650 AM5 DDR5 second fullset"),  # 'fullset' = kelengkapan dus
    (MOBO_Q, "GIGABYTE B650M AORUS ELITE AX Socket AM5"),
]

fails = []
for q, title in MUST_REJECT:
    if rel(q, title, None):
        fails.append(f"HARUS DITOLAK : {q!r} vs {title!r}")
for q, title in MUST_ACCEPT:
    if not rel(q, title, None):
        fails.append(f"HARUS DITERIMA: {q!r} vs {title!r}")

if fails:
    print("FAIL:", len(fails))
    for f in fails:
        print(" ", f)
    raise SystemExit(1)
print(f"OK: {len(MUST_REJECT)} reject + {len(MUST_ACCEPT)} accept semua lolos")
