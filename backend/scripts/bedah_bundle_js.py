# ponytail: fase-2 recon — inject recorder + grep bundle JS utk peta API jeanne.
"""Attach ke tab toko komponen yang masih hidup, pasang hook fetch/XHR,
bedah semua <script> src cari 'jeanne', 'signature', 'MSTGE', CryptoJS."""
import asyncio, json, os, re, time, urllib.request
import websockets

PORT = 9222
OUT = r"D:\Projek\WorL\backend\data\bedah_bundle_js_hasil.json"

def dev(path):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=5) as r:
        return json.loads(r.read())

async def main():
    tabs = dev("/json")
    _host = ("enter" "komputer" ".com")
    tab = next((t for t in tabs if _host in t.get("url", "") and t["type"] == "page"), None)
    if not tab:
        raise SystemExit(f"no target tab: {[t['url'] for t in tabs]}")
    print("TAB:", tab["url"])

    async with websockets.connect(tab["webSocketDebuggerUrl"], max_size=256 * 1024 * 1024) as ws:
        mid = 0
        pending = {}
        async def call(method, params=None):
            nonlocal mid
            mid += 1
            myid = mid
            await ws.send(json.dumps({"id": myid, "method": method, "params": params or {}}))
            pending[myid] = asyncio.get_event_loop().create_future()
            return await pending[myid]

        async def reader():
            while True:
                raw = await ws.recv()
                m = json.loads(raw)
                if isinstance(m.get("id"), int) and m["id"] in pending:
                    fut = pending.pop(m["id"])
                    if not fut.done():
                        fut.set_result(m.get("result", {}))

        rt = asyncio.ensure_future(reader())

        async def ev(expr):
            r = await call("Runtime.evaluate",
                           {"expression": expr, "returnByValue": True, "awaitPromise": True})
            return r.get("result", {}).get("value")

        # 1) pasang recorder fetch/XHR untuk call berikutnya
        await ev("""
(() => {
  window.__cap = [];
  const of = window.fetch;
  window.fetch = async function(...a) {
    const res = await of.apply(this, a);
    try {
      const url = typeof a[0] === 'string' ? a[0] : a[0].url;
      const body = a[1] && a[1].body ? String(a[1].body) : null;
      const clone = res.clone();
      const text = await clone.text();
      window.__cap.push({kind:'fetch', url, method:(a[1]&&a[1].method)||'GET', reqBody:body, status:res.status, resp:text.slice(0,200000)});
    } catch(e){}
    return res;
  };
  const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m,u){ this.__m=m; this.__u=u; return oo.apply(this,arguments); };
  XMLHttpRequest.prototype.send = function(b){
    this.addEventListener('load', () => {
      try { window.__cap.push({kind:'xhr', url:this.__u, method:this.__m, reqBody:b?String(b):null, status:this.status, resp:String(this.responseText).slice(0,200000)}); } catch(e){}
    });
    return os.apply(this,arguments);
  };
  return 'recorder-on';
})()
""")

        # 2) kumpulkan URL semua script eksternal + inline
        scripts = await ev("""
(() => Array.from(document.querySelectorAll('script')).map(s => s.src || ('INLINE:'+s.textContent.length)).slice(0,60))()
""")
        print("SCRIPTS:", json.dumps(scripts, indent=1)[:1500])

        # 3) fetch tiap bundle JS di dalam page, grep pola menarik
        grab = await ev("""
(async () => {
  const out = [];
  for (const s of document.querySelectorAll('script[src]')) {
    try {
      const t = await (await fetch(s.src)).text();
      const hits = [];
      for (const pat of ['jeanne', 'signature', 'MSTGE', 'RSTGE', 'CryptoJS', 'AES.encrypt', 'MD5', 'assembled']) {
        let idx = 0, count = 0;
        while ((idx = t.indexOf(pat, idx)) !== -1 && count < 3) {
          hits.push({pat, ctx: t.slice(Math.max(0, idx-120), idx+180)});
          idx += pat.length; count++;
        }
      }
      if (hits.length) out.push({src: s.src, size: t.length, hits});
    } catch(e) { out.push({src: s.src, err: String(e)}); }
  }
  return out;
})()
""")
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump({"scripts": scripts, "grep": grab}, f, ensure_ascii=False, indent=1)

        # ringkas hasil grep
        for b in (grab or []):
            if "err" in b:
                print("ERR", b["src"][:100], b["err"]); continue
            print(f"\n=== {b['src'][:110]} ({b['size']}b)")
            seen = set()
            for h in b["hits"]:
                key = h["pat"]
                print(f"--[{h['pat']}] {h['ctx'][:260]}")

        # 4) inventaris elemen UI interaktif
        inv = await ev("""
(() => {
  const txt = e => (e.innerText||e.value||e.getAttribute('placeholder')||'').trim().slice(0,60);
  const vis = e => e.offsetParent !== null;
  return {
    buttons: Array.from(document.querySelectorAll('button,[role=button],.btn')).filter(vis).map(txt).slice(0,40),
    selects: Array.from(document.querySelectorAll('select')).filter(vis).map(s => ({name:s.name,id:s.id,opts:Array.from(s.options).map(o=>o.value+'|'+o.text.trim()).slice(0,15)})),
    links: Array.from(document.querySelectorAll('a[href]')).map(a=>txt(a)+' :: '+a.getAttribute('href')).slice(0,50),
    inputs: Array.from(document.querySelectorAll('input')).filter(vis).map(i=>({t:i.type,n:i.name,p:i.placeholder})).slice(0,20),
  };
})()
""")
        print("\n=== UI ===")
        print(json.dumps(inv, ensure_ascii=False, indent=1)[:3000])

        rt.cancel()

asyncio.run(main())
