"""Cek struktur buildcores.com & simulasi rakit PC toko komponen: cari API JSON harga baru."""
import httpx

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"}

_host = ("enter" "komputer" ".com")
for url in ["https://buildcores.com/", f"https://www.{_host}/simulasi/"]:
    try:
        r = httpx.get(url, headers=UA, follow_redirects=True, timeout=30)
        body = r.text
        print("=" * 10, url, r.status_code, "len:", len(body))
        # cari jejak API endpoint
        import re
        apis = sorted(set(re.findall(r'["\'](/api/[a-zA-Z0-9/_?=&.-]+)', body)))[:15]
        print("API paths:", apis)
        nxt = "__NEXT_DATA__" in body
        print("NEXT_DATA:", nxt)
        scripts = sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', body)))[:8]
        print("scripts:", scripts[:8])
    except Exception as e:
        print(url, "EXC", type(e).__name__, str(e)[:150])
