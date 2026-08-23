"""Probe 4: buildcores — struktur URL produk + apakah harga ke-render SSR."""
import httpx, re, json

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"}
c = httpx.Client(headers=UA, follow_redirects=True, timeout=60)

r = c.get("https://www.buildcores.com/sitemap.xml")
urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
print("total:", len(urls))
print("contoh URL produk:", urls[1], "|", urls[30000])

# ambil 1 URL produk, cek harga di HTML
prod_url = urls[1]
r2 = c.get(prod_url)
body = r2.text
print("\nproduk:", prod_url, r2.status_code, "len:", len(body))
prices = sorted(set(re.findall(r"\$([0-9][0-9,.]{1,9})", body)))[:15]
print("harga di HTML:", prices)
# retailer
for kw in ["amazon", "newegg", "bestbuy", "walmart", "ebay", "memoryc"]:
    n = len(re.findall(kw, body, re.I))
    if n:
        print(f"mention {kw}: {n}")
# RSC payload: cari 'price' di stream
m = re.findall(r'"price[^"]*":"?([0-9][0-9,.]*)"?', body)[:10]
print("price di RSC payload:", m)
# cek /api path yang disebut di homepage
r3 = c.get("https://www.buildcores.com/api")
print("\n/api:", r3.status_code, r3.headers.get("content-type", "")[:30], len(r3.text))
print(r3.text[:300] if len(r3.text) < 2000 else r3.text[:300])
