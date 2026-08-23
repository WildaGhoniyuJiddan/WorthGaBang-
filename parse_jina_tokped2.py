"""Parse jina_tokped.md v2 — struktur: [![img](imgurl) NAMA RpHARGA ... SHOP](product-url)"""
import re
import json

with open("jina_tokped.md", encoding="utf-8") as f:
    md = f.read()

rows = []
seen = set()

# tiap blok produk diawali [![Image N: product-image]
blocks = re.split(r'\[!\[Image \d+: product-image\]', md)
for block in blocks[1:]:
    # product URL ada di akhir blok: ](https://www.tokopedia.com/...)
    m_url = re.search(r'\]\((https://www\.tokopedia\.com/[^)\s]+)\)', block)
    if not m_url:
        continue
    url = m_url.group(1)
    # ambil teks sebelum ]( — buang image markdown, rating img, shop badge img
    text = m_url.string[m_url.start(0):]  # tak terpakai; pakai pendekatan lain
    # teks produk = antara akhir img-url paren pertama dan Rp
    m_txt = re.match(r'[^)]*\)\s*(.*?)\s*Rp([\d.,]+)', block, re.S)
    if not m_txt:
        continue
    name_raw = m_txt.group(1)
    price = m_txt.group(2)
    # bersihkan sisa markdown image dalam nama
    name = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', name_raw)
    name = re.sub(r'\s+', ' ', name).strip()
    if url in seen or not name:
        continue
    seen.add(url)
    rows.append({
        "name": name[:140],
        "price_rp": int(price.replace(".", "").replace(",", "")),
        "url": url[:160],
    })

print("products parsed:", len(rows))
for r in rows:
    print(f"Rp{r['price_rp']:>12,} | {r['name'][:75]}")

with open("tokped_jina_products.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)
print("saved tokped_jina_products.json")
