"""Parse jina_tokped.md — ekstrak nama + harga produk."""
import re
import json

with open("jina_tokped.md", encoding="utf-8") as f:
    md = f.read()

# pola: [![...](img)] URL-produk NAMA RpHARGA ...
pattern = re.compile(
    r'\[!\[[^\]]*\]\([^)]*\)\]\s*(https://www\.tokopedia\.com/[^\s\]]+)\s*\n?\s*([^\[\n]+?)\s+Rp([\d.,]+)',
    re.S,
)
rows = []
seen = set()
for m in pattern.finditer(md):
    url, name, price = m.group(1), m.group(2).strip(), m.group(3)
    if url in seen:
        continue
    seen.add(url)
    rows.append({
        "name": name[:120],
        "price_rp": int(price.replace(".", "").replace(",", "")),
        "url": url,
    })

print("products parsed:", len(rows))
for r in rows:
    print(f"- Rp{r['price_rp']:>12,} | {r['name'][:70]}")

with open("tokped_jina_products.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)
print("saved tokped_jina_products.json")
