# ponytail: fase-3 recon — webconfig dari DOM + grep inline script + trigger interaksi.
import asyncio, json, os, urllib.request
import websockets

PORT = 9222
OUT = r"D:\Projek\WorL\backend\data\bedah_inline_webconfig_hasil.json"

def dev(path):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=5) as r:
        return json.loads(r.read())

async def main():
    tabs = dev("/json")
    _host = ("enter" "komputer" ".com")
    tab = next((t for t in tabs if _host in t.get("url", "") and t["type"] == "page"), None)
    if not tab:
        raise SystemExit("no target tab")

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

        # pasang recorder dulu
        await ev("""
(() => { window.__cap = [];
  const of = window.fetch;
  window.fetch = async function(...a) {
    const res = await of.apply(this, a);
    try {
      const url = typeof a[0]==='string'?a[0]:a[0].url;
      const body = a[1]&&a[1].body?String(a[1].body):null;
      const text = await res.clone().text();
      window.__cap.push({kind:'fetch',url,method:(a[1]&&a[1].method)||'GET',reqBody:body,status:res.status,resp:text.slice(0,200000)});
    } catch(e){}
    return res;
  };
  const oo=XMLHttpRequest.prototype.open, os=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open=function(m,u){this.__m=m;this.__u=u;return oo.apply(this,arguments);};
  XMLHttpRequest.prototype.send=function(b){this.addEventListener('load',()=>{try{window.__cap.push({kind:'xhr',url:this.__u,method:this.__m,reqBody:b?String(b):null,status:this.status,resp:String(this.responseText).slice(0,200000)});}catch(e){}});return os.apply(this,arguments);};
  return 'on';
})()
""")

        # 1) webconfig: cari elemen sumber
        wc = await ev("""
(() => {
  const out = {};
  const els = document.querySelectorAll('[class*=webconfig],[id*=webconfig],#webconfig,.webconfig');
  out.elems = Array.from(els).map(e => ({tag:e.tagName, cls:e.className, data:{...e.dataset}}));
  // fallback global
  out.hasJQuery = typeof window.jQuery !== 'undefined';
  return out;
})()
""")
        print("WEBCONFIG:", json.dumps(wc, indent=1)[:2000])

        # 2) grep semua INLINE script
        inl = await ev("""
(() => {
  const out = [];
  document.querySelectorAll('script:not([src])').forEach((s,i) => {
    const t = s.textContent;
    const hits = [];
    for (const pat of ['jeanne','RSTGE','MSTGE','signature','token','assembled','simulasi','CryptoJS','AES']) {
      let idx=0,c=0;
      while ((idx=t.indexOf(pat,idx))!==-1 && c<4) {
        hits.push({pat,ctx:t.slice(Math.max(0,idx-150),idx+250)});
        idx+=pat.length;c++;
      }
    }
    if (hits.length) out.push({idx,len:t.length,hits});
  });
  return out;
})()
""")

        # 3) klik kategori pertama di panel simulasi utk memicu XHR kategori
        click_res = await ev("""
(() => {
  const cand = document.querySelectorAll('[class*=simulasi] [class*=categor], .ps-list--categories li, [onclick]');
  const info = Array.from(cand).slice(0,15).map(e=>({cls:e.className.toString().slice(0,60), txt:(e.innerText||'').trim().slice(0,40)}));
  // klik elemen kategori prosesor kalau ada
  const target = Array.from(cand).find(e => /processor/i.test(e.innerText||'') && e.offsetParent!==null);
  if (target) { target.click(); return {clicked:(target.innerText||'').trim().slice(0,50), info}; }
  return {clicked:null, info};
})()
""")
        print("CLICK:", json.dumps(click_res, ensure_ascii=False)[:800])

        await asyncio.sleep(6)

        caps = await ev("window.__cap ? window.__cap.filter(c=>c.url.includes(_host)).map(c=>({url:c.url,method:c.method,reqBody:c.reqBody,status:c.status,resp:c.resp.slice(0,400)})) : []")
        full = await ev("window.__cap || []")

        with open(OUT, "w", encoding="utf-8") as f:
            json.dump({"webconfig": wc, "inline_grep": inl, "captured": full}, f, ensure_ascii=False, indent=1)

        print("\nINLINE GREP:")
        for b in (inl or []):
            print(f"\n-- inline#{b['idx']} ({b['len']}b)")
            seenp = set()
            for h in b["hits"]:
                if h["pat"] in seenp and h["pat"] in ("token",):
                    continue
                seenp.add(h["pat"])
                print(f"  [{h['pat']}] ...{h['ctx'][:300]}")

        print("\nCAPTURED (ringkas):")
        for c in (caps or []):
            print(f"{c['status']} {c['method']} {c['url'][:100]}")
            if c.get("reqBody"):
                print(f"   BODY: {c['reqBody'][:200]}")

        rt.cancel()

asyncio.run(main())
