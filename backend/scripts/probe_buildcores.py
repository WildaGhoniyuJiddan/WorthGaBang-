"""Probe buildcores lebih dalam: robots, sitemap, RSC payload, repo GitHub."""
import httpx, re

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"}
c = httpx.Client(headers=UA, follow_redirects=True, timeout=30)

for path in ["/robots.txt", "/sitemap.xml"]:
    r = c.get("https://buildcores.com" + path)
    print(path, r.status_code, len(r.text))
    if r.status_code == 200 and len(r.text) < 3000:
        print(r.text[:800])

# halaman browse CPU — cari pola data
r = c.get("https://buildcores.com/browse/cpu")
print("\n/browse/cpu:", r.status_code, len(r.text))
body = r.text
# Next App Router: payload ada di self.__next_f.push — cari nama endpoint/route di dalamnya
chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', body)[:5]
joined = "".join(chunks)[:1500]
print("RSC sample:", joined[:600].replace("\\n", "\n"))
# cari kata 'trpc' / 'api' / fetch URL
print("\ntrpc mentions:", len(re.findall(r"trpc", body)))
print("api urls:", sorted(set(re.findall(r'["\']((?:https?://|/)[^"\']{0,80}api[^"\']{0,80})["\']', body)))[:10])
