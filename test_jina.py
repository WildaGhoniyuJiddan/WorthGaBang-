"""
Test 4: Jina AI Reader (r.jina.ai) — proxy rendering gratis.
Test ke tokopedia search & shopee search.
"""
import requests

UA = {"User-Agent": "Mozilla/5.0"}

targets = {
    "tokped": "https://r.jina.ai/https://www.tokopedia.com/search?st=product&q=rtx+3060",
    "shopee": "https://r.jina.ai/https://shopee.co.id/search?keyword=rtx+3060",
}

for name, url in targets.items():
    try:
        r = requests.get(url, headers=UA, timeout=90)
        print(f"=== {name}: {r.status_code} len={len(r.text)}")
        print(r.text[:600])
        print("...")
        if r.status_code == 200:
            with open(f"jina_{name}.md", "w", encoding="utf-8") as f:
                f.write(r.text)
            print(f"saved jina_{name}.md")
    except Exception as e:
        print(f"{name}: FAIL {str(e)[:150]}")
