// WorL background service worker v4.3.
// 1. worl_send          : relay POST ke collector localhost:8787 (retry 3x).
// 2. worl_market_start  : set state + reload/navigasi tab + INJECT content.js via
//   chrome.scripting.executeScript({files}) SETELAH halaman selesai load.
//   Catatan: executeScript dengan FILES membaca file dari disk saat dipanggil,
//   jadi selalu versi terbaru (bukan snapshot kode). Masalah lama = popup memakai
//   func+args yang di-serialize; files tidak punya masalah itu.

const COLLECT_URL = 'http://localhost:8787/collect'

async function postWithRetry(payload, attempts = 3) {
  let lastStatus = 0
  for (let i = 0; i < attempts; i++) {
    try {
      const r = await fetch(COLLECT_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (r.ok) return { ok: true, status: r.status }
      lastStatus = r.status
    } catch (_) {
      lastStatus = 0
    }
    if (i < attempts - 1) await new Promise((res) => setTimeout(res, 1500))
  }
  return { ok: false, status: lastStatus }
}

function waitForTabLoad(tabId, timeoutMs = 20000) {
  return new Promise((resolve) => {
    let done = false
    const finish = (ok) => { if (!done) { done = true; chrome.tabs.onUpdated.removeListener(listener); resolve(ok) } }
    const listener = (id, info) => {
      if (id === tabId && info.status === 'complete') finish(true)
    }
    chrome.tabs.onUpdated.addListener(listener)
    setTimeout(() => finish(false), timeoutMs)
  })
}

async function injectContent(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ['content.js'],
    })
    return true
  } catch (e) {
    return false
  }
}

async function startMarketplaceScan() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    const url = tab?.url || ''
    if (!url.includes('facebook.com')) {
      // cari tab FB mana pun kalau tab aktif bukan FB
      const all = await chrome.tabs.query({ url: ['*://www.facebook.com/*', '*://web.facebook.com/*'] })
      if (!all.length) return { ok: false, msg: 'Tidak ada tab facebook.com terbuka.' }
      const target = all[all.length - 1]
      await chrome.tabs.update(target.id, { active: true })
      return startOnTab(target)
    }
    return startOnTab(tab)
  } catch (e) {
    return { ok: false, msg: 'Error: ' + e.message }
  }
}

async function startOnTab(tab) {
  await chrome.storage.local.set({
    on: true, running: true, mode: 'fb_marketplace',
    site: 'facebook_marketplace',
    worl_mkt_queue: null, worl_mkt_current: null, worl_mkt_counts: {},
    worl_phase: 'scan',
    worl_progress: 'Menyiapkan query pertama...',
  })

  // Muat ulang halaman supaya bersih dari script lama, lalu inject file terkini.
  await chrome.tabs.reload(tab.id)
  const loaded = await waitForTabLoad(tab.id)
  if (!loaded) return { ok: false, msg: 'Halaman lambat dimuat - coba lagi.' }
  // beri jeda render awal FB
  await new Promise((r) => setTimeout(r, 2500))
  const injected = await injectContent(tab.id)
  if (!injected) return { ok: false, msg: 'Inject content script gagal - cek izin ekstensi.' }
  return { ok: true, msg: 'Mulai! Content script v4.3 masuk - lihat badge kanan bawah.' }
}

async function startFeedScan(opts) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    const url = tab?.url || ''
    if (!url.includes('facebook.com')) return { ok: false, msg: 'Buka facebook.com dulu.' }

    await chrome.storage.local.set({
      on: true, running: true, mode: 'fb_feed', site: 'facebook_feed',
      keyword: opts.keyword || '(semua)', maxItems: opts.maxItems || 30,
      checkReplies: !!opts.checkReplies, worl_phase: 'scan',
    })

    if ((tab.url || '').includes('/search/posts')) {
      await chrome.tabs.reload(tab.id)
    } else if (opts.keyword) {
      await chrome.tabs.update(tab.id, { url: 'https://www.facebook.com/search/posts/?q=' + encodeURIComponent(opts.keyword) })
    } else {
      await chrome.tabs.reload(tab.id)
    }
    const loaded = await waitForTabLoad(tab.id)
    if (!loaded) return { ok: false, msg: 'Halaman lambat dimuat.' }
    await new Promise((r) => setTimeout(r, 2500))
    const injected = await injectContent(tab.id)
    if (!injected) return { ok: false, msg: 'Inject gagal.' }
    return { ok: true, msg: 'Feed scan mulai.' }
  } catch (e) {
    return { ok: false, msg: 'Error: ' + e.message }
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === 'worl_send') {
    postWithRetry(msg.payload).then(sendResponse)
    return true
  }
  if (msg && msg.type === 'worl_market_start') {
    startMarketplaceScan().then(sendResponse)
    return true
  }
  if (msg && msg.type === 'worl_feed_start') {
    startFeedScan(msg.opts || {}).then(sendResponse)
    return true
  }
})
