# ponytail: recon tool sekali-pakai untuk reverse-engineer API simulasi rakit PC di toko komponen.
# Naikkan WAIT_S / tambah langkah interaksi kalau mau capture lebih dalam.
"""CDP recon: buka halaman di Brave (debug profile), rekam XHR/fetch + body."""
import asyncio, json, os, subprocess, time, urllib.request
import websockets

BRAVE = os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe")
PROFILE = r"D:\Projek\WorL\backend\data\profil_browser_recon"
PORT = 9222
_host = ("enter" "komputer" ".com")
TARGET = os.environ.get("RETAIL_URL", f"https://www.{_host}/simulasi/")
WAIT_S = int(os.environ.get("EK_WAIT", "45"))
OUT = r"D:\Projek\WorL\backend\data\rekam_api_hasil.json"

def dev(path):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=5) as r:
        return json.loads(r.read())

def ensure_browser():
    try:
        dev("/json/version")
        return None  # already running with our port
    except Exception:
        pass
    return subprocess.Popen([
        BRAVE, f"--remote-debugging-port={PORT}", f"--user-data-dir={PROFILE}",
        "--no-first-run", "--no-default-browser-check", "--window-size=1400,900",
        "about:blank",
    ])

async def main():
    proc = ensure_browser()
    if proc:
        for _ in range(60):
            try:
                dev("/json/version"); break
            except Exception:
                time.sleep(0.5)
        else:
            raise SystemExit("devtools port never opened")
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?about:blank", method="PUT")
    tab = json.loads(urllib.request.urlopen(req, timeout=10).read())
    print("TAB:", tab["id"])

    seen_reqs = {}     # requestId -> {url, method, postData}
    xhr = {}           # requestId -> {url, status, mimeType, resourceType}
    bodies = {}        # requestId -> body text
    titles = []

    async with websockets.connect(tab["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024) as ws:
        mid = 0
        async def call(method, params=None):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            return mid

        for m in ("Page.enable", "Network.enable", "Runtime.enable"):
            await call(m)

        await call("Page.navigate", {"url": TARGET})
        deadline = time.time() + WAIT_S
        last_title_check = 0
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                if time.time() - last_title_check > 6:
                    last_title_check = time.time()
                    q = mid + 1000  # fire-and-forget eval ids
                    mid = q
                    await ws.send(json.dumps({"id": q, "method": "Runtime.evaluate",
                        "params": {"expression": "document.title+'|'+location.href", "returnByValue": True}}))
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            meth = msg.get("method", "")
            p = msg.get("params", {})
            if meth == "Network.requestWillBeSent":
                r = p["request"]
                seen_reqs[p["requestId"]] = {"url": r["url"], "method": r.get("method"),
                                             "postData": r.get("postData")}
            elif meth == "Network.responseReceived":
                resp = p["response"]
                xhr[p["requestId"]] = {
                    "url": resp["url"], "status": resp.get("status"),
                    "mime": resp.get("mimeType"), "type": p.get("type"),
                }
            elif meth == "Runtime.evaluate":
                val = msg.get("result", {}).get("result", {}).get("value")
                if val:
                    titles.append(val)
                    print("PAGE:", val)
            elif meth == "Network.loadingFailed":
                e = p.get("errorText", "")
                if "ERR_BLOCKED_BY_CLIENT" in e or "ERR_FAILED" in e:
                    print("LOADFAIL:", seen_reqs.get(p.get("requestId"), {}).get("url"), e)

        # fetch bodies for XHR/Fetch responses
        for rid, info in xhr.items():
            if info["type"] not in ("XHR", "Fetch"):
                continue
            try:
                await ws.send(json.dumps({"id": 500000 + len(bodies), "method": "Network.getResponseBody",
                                          "params": {"requestId": rid}}))
                # read until we get this id back
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    m = json.loads(raw)
                    if m.get("id") == 500000 + len(bodies):
                        res = m.get("result", {})
                        if "body" in res:
                            bodies[rid] = res["body"][:200000]
                        break
            except Exception as e:
                print("BODYFAIL:", info["url"][:120], str(e)[:80])

    out = {
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "page_titles": titles,
        "xhr": xhr,
        "all_requests": {k: v for k, v in seen_reqs.items()},
        "bodies": bodies,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\n=== XHR/FETCH responses ===")
    for rid, i in xhr.items():
        mark = "HAS-BODY" if rid in bodies else ""
        if i["type"] in ("XHR", "Fetch") or "json" in (i["mime"] or ""):
            print(f'{i["status"]} {i["type"]} {i["url"][:150]} {mark}')
    print(f"\nDump: {OUT} ({len(xhr)} responses, {len(bodies)} bodies)")
    # keep browser alive briefly so challenge cookie jar persists? no—leave running.
    if proc:
        pass  # leave Brave running for follow-up phases

asyncio.run(main())
