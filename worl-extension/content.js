// WorL content script v4.2 — dua mode:
//
//  MODE A (fb_feed): PENGUMPUL PERTANYAAN WORTH-IT dari feed/grup.
//  MODE B (fb_marketplace): PENGUMPUL HARGA KOMPONEN BEKAS.
//
// ATURAN EKSEKUSI (penting, jangan diubah sembarangan):
// - Script ini HARUS di-load lewat manifest (bukan executeScript) supaya selalu
//   versi terbaru setelah reload ekstensi. Background hanya reload/navigasi tab.
// - Guard __WORL_ACTIVE__ mencegah dua instansi jalan bareng di satu halaman.
// - Navigasi antar-query = location.assign penuh; boot() berikutnya melanjutkan
//   dari storage (queue/current). Tidak ada SPA history API.

// Guard anti-duplikat: kalau instansi lain masih hidup, JANGAN jalankan boot lagi,
// tapi JUGA jangan throw — FB adalah SPA dan isolated world bisa bertahan lintas
// soft-navigasi; throw di sini membuat injeksi baru gagal total selamanya.
let __worlAlreadyActive = false
try {
  __worlAlreadyActive = window.__WORL_ACTIVE__ === true
} catch (_) {}
window.__WORL_ACTIVE__ = true

// ================= KONFIGURASI UMUM =================

const SEND_URL = 'http://localhost:8787/collect'
const CSV_DIR_HINT = 'hasil\\'

let state = {
  on: false,
  running: false,
  mode: 'fb_feed',
  site: 'facebook_feed',
  keyword: '(semua)',
  maxItems: 30,
  checkReplies: false,
}

const STATS_KEY = 'worl_stats'
let stopped = true
let mo = null
let scrollTimer = null

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)) }
function jitter(min, max) { return min + Math.random() * (max - min) }

function hashStr(s) {
  let h = 0
  for (let i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) | 0 }
  return Math.abs(h).toString(36)
}

// smartText: gabung teks leaf span dengan urutan CSS flexbox order (FB mengacak
// urutan DOM author name via order — pengalaman v7).
function smartText(el) {
  const leaves = []
  const walk = (node) => {
    if (!node) return
    if (node.children && node.children.length === 0) {
      const t = (node.textContent || '').replace(/\u00a0/g, ' ').trim()
      if (t) leaves.push({ t, o: parseFloat(getComputedStyle(node).order) || 0 })
      return
    }
    for (const c of node.children || []) walk(c)
  }
  walk(el)
  leaves.sort((a, b) => a.o - b.o)
  let out = ''
  for (const { t } of leaves) {
    out = out ? out + ' ' + t : t
  }
  return out.replace(/\s+/g, ' ').trim()
}

// ================= BADGE OVERLAY =================

function ensureBadge() {
  if (document.getElementById('worl-badge')) return
  const b = document.createElement('div')
  b.id = 'worl-badge'
  b.style.cssText = [
    'position:fixed', 'bottom:14px', 'right:14px', 'z-index:999999',
    'background:#1e293b', 'color:#e2e8f0', 'padding:10px 14px', 'border-radius:10px',
    'font:12px/1.5 system-ui,sans-serif', 'box-shadow:0 6px 20px rgba(0,0,0,.35)',
    'max-width:340px', 'pointer-events:none',
  ].join(';')
  document.documentElement.appendChild(b)
}

function setBadge(title, sub = '', color = '#1e293b') {
  ensureBadge()
  const b = document.getElementById('worl-badge')
  if (!b) return
  b.style.background = color
  b.innerHTML =
    '<div style="font-weight:700">' + title + '</div>' +
    (sub ? '<div style="opacity:.85">' + sub + '</div>' : '')
}

// ================= KIRIM KE COLLECTOR =================

async function send(payload) {
  try {
    const r = await chrome.runtime.sendMessage({ type: 'worl_send', payload })
    return r?.ok === true
  } catch (_) {
    return false
  }
}

// seenBefore: dedup id listing via storage (bertahan lintas reload).
async function seenBefore(id) {
  const k = 'worl_seen_ids'
  const s = await chrome.storage.local.get(k)
  const map = s[k] || {}
  if (map[id]) return true
  map[id] = Date.now()
  // prune > 5000 entri terlama
  const entries = Object.entries(map)
  if (entries.length > 5000) {
    entries.sort((a, b) => a[1] - b[1])
    for (const [oldId] of entries.slice(0, entries.length - 5000)) delete map[oldId]
  }
  await chrome.storage.local.set({ [k]: map })
  return false
}

async function bumpStats(field) {
  const s = await chrome.storage.local.get(STATS_KEY)
  const st = s[STATS_KEY] || { scanned: 0, questions: 0, pcQuestions: 0 }
  st[field] = (st[field] || 0) + 1
  st.scanned = (st.scanned || 0) + 1
  await chrome.storage.local.set({ [STATS_KEY]: st })
  return st
}

// ================= MODE A: FEED QUESTION COLLECTOR (v3, tetap utuh) =================
// (dipanggil dari mainLoop; logika lama dipertahankan)

let feedCollected = 0
const seenPosts = new Set()

function looksLikeQuestion(text) {
  if (!text) return false
  const t = text.toLowerCase()
  const hasQ = /\?|worth|it|lokh|gak|ga |nggak|gimana|bagus|recommend|rekomend|saran|budget|kira2|kira-kira|help|tolong/.test(t)
  const words = t.split(/\s+/).length
  return hasQ && words >= 6
}

async function collectFeedPost(postEl) {
  const text = smartText(postEl)
  if (!text || seenPosts.has(text.slice(0, 120))) return
  seenPosts.add(text.slice(0, 120))
  await bumpStats('questions')
  if (!looksLikeQuestion(text)) return
  await bumpStats('pcQuestions')
  feedCollected++
  await send({
    site: state.site,
    keyword: state.keyword,
    page_url: location.href,
    type: 'feed_post',
    items: [{
      name: text.slice(0, 140),
      description: text.slice(0, 2000),
      url: location.href.split('?')[0],
    }],
  })
  setBadge('Feed: ' + feedCollected + ' pertanyaan', 'total post dilihat: ' + seenPosts.size, '#7c2d12')
}

async function runQuestionCollector() {
  if (stopped || !state.running || state.mode !== 'fb_feed') return
  ensureBadge()
  setBadge('Mode Feed aktif', 'scroll berjalan otomatis…', '#7c2d12')

  const posts = () => [...document.querySelectorAll('div[role="article"]')]

  mo = new MutationObserver(() => {
    clearTimeout(mo._t)
    mo._t = setTimeout(() => {
      for (const p of posts().slice(-12)) collectFeedPost(p)
    }, 600)
  })
  mo.observe(document.body, { childList: true, subtree: true })

  for (const p of posts()) await collectFeedPost(p)

  while (!stopped && state.on && state.running && feedCollected < state.maxItems) {
    const se = document.scrollingElement || document.documentElement
    se.scrollTop += 850
    await sleep(jitter(2400, 3200))
  }

  finishSession()
  setBadge('Feed selesai ✓', feedCollected + ' pertanyaan tersimpan ke hasil\\', '#166534')
}

// ================= MODE B: MARKETPLACE PRICE COLLECTOR =================
// Query komponen bekas — sinkron app/data/query_list.json backend (43 query).

const MARKET_QUERIES = [
  // GPU (31)
  'RTX 3050', 'RTX 3060', 'RTX 3060 Ti', 'RTX 3070', 'RTX 4060',
  'RX 5500 XT', 'RX 5600 XT', 'RX 5700', 'RX 5700 XT', 'RX 6600',
  'RX 6650 XT', 'RX 7600', 'Intel Arc A750', 'Intel Arc A770',
  'GTX 1650', 'GTX 1660 Super', 'GTX 1070', 'GTX 1080', 'GTX 1080 Ti',
  'RTX 2060', 'RTX 2060 Super', 'RTX 2070', 'RTX 2080 Super',
  'RTX 3070 Ti', 'RTX 3080', 'RTX 3090', 'RTX 4060 Ti', 'RTX 4070',
  'RX 9070 XT', 'RX 7800 XT', 'Arc B580',
  // CPU (12)
  'Ryzen 5 5600', 'Ryzen 5 7600', 'Core i5 12400', 'Core i5 13400',
  'Core i7 12700', 'Core i7 13700', 'Ryzen 7 7700', 'Ryzen 5 3600',
  'Ryzen 5 5500', 'Core i5 10400', 'Core i5 11400', 'Core i7 11700',
]

// Parse "IDR3,700,000" (format marketplace) / "Rp3.750.000" -> integer rupiah; null kalau bukan.
// Kedua format: separator (titik/koma) adalah pemisah ribuan, langsung dibuang.
function parseRp(text) {
  const t = (text || '').replace(/\u00a0/g, ' ').trim()
  const m = t.match(/^(?:idr|rp)\s*([\d.,\s]+)/i)
  if (!m) return null
  const digits = m[1].replace(/[.,\s]/g, '')
  if (!digits) return null
  const val = parseInt(digits, 10)
  return isFinite(val) ? val : null
}

// Ekstrak satu card listing marketplace.
// Struktur asli (probe DOM 2026-08-24): leaf spans urutan dokumen =
// [badge waktu opsional "Just listed", IMG, HARGA "IDR3,700,000", JUDUL, LOKASI].
function extractMarketCard(cardEl, query) {
  const link = cardEl.matches('a[href]') ? cardEl : cardEl.querySelector('a[href*="/marketplace/item/"]')
  if (!link) return null
  const href = link.href || ''
  if (!href.includes('/marketplace/item/')) return null
  const scope = cardEl.matches('a[href]') ? cardEl.parentElement || cardEl : cardEl

  const texts = [...scope.querySelectorAll('span')]
    .filter((s) => !s.children.length)
    .map((s) => smartText(s))
    .filter((t) => t && t.length < 200)

  let title = ''
  let priceText = ''
  let price = null
  let priceIdx = -1
  for (let i = 0; i < texts.length; i++) {
    if (/^(idr|rp)\s?[\d.,]/i.test(texts[i])) {
      priceText = texts[i]
      price = parseRp(texts[i])
      priceIdx = i
      break
    }
  }
  // judul: teks non-harga pertama SETELAH harga (sebelum harga cuma badge "Just listed").
  // Span harga kedua (= harga lama dicoret) juga dilewati — bukan judul.
  for (let i = priceIdx + 1; i < texts.length; i++) {
    if (/^(just|baru saja)/i.test(texts[i])) continue
    if (/^(idr|rp)\s?[\d.,]/i.test(texts[i])) continue
    title = texts[i]
    break
  }
  // lokasi: leaf terakhir selain harga/judul
  const location = texts.length > priceIdx + 2 ? texts[texts.length - 1] : ''

  if (!price || !title || price < 50_000) return null // tanpa harga/judul = sampah
  const idMatch = href.match(/\/marketplace\/item\/(\d+)/)
  const id = idMatch ? idMatch[1] : 'mk:' + hashStr(href.split('?')[0])
  return {
    id,
    name: (query + ' — ' + title).slice(0, 300),
    price_text: priceText,
    price_rp: price,
    description: title,
    location,
    category: query,
    url: href.split('?')[0],
  }
}

// True kalau URL memang search page utk query yang diharapkan.
// Cukup param ?query= — pathname FB bervariasi (ada trailing slash, ada city id).
function onExpectedSearchPage(expectedQuery) {
  try {
    const u = new URL(location.href)
    if (!u.pathname.toLowerCase().includes('marketplace')) return false
    const got = (u.searchParams.get('query') || '').trim().toLowerCase()
    return got === expectedQuery.trim().toLowerCase()
  } catch (_) {
    return false
  }
}

// Scan semua card marketplace yang tampak sekarang; kirim batch per 10 item.
let mktBuffer = []
async function flushMarketBuffer(query, force = false) {
  if (!mktBuffer.length) return
  if (!force && mktBuffer.length < 10) return
  const batch = mktBuffer.splice(0, mktBuffer.length)
  await send({
    site: 'facebook_marketplace',
    keyword: query,
    page_url: location.href,
    type: 'marketplace_listing',
    items: batch,
  })
}

let scanInFlight = false
async function scanMarketplace(query) {
  if (stopped || !state.running || state.mode !== 'fb_marketplace') return
  if (!onExpectedSearchPage(query)) return
  if (scanInFlight) return
  scanInFlight = true
  try {
    const anchors = [...document.querySelectorAll('a[href*="/marketplace/item/"]')]
    const seenEls = new Set()
    for (const a of anchors) {
      try {
        const cardEl = a.parentElement && a.parentElement.querySelector('img') ? a.parentElement : a
        if (seenEls.has(cardEl)) continue
        seenEls.add(cardEl)
        const item = extractMarketCard(cardEl, query)
        if (!item) continue
        if (await seenBefore(item.id)) continue
        await bumpStats('pcQuestions')
        mktBuffer.push(item)
        await flushMarketBuffer(query)
      } catch (_) {}
    }
    const total = ((await chrome.storage.local.get(STATS_KEY))[STATS_KEY] || {}).pcQuestions || 0
    setBadge(`▶ ${query}: ${total} listing`, `query ${idxOfQuery(query) + 1}/${MARKET_QUERIES.length}`, '#166534')
    chrome.storage.local.set({ worl_progress: `Marketplace ${idxOfQuery(query) + 1}/${MARKET_QUERIES.length} — ${query}: ${total} total` })
  } finally {
    scanInFlight = false
  }
}

// posisi query saat ini dalam antrian (untuk badge)
let QUEUE_INDEX = { q: '', i: 0 }
function idxOfQuery(q) {
  return QUEUE_INDEX.i
}

// ================= RUNNER MULTI-QUERY MARKETPLACE =================
// Satu query = satu navigasi penuh. Progres di storage -> aman lintas reload.

const MKEY = {
  queue: 'worl_mkt_queue',       // array query tersisa
  current: 'worl_mkt_current',   // query yang sedang dipindai
  counts: 'worl_mkt_counts',     // {query: jumlah listing}
}

async function marketStart() {
  const fullQueue = [...MARKET_QUERIES]
  await chrome.storage.local.set({
    [MKEY.queue]: fullQueue,
    [MKEY.counts]: {},
    [MKEY.current]: fullQueue[0],
    worl_stats: { scanned: 0, questions: 0, pcQuestions: 0 },
  })
  setBadge('Marketplace: mulai', `${MARKET_QUERIES.length} query — menuju "${fullQueue[0]}"`, '#1e3a8a')
  // langsung navigasi ke query pertama (jangan menunggu boot berikutnya)
  location.assign('https://www.facebook.com/marketplace/search/?query=' + encodeURIComponent(fullQueue[0]))
}

async function marketNext() {
  const q = await chrome.storage.local.get(MKEY.queue)
  const queue = q[MKEY.queue] || []
  if (!queue.length) {
    await marketFinish()
    return
  }
  const current = queue[0]
  await chrome.storage.local.set({ [MKEY.current]: current, [MKEY.queue]: queue })
  setBadge('Marketplace', `menuju: ${current}`, '#1e3a8a')
  location.assign('https://www.facebook.com/marketplace/search/?query=' + encodeURIComponent(current))
}

async function runMarketCollector() {
  const st = await chrome.storage.local.get([MKEY.current, MKEY.queue])
  const current = st[MKEY.current]
  const queueNow = st[MKEY.queue] || []
  if (!current) { await marketNext(); return }
  QUEUE_INDEX = { q: current, i: MARKET_QUERIES.length - queueNow.length }

  // VERIFIKASI HALAMAN: tunggu sampai URL benar-benar halaman search query ini.
  // Reload penuh ±2-4 detik; cek tiap 1.5 detik, maksimal 20 detik.
  let pageOk = onExpectedSearchPage(current)
  if (!pageOk) {
    setBadge('Marketplace', `menunggu halaman "${current}"…`, '#1e3a8a')
    for (let i = 0; i < 13 && !stopped && state.running; i++) {
      await sleep(1500)
      if (onExpectedSearchPage(current)) { pageOk = true; break }
    }
    if (!pageOk) {
      if (stopped || !state.running) return
      setBadge('Marketplace', `halaman tak kunjung benar — navigasi ulang`, '#7f1d1d')
      location.assign('https://www.facebook.com/marketplace/search/?query=' + encodeURIComponent(current))
      return
    }
  }

  setBadge('Marketplace: ' + current, `query ${QUEUE_INDEX.i + 1}/${MARKET_QUERIES.length} — render awal…`, '#166534')

  // TUNGGU CARD PERTAMA dirender sebelum scroll (grid butuh ±3-8 dtk setelah load).
  let firstCard = false
  for (let i = 0; i < 10 && !stopped && state.running; i++) {
    if (document.querySelector('a[href*="/marketplace/item/"]')) { firstCard = true; break }
    setBadge('Marketplace: ' + current, `menunggu hasil render… (${i + 1})`, '#1e3a8a')
    await sleep(1600)
  }
  await scanMarketplace(current) // scan pertama sesaat setelah render

  mo = new MutationObserver(() => {
    clearTimeout(mo._t)
    mo._t = setTimeout(() => scanMarketplace(current), 800)
  })
  mo.observe(document.body, { childList: true, subtree: true })

  const startedAt = Date.now()
  const MIN_DWELL_MS = 75 * 1000      // minimal 75 dtk di query ini apa pun yang terjadi
  const MAX_TIME_MS = 3 * 60 * 1000   // maksimal 3 menit
  let noNewRounds = 0
  let lastTotal = -1

  while (!stopped && state.on && state.running) {
    const se = document.scrollingElement || document.documentElement
    const before = se.scrollTop
    se.scrollTop = before + 900
    await sleep(jitter(2500, 3300))
    await scanMarketplace(current)

    const total = ((await chrome.storage.local.get(STATS_KEY))[STATS_KEY] || {}).pcQuestions || 0
    const gotNew = total !== lastTotal
    lastTotal = total
    const elapsed = Date.now() - startedAt

    if (elapsed >= MAX_TIME_MS) break
    if (elapsed >= MIN_DWELL_MS && !gotNew && firstCard) {
      noNewRounds++
      if (noNewRounds >= 2) break // stagnan ±6-7 dtk setelah dwell minimum
    } else if (gotNew) {
      noNewRounds = 0
    }
  }

  mo?.disconnect()
  await flushMarketBuffer(current, true)
  const done = ((await chrome.storage.local.get(STATS_KEY))[STATS_KEY] || {}).pcQuestions || 0
  const countsFinal = (await chrome.storage.local.get(MKEY.counts))[MKEY.counts] || {}
  const prevTotalAll = Object.entries(countsFinal).reduce((a, [, v]) => a + v, 0)
  countsFinal[current] = Math.max(0, done - prevTotalAll)
  await chrome.storage.local.set({ [MKEY.counts]: countsFinal })
  await send({
    site: 'facebook_marketplace',
    keyword: current,
    page_url: location.href,
    type: 'session_summary',
    items: [{ name: `SELESAI QUERY: ${current}`, description: `listing query ini: ${countsFinal[current]}`, url: location.href }],
  })
  setBadge(`✓ ${current}`, `${countsFinal[current]} listing — lanjut…`, '#166534')
  const qq = await chrome.storage.local.get(MKEY.queue)
  const queue = (qq[MKEY.queue] || []).slice(1)
  await chrome.storage.local.set({ [MKEY.queue]: queue, [MKEY.current]: null })
  await marketNext()
}

async function marketFinish() {
  const counts = (await chrome.storage.local.get(MKEY.counts))[MKEY.counts] || {}
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  const filled = Object.values(counts).filter((n) => n > 0).length
  await send({
    site: 'facebook_marketplace',
    keyword: '(semua query)',
    page_url: location.href,
    type: 'session_summary',
    items: [{
      name: `RINGKASAN MARKETPLACE: ${total} listing dari ${filled}/${MARKET_QUERIES.length} query`,
      description: JSON.stringify(counts),
      url: location.href,
    }],
  })
  setBadge(`Selesai ✓ ${total} listing`, `${filled}/${MARKET_QUERIES.length} query — cek folder hasil`, '#166534')
  cleanupScan()
}

// ================= BOOT & LOOP =================

function cleanupScan() {
  mo?.disconnect()
  mo = null
  clearTimeout(scrollTimer)
}

function hardStop() {
  cleanupScan()
  stopped = true
  setBadge('WorL berhenti', 'aktifkan toggle + klik hijau untuk mulai lagi', '#334155')
}

function finishSession() {
  stopped = true
  chrome.storage.local.set({ running: false })
}

async function mainLoop() {
  if (!state.on || !state.running || stopped) return

  if (state.mode === 'fb_marketplace') {
    // resume-safe: antrian kosong & tak ada current -> mulai baru; else lanjut.
    const q = await chrome.storage.local.get([MKEY.queue, MKEY.current])
    const hasQueue = (q[MKEY.queue] || []).length > 0
    const hasCurrent = !!q[MKEY.current]
    if (!hasQueue && !hasCurrent) {
      await marketStart()
    } else {
      await runMarketCollector()
    }
    return
  }
  if (state.mode !== 'fb_feed') { finishSession(); return }

  const ph = await chrome.storage.local.get('worl_phase')
  const phase = ph.worl_phase || 'scan'

  if (phase === 'reply') {
    // fase reply-check milik mode feed lama; jalankan bila tersedia
    if (typeof continueReplyCheck === 'function' && typeof startNextReply === 'function' && typeof endReplyPhase === 'function') {
      const handled = await continueReplyCheck()
      if (!handled) {
        const rq = await chrome.storage.local.get('worl_reply_queue')
        if ((rq.worl_reply_queue || []).length && state.running && !stopped) {
          await sleep(2000)
          await startNextReply()
        } else {
          await endReplyPhase()
        }
      }
      return
    }
    // fungsi reply tidak ada (file ringkas) — kembali ke scan biasa
    await chrome.storage.local.set({ worl_phase: 'scan' })
  }

  await runQuestionCollector()
}

async function boot() {
  if (!stopped || __worlAlreadyActive) return
  stopped = false
  ensureBadge()
  setBadge('WorL siap ✓', 'mode: ' + (state.mode || 'fb_feed'), '#334155')
  mainLoop()
}

// ponytail: self-start di halaman search marketplace — menghapus dependensi
// storage gate yang rapuh di Brave (SW mati sebelum storage flush).
// Upgrade path: kalau mau kontrol penuh, simpan flag via chrome.session.
const isMarketSearch = /^\/marketplace\/(\d+\/)?search\//.test(location.pathname)

// DEBUG v4.3.2: tanda hidup content.js di halaman search, dihapus setelah diagnosis.
if (isMarketSearch) {
  const dbg = document.createElement('div')
  dbg.id = 'worl-debug'
  dbg.textContent = 'WorL content.js LOADED'
  dbg.style.cssText = 'position:fixed;bottom:14px;left:14px;z-index:999999;background:#7c3aed;color:#fff;padding:8px 12px;border-radius:8px;font:11px system-ui;'
  document.documentElement.appendChild(dbg)
}

if (isMarketSearch) {
  // Paksa mode marketplace di halaman search, apa pun isi storage.
  state.on = true
  state.running = true
  state.mode = 'fb_marketplace'
}

chrome.storage.local.get(Object.keys(state), (s) => {
  try {
    state = { ...state, ...s }
    if (isMarketSearch) {
      state.on = true
      state.running = true
      state.mode = 'fb_marketplace'
    }
    const dbg = document.getElementById('worl-debug')
    if (dbg) dbg.textContent = 'WorL gate: on=' + state.on + ' running=' + state.running
    if (state.on && state.running) boot()
  } catch (e) {
    const dbg2 = document.getElementById('worl-debug')
    if (dbg2) dbg2.textContent = 'WorL ERR: ' + e.message
  }
})

chrome.storage.onChanged.addListener((changes) => {
  for (const [k, v] of Object.entries(changes)) if (k in state) state[k] = v.newValue
  const active = isMarketSearch || (state.on && state.running)
  if (state.on && state.running) boot()
  else if (!stopped && !active) hardStop()
})
