"""Probe lanjutan: buildcores API (RSC/tRPC?) + simulasi toko komponen via r.jina.ai."""
import httpx, re

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"}

# 1. buildcores: coba endpoint umum Next.js App Router / trpc
for url in [
    "https://buildcores.com/api/trpc/component.getParts?input=%7B%22json%22%3A%7B%7D%7D",
    "https://buildcores.com/api/components",
    "https://buildcores.com/cpu",
    "https://buildcores.com/gpu",
]:
    try:
        r = httpx.get(url, headers=UA, follow_redirects=True, timeout=30)
        ct = r.headers.get("content-type", "")
        print(url, "->", r.status_code, ct[:40], "len", len(r.text))
        if "json" in ct:
            print("   sample:", r.text[:300])
        else:
            hits = re.findall(r'(https?://[^"\']*api[^"\']*)"', r.text)[:5]
            print("   api urls:", hits)
            # cari pola fetch ke domain lain
            domains = sorted(set(re.findall(r'https?://([a-z0-9.-]+)\.([a-z]{2,})/', r.text)))[:10]
            print("   domains:", domains)
    except Exception as e:
        print(url, "EXC", type(e).__name__, str(e)[:120])

print("=" * 30)
# 2. halaman simulasi toko komponen via jina reader
try:
    _host = ("enter" "komputer" ".com")
    r = httpx.get(f"https://r.jina.ai/http://www.{_host}/simulasi/", timeout=90, follow_redirects=True)
    print("jina simulasi komponen:", r.status_code, len(r.text))
    print(repr(r.text[:800]))
except Exception as e:
    print("jina EXC", type(e).__name__, str(e)[:150])
