"""Probe 3: sitemap buildcores (6.3MB!) — struktur URL katalog per komponen."""
import httpx, re
from collections import Counter

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"}
r = httpx.get("https://www.buildcores.com/sitemap.xml", headers=UA, follow_redirects=True, timeout=60)
urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
print("total URL di sitemap:", len(urls))

# pola path level-1
lvl1 = Counter(u.replace("https://www.buildcores.com", "").split("/")[1] for u in urls if u.count("/") >= 3)
print("level-1:", lvl1.most_common(15))

# contoh URL CPU & GPU
cpu = [u for u in urls if "/cpu/" in u][:5]
gpu = [u for u in urls if "/gpu/" in u][:5]
print("\ncontoh cpu:", *cpu, sep="\n  ")
print("\ncontoh gpu:", *gpu, sep="\n  ")

# fetch satu halaman produk — apakah harga ke-render server-side?
if cpu:
    prod = cpu[0]
    r2 = httpx.get(prod, headers=UA, follow_redirects=True, timeout=30)
    body = r2.text
    print("\nproduk:", prod)
    print("status:", r2.status_code, "len:", len(body))
    prices = sorted(set(re.findall(r"\$\s?([\d,]+\.?\d*)", body)))[:12]
    print("harga USD muncul di HTML:", prices)
    # retailer names?
    for kw in ["amazon", "newegg", "bestbuy", "walmart", "ebay"]:
        n = len(re.findall(kw, body, re.I))
        if n:
            print(f"mention {kw}: {n}")
