// WorL content script v4 — dua mode:
//
//  MODE A (fb_feed): PENGUMPUL PERTANYAAN WORTH-IT dari feed/grup.
//    1. COLLECT-AS-YOU-GO: MutationObserver menangkap tiap post begitu dirender (FB virtualisasi DOM).
//    2. DETEKSI: WORTH_DOUBT / WORTH_ASSERT + PRICE + VALUE_JUDGE + gerbang SELL_SIGNALS
//       (post jualan hanya dihitung kalau ada tanda tanya/partikel keraguan eksplisit).
//    3. Dedup & stats PERSISTEN via chrome.storage.local (aman tab reload / re-inject).
//    4. Kirim via background service worker (CORS-safe + retry), bukan fetch langsung.
//    5. Timestamp absolut dari <abbr title> -> posted_at_title (+ISO bila bisa diparse).
//    6. CEK JAWABAN (checkReplies): antrian permalink, hitung latency komentar pertama.
//    7. Anti-deteksi: delay acak, batas waktu/post/idle.
//
//  MODE B (fb_marketplace): PENGUMPUL HARGA KOMPONEN BEKAS dari FB Marketplace.
//    - Daftar query GPU/CPU terpasang otomatis (MARKET_QUERIES) — satu sesi = semua query.
//    - Per query: buka halaman search marketplace -> auto-scroll + collect-as-you-go
//      (MutationObserver; FB unmount card yang sudah lewat, scroll-then-parse pasti bolong).
//    - Render floor ~2.5s/scroll, delay antar-query 3-5s.
//    - Output item: title/price_rp/location/url per listing, type='marketplace_listing'.

const BACKEND = 'http://localhost:8787/collect'

let state = {
  on: false,
  running: false,
  mode: null,
  site: null,
  keyword: null,
  maxItems: 50,
  checkReplies: false, // true = buka tiap pertanyaan utk hitung latency jawaban (lambat tapi kaya data)
  requirePcTopic: true, // filter konteks PC/Laptop
}
let stopped = true
let mo = null

// ================= BADGE =================
let badge = null
function ensureBadge() {
  if (badge && document.body?.contains(badge)) return badge
  badge = document.createElement('div')
  badge.style.cssText =
    'position:fixed;bottom:16px;right:16px;z-index:2147483647;background:#0f172a;color:#fff;' +
    'padding:10px 14px;border-radius:10px;font:13px/1.5 monospace;box-shadow:0 4px 14px rgba(0,0,0,.45);' +
    'pointer-events:auto;min-width:230px;'
  badge.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
      <strong>WorL</strong>
      <button id="worl-x" style="background:#334155;color:#fff;border:none;border-radius:4px;cursor:pointer;padding:1px 7px;">✕</button>
    </div>
    <div id="worl-line1">siap…</div>
    <div id="worl-line2" style="color:#94a3b8;font-size:11px;"></div>`
  ;(document.body || document.documentElement).appendChild(badge)
  badge.querySelector('#worl-x').onclick = () => hardStop()
  return badge
}
function setBadge(l1, l2, bg) {
  try {
    const b = ensureBadge()
    b.querySelector('#worl-line1').textContent = l1
    b.querySelector('#worl-line2').textContent = l2 || ''
    if (bg) b.style.background = bg
  } catch (_) {}
}
async function hardStop() {
  stopped = true
  await chrome.storage.local.set({ running: false })
  setBadge('WorL berhenti', '', '#7f1d1d')
  setTimeout(() => { try { badge.remove() } catch (_) {} }, 2500)
}

// ================= UTIL =================
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// delay acak utk anti-deteksi (Bug 7)
const jitter = (min, max) => Math.floor(min + Math.random() * (max - min))

function hashStr(s) {
  let h = 0
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0
  return Math.abs(h).toString(36)
}

// Unscramble teks (FB pecah per karakter + CSS order acak)
function smartText(el) {
  if (!el) return ''
  const kids = Array.from(el.children || [])
  if (
    kids.length >= 4 &&
    kids.every((c) => (c.textContent || '').length <= 2) &&
    kids.some((c) => parseFloat(getComputedStyle(c).order || '0') !== 0)
  ) {
    return kids
      .slice()
      .sort((a, b) => (parseFloat(getComputedStyle(a).order) || 0) - (parseFloat(getComputedStyle(b).order) || 0))
      .map((c) => c.textContent)
      .join('')
      .trim()
  }
  return (el.textContent || '').trim()
}

// ================= DETEKSI PERTANYAAN WORTH-HARGA (ID) =================
// Spesifik pitch WorL: post yang MENILAI harga/nilai barang PC/Laptop.

// Grup 1 (Bug 1 fix): partikel keraguan eksplisit — selalu valid sbg sinyal tanya.
const WORTH_DOUBT = [
  'worth it', 'worthit', 'worth ga', 'worth gak', 'worth ngga', 'worth nggak', 'worth kah',
  'worth or not', 'worth tidak', 'ga worth', 'gak worth', 'ngga worth', 'nggak worth',
  'tidak worth', 'kurang worth', 'lebih worth', 'paling worth',
]
// Grup 2: assertif/netral — sering dipakai penjual; valid hanya dgn ? atau VALUE_JUDGE.
const WORTH_ASSERT = [
  'worth sih', 'worth nih', 'worth bang', 'worth gan', 'worth banget',
  'masih worth', 'worth up to', 'worth until', 'worth at',
]

// Sinyal jualan (Bug 1): kalau kena, WAJIB ada ? atau partikel keraguan eksplisit.
const SELL_SIGNALS = [
  /\bjual\b/i, /\bdijual\b/i, /\bwts\b/i, /ready\s*stock/i, /\bready\b/i,
  /preloved/i, /nego\s*tipis/i, /minat\s*(chat|wa|dm|cp)/i, /\border\b/i,
  /siap\s*kirim/i, /\bcod\b/i, /garansi\s*toko/i, /real\s*pic/i,
]

const PRICE_MENTION = [
  /rp\s?[\d.,]+/i,
  /\d+([.,]\d+)?\s*(jt|juta|k|rb|ribu|m)\b/i,
  /harga\s?\d/i,
  /di\s?harga/i,
  /dengan\s?harga/i,
  /seharga/i,
  /harganya?/,
  /overprice/,
  /murah (ga|gak|ngga|nggak|kah)/i,
  /mahal (ga|gak|ngga|nggak|kah)/i,
  /(ga|gak|ngga|nggak|kah)\s?(sih)?\s?(murah|mahal|masuk akal|overprice)/i,
]

const VALUE_JUDGE = [
  'layak ga', 'layak gak', 'layak ngga', 'layak kah', 'ga layak', 'gak layak', 'tidak layak',
  'masuk akal ga', 'masuk akal gak', 'masuk akal ngga', 'masuk akal kah',
  'bagus ga ya di harga', 'bagus ga sih di harga', 'bagus gak ya',
  'bagus ga sih', 'bagus ga ya', 'bagus ngga', 'ok ga harganya', 'oke ga harganya',
  'wajar ga', 'wajar gak', 'wajar ngga', 'wajar tidak',
  'untung ga', 'untung gak', 'rugi ga', 'rugi gak', 'rugi ngga', 'rugi tidak',
  'overprice ga', 'overprice gak', 'overprice ngga', 'overpriced',
  'ambil ga ya', 'ambil gak ya', 'beli ga ya', 'beli gak ya', 'beli kah', 'ambil kah',
  'deal ga ya', 'deal gak ya', 'gas ambil', 'jadi ambil', 'jadi beli',
  'apakah wajar', 'apakah masuk akal', 'apakah overprice', 'apakah worth', 'apakah layak',
]

// partikel keraguan nempel ke kata penilai (layak/wajar/worth/dll) — utk gerbang SELL_SIGNALS
const DOUBT_PARTICLE = /\b(layak|wajar|worth|masuk\s?akal|murah|mahal|rugi|untung|overpric\w*|bagus|ambil|beli|deal)\s*(ituh?)?\s*(ga|gak|ngga|nggak|kah)\b/i

function isWorthQuestion(text) {
  const t = ' ' + text.toLowerCase() + ' '

  const hasWorthDoubt = WORTH_DOUBT.some((w) => t.includes(w))
  const hasWorthAssert = WORTH_ASSERT.some((w) => t.includes(w))
  const hasPrice = PRICE_MENTION.some((p) => p.test(t))
  const hasJudge = VALUE_JUDGE.some((v) => t.includes(v))
  const hasQMark = text.includes('?')
  const hasDoubtParticle = DOUBT_PARTICLE.test(t)
  const isSell = SELL_SIGNALS.some((p) => p.test(t))

  // ATURAN INTI:
  //  A. kata "worth" + harga -> YA ("5600 1.8jt worth it ga?")
  //     (validitasnya ditentukan gerbang di bawah: keraguan eksplisit vs assert penjual)
  //  B. frasa penilai (layak/wajar/rugi..) + ? atau harga -> YA
  //  D. "worth" + ? tanpa harga, konteks upgrade/beli/ganti -> YA
  let reason = ''
  if ((hasWorthDoubt || hasWorthAssert) && hasPrice) reason = 'A'
  else if (hasJudge && (hasQMark || hasPrice)) reason = 'B'
  else if (hasWorthDoubt && hasQMark) reason = 'D'
  else {
    const upgradeCtx = /worth.*(upgrade|beli|ganti|ambil|rakit)/i.test(t) || /(upgrade|beli|ganti|ambil|rakit).*worth/i.test(t)
    if (hasWorthDoubt && upgradeCtx) reason = 'D'
  }

  if (!reason) return { is: false, reason: '' }

  const hasSupport = hasQMark || hasJudge || hasDoubtParticle || hasWorthDoubt
  if (isSell) {
    // GERBANG SELL (Bug 1): post jualan WAJIB punya ? atau partikel keraguan
    // eksplisit nempel kata penilai. Kata "worth it"/"worth banget" saja TIDAK cukup
    // (penjual juga pakai itu) — contoh: "worth it pasti, chat langsung".
    if (!(hasQMark || hasDoubtParticle)) {
      return { is: false, reason: reason + '+sell_filtered' }
    }
  } else if (!hasSupport) {
    // bukan jualan tapi assert tanpa dukungan apa pun ("worth banget sih") — bukan tanya
    return { is: false, reason: reason + '_unsupported' }
  }
  return { is: true, reason }
}

const PC_TERMS = [
  'pc', 'rakit', 'vga', 'gpu', 'ryzen', 'intel', 'radeon', 'rtx', 'gtx', 'rx ', 'rx5', 'rx6', 'rx7', 'rx9',
  'core i', 'i3', 'i5', 'i7', 'i9', 'pentium', 'celeron', 'xeon',
  'laptop', 'notebook', 'chromebook', 'macbook',
  'psu', 'ssd', 'hdd', 'nvme', 'sata', 'ram', 'ddr4', 'ddr5', 'ddr3',
  'prosesor', 'processor', 'cpu', 'motherboard', 'mobo', 'kasing', 'casing', 'cooler', 'fan',
  'monitor', 'keyboard', 'mouse', 'headset', 'speaker',
  'gaming', 'render', 'editing', 'streaming', 'dota', 'valorant', 'ml ', 'pubg', 'genshin', 'minecraft',
  'nitro', 'vivobook', 'thinkpad', 'ideapad', 'legion', 'rog', 'tuf', 'katana', 'cyborg', 'victus',
  'gf63', 'nf5', 'loq', 'omen', 'predator', 'swift', 'aspire', 'zenbook', 'expertbook',
]

function isPcTopic(text) {
  const t = text.toLowerCase()
  return PC_TERMS.some((w) => t.includes(w))
}

// ================= EKSTRAK POST (mode feed) =================

// Bug 5: parse timestamp absolut dari <abbr title> ke ISO (fallback: raw string).
const BULAN = { januari: 1, februari: 2, maret: 3, april: 4, mei: 5, juni: 6, juli: 7,
  agustus: 8, september: 9, oktober: 10, november: 11, desember: 12,
  january: 1, february: 2, march: 3, june: 6, july: 7, august: 8, october: 10, december: 12 }

function parseAbbrTitle(title) {
  if (!title) return null
  const m = title.match(
    /(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})[^]*?(\d{1,2})[.:](\d{2})/
  )
  if (!m) return null
  const mon = BULAN[m[2].toLowerCase()]
  if (!mon) return null
  const iso = new Date(+m[3], mon - 1, +m[1], +m[4], +m[5], 0)
  return isNaN(iso) ? null : iso.toISOString()
}

function extractPost(art) {
  // URL permanen
  let url = ''
  art.querySelectorAll('a[href]').forEach((a) => {
    const h = a.href || ''
    if (!url && (h.includes('/posts/') || h.includes('/permalink/') || /\/groups\/[^/]+\/posts\//.test(h) || h.includes('/videos/'))) {
      url = h.split('?')[0].replace(/\/$/, '')
    }
  })

  // klik "Lihat selengkapnya"
  const seeMore = [...art.querySelectorAll('div[role="button"], span[role="button"]')].find((b) =>
    /lihat selengkapnya|see more/i.test(b.textContent || '')
  )
  if (seeMore) { try { seeMore.click() } catch (_) {} }

  // penulis (anti-scramble)
  const authorEl = art.querySelector('h3 a, h4 a') || art.querySelector('strong a')
  let author = ''
  if (authorEl) author = smartText(authorEl.closest('h3, h4') || authorEl).split('\n')[0]
  if (!author) author = smartText(art.querySelector('a[role="link"] span'))

  // waktu: teks relatif + timestamp absolut dari atribut title (Bug 5)
  let timeText = ''
  let postedAtTitle = ''
  let postedAtIso = null
  const abbr = art.querySelector('abbr')
  if (abbr) {
    timeText = smartText(abbr)
    postedAtTitle = abbr.getAttribute('title') || ''
    postedAtIso = parseAbbrTitle(postedAtTitle)
  }

  // teks utama: div[dir=auto] terdalam, bukan tombol/label aksi
  let text = ''
  art.querySelectorAll('div[dir="auto"]').forEach((el) => {
    if (el.querySelector('div[dir="auto"]')) return
    const t = smartText(el)
    if (t.length <= text.length || t.length >= 6000) return
    if (/^(suka|balas|bagikan|komentari|tanggapi|like|comment|share)/i.test(t)) return
    if (author && t === author) return
    if (/^\d+(\.\d+)?[km]?$/.test(t)) return // angka engagement
    text = t
  })

  // nama grup (kalau ada)
  let group = ''
  const groupEl = art.closest('[aria-label], [data-pagelet]')?.querySelector('h2 a, h3 a[href*="/groups/"]')
  if (groupEl) group = smartText(groupEl)

  // engagement
  const allText = art.textContent || ''
  const cmMatch = allText.match(/([\d.,]+)\s*(?:komentar|comment)/i)
  const shMatch = allText.match(/([\d.,]+)\s*(?:bagikan|share)/i)

  return {
    url, author, timeText, postedAtTitle, postedAtIso, text, group,
    comments: cmMatch ? cmMatch[1] : '',
    shares: shMatch ? shMatch[1] : '',
  }
}

// ================= KIRIM (via background service worker, Bug 4) =================

// balikin {ok, status} dari background; null kalau backend mati
async function send(payload) {
  payload.scraped_at = new Date().toISOString()
  try {
    const r = await chrome.runtime.sendMessage({ type: 'worl_send', payload })
    if (!r || !r.ok) {
      console.log('[WorL] POST gagal:', r ? r.status : 'no response')
      setBadge('Backend mati! jalankan python worl-backend.py', '', '#7f1d1d')
      return false
    }
    console.log('[WorL] POST', (payload.items || []).length, '->', r.status)
    return true
  } catch (e) {
    console.log('[WorL] BACKEND MATI:', e.message)
    setBadge('Backend mati! jalankan python worl-backend.py', '', '#7f1d1d')
    return false
  }
}

// ================= DEDUP & STATS PERSISTEN (Bug 3) =================

async function seenBefore(id) {
  const key = 'seen_' + id
  const st = await chrome.storage.local.get(key)
  if (st[key]) return true
  await chrome.storage.local.set({ [key]: true })
  return false
}

const STATS_KEY = 'worl_stats'
async function bumpStats(field) {
  const st = await chrome.storage.local.get(STATS_KEY)
  const s = st[STATS_KEY] || { scanned: 0, questions: 0, pcQuestions: 0 }
  s[field] = (s[field] || 0) + 1
  await chrome.storage.local.set({ [STATS_KEY]: s })
  return s
}

// ================= MODE FEED: PENGUMPUL TANYA =================

async function scanFeed() {
  if (stopped || !state.running || state.mode !== 'fb_feed') return
  for (const art of document.querySelectorAll('div[role="article"]')) {
    try {
      const p = extractPost(art)
      if (p.text.length < 12) continue
      const id = p.url || 'txt:' + hashStr(p.text.slice(0, 160))
      if (await seenBefore(id)) continue
      await bumpStats('scanned')

      const d = isWorthQuestion(p.text)
      if (!d.is) continue
      await bumpStats('questions')
      const pc = state.requirePcTopic ? isPcTopic(p.text) : true
      if (!pc) continue
      const stats = await bumpStats('pcQuestions')

      const item = {
        id,
        name: p.author,
        author: p.author,
        time_text: p.timeText,
        posted_at_title: p.postedAtTitle,
        posted_at: p.postedAtIso,
        comments: p.comments,
        shares: p.shares,
        description: p.text.slice(0, 3000),
        url: p.url,
        is_question: 1,
        group: p.group,
        detected_reason: d.reason,
        answered: null,
        first_reply_latency_minutes: null,
      }
      const sent = await send({
        site: 'facebook_feed',
        keyword: state.keyword || '(grup)',
        page_url: location.href,
        type: 'question_post',
        items: [item],
      })
      if (sent && state.checkReplies && p.url) {
        // antrian cek-jawaban (Bug 2) — diproses di luar loop scroll
        const q = await chrome.storage.local.get('worl_reply_queue')
        const queue = q.worl_reply_queue || []
        if (!queue.some((x) => x.id === id)) queue.push({ id, url: p.url, posted_at: p.postedAtIso })
        await chrome.storage.local.set({ worl_reply_queue: queue })
      }
      setBadge(
        `▶ ${stats.pcQuestions} pertanyaan PC/Laptop`,
        `${stats.questions} pertanyaan | ${stats.scanned} post discan`,
        '#166534'
      )
      chrome.storage.local.set({
        worl_progress: `${stats.pcQuestions} pertanyaan (${stats.scanned} post discan)`,
      })
    } catch (_) {}
  }
}

async function runQuestionCollector() {
  setBadge('Mulai memindai…', 'scroll akan dilakukan otomatis', '#1e3a8a')
  await sleep(jitter(2400, 3200)) // render awal
  await scanFeed()

  mo = new MutationObserver(() => {
    clearTimeout(mo._t)
    mo._t = setTimeout(scanFeed, 800)
  })
  mo.observe(document.body, { childList: true, subtree: true })

  // Bug 7: batas waktu 20 menit + batas 400 post + delay acak 1800-3200ms
  const startedAt = Date.now()
  const TIME_LIMIT_MS = 20 * 60 * 1000
  const SCAN_LIMIT = 400
  let idle = 0
  while (!stopped && state.on && state.running) {
    const stats = (await chrome.storage.local.get(STATS_KEY))[STATS_KEY] || { scanned: 0, pcQuestions: 0 }
    if (stats.pcQuestions >= state.maxItems) break
    if (stats.scanned >= SCAN_LIMIT) { setBadge('Berhenti: batas 400 post', '', '#1e3a8a'); break }
    if (Date.now() - startedAt >= TIME_LIMIT_MS) { setBadge('Berhenti: batas 20 menit', '', '#1e3a8a'); break }

    const se = document.scrollingElement || document.documentElement
    const before = se.scrollTop
    se.scrollTop = before + 800 // instant scroll — smooth bikin FB loading lambat
    await sleep(jitter(1800, 3200))
    await scanFeed()

    const moved = (document.scrollingElement || se).scrollTop - before
    if (moved < 40) {
      idle++
      if (idle >= 5) { setBadge('Berhenti: FB throttle render', '', '#1e3a8a'); break } // Bug 7: early stop
    } else idle = 0
  }

  mo?.disconnect()
  await finishCollect()
}

// ================= SELESAI (feed) =================

async function finishCollect() {
  if (stopped) return // user hard-stop — jangan kirim ringkasan / mulai cek jawaban
  // ringkasan sesi (type=session_summary) biar keliatan denominasinya
  const stats = (await chrome.storage.local.get(STATS_KEY))[STATS_KEY] || { scanned: 0, questions: 0, pcQuestions: 0 }
  await send({
    site: 'facebook_feed',
    keyword: state.keyword || '(grup)',
    page_url: location.href,
    type: 'session_summary',
    items: [{
      name: `RINGKASAN: ${stats.pcQuestions} pertanyaan PC/Laptop dari ${stats.scanned} post`,
      description: `discan=${stats.scanned}; pertanyaan=${stats.questions}; pertanyaan_pc=${stats.pcQuestions}`,
      url: location.href,
    }],
  })
  setBadge(`Selesai ✓ ${stats.pcQuestions} pertanyaan`, `${stats.scanned} post discan — cek folder hasil`, '#166534')

  // Bug 2: setelah scan, proses antrian cek-jawaban (kalau aktif & ada isinya)
  if (state.checkReplies) {
    const q = await chrome.storage.local.get('worl_reply_queue')
    if ((q.worl_reply_queue || []).length) {
      await chrome.storage.local.set({ worl_phase: 'reply' })
      await sleep(1500)
      await startNextReply()
      return // navigasi ke permalink; lanjut di continueReplyCheck setelah re-inject
    }
  }
  cleanupScan()
}

function cleanupScan() {
  setTimeout(async () => {
    await chrome.storage.local.set({ running: false })
    stopped = true
    try { badge.remove() } catch (_) {}
  }, 6000)
}

// ================= CEK JAWABAN (Bug 2) =================
// Antrian permalink diproses SATU per navigasi: buka permalink -> hitung komentar +
// timestamp komentar pertama -> kirim UPDATE ke record yg sama (id sama) ->
// history.back() -> item berikutnya. Fase dilacak via storage key 'worl_phase'
// ('scan' | 'reply') supaya re-inject content script di feed tidak memicu scan baru.

async function startNextReply() {
  const q = await chrome.storage.local.get('worl_reply_queue')
  const queue = q.worl_reply_queue || []
  if (!queue.length) return false
  setBadge(`Cek jawaban: ${queue.length} menunggu`, 'buka permalink…', '#1e3a8a')
  location.href = queue[0].url
  return true
}

async function endReplyPhase() {
  stopped = true
  await chrome.storage.local.set({ worl_phase: 'scan', running: false })
  setBadge('Selesai ✓ termasuk cek jawaban', '', '#166534')
  setTimeout(() => { try { badge.remove() } catch (_) {} }, 6000)
}

async function continueReplyCheck() {
  const q = await chrome.storage.local.get('worl_reply_queue')
  let queue = q.worl_reply_queue || []
  const idx = queue.findIndex((x) => x.url && location.href.split('?')[0].replace(/\/$/, '') === x.url)
  if (idx === -1) return false

  await sleep(jitter(2500, 4000)) // tunggu render komentar
  const allText = document.body.textContent || ''
  const cm = allText.match(/([\d.,]+)\s*(?:komentar|comment)/i)
  const nComments = cm ? parseInt(cm[1].replace(/[.,]/g, ''), 10) || 0 : 0

  let firstReplyIso = null
  // abbr pertama di halaman = waktu POST-nya sendiri; komentar datang sesudahnya.
  // Ambil kandidat ISO, buang yg <= waktu post, terakhir yg tersisa = komentar.
  const isoCandidates = [...document.querySelectorAll('abbr[title]')]
    .map((a) => parseAbbrTitle(a.getAttribute('title') || ''))
    .filter(Boolean)
  const postMs = queue[idx].posted_at ? new Date(queue[idx].posted_at).getTime() : null
  const replies = isoCandidates.filter((iso) => !postMs || new Date(iso).getTime() > postMs)
  if (replies.length) firstReplyIso = replies[0]

  let latency = null
  if (nComments > 0 && firstReplyIso && queue[idx].posted_at) {
    latency = Math.max(0, Math.round((new Date(firstReplyIso) - postMs) / 60000))
  }

  const sent = await send({
    site: 'facebook_feed',
    keyword: state.keyword || '(grup)',
    page_url: location.href,
    type: 'question_post',
    items: [{
      id: queue[idx].id,
      url: queue[idx].url,
      answered: nComments > 0,
      first_reply_latency_minutes: latency,
      reply_check_at: new Date().toISOString(),
    }],
  })
  if (sent) {
    queue.splice(idx, 1)
    await chrome.storage.local.set({ worl_reply_queue: queue })
  } else {
    // backend mati — stop fase reply, antrian dipertahankan (jangan loop tak berujung)
    await endReplyPhase()
    setBadge('Backend mati! antrian cek-jawaban dipertahankan', 'jalankan backend lalu scan ulang', '#7f1d1d')
    return true
  }
  setBadge(`Cek jawaban: sisa ${queue.length}`, `${nComments} komentar — kembali ke feed…`, '#166534')

  // fase reply selesai utk item ini; balik ke feed, item berikutnya diproses
  // oleh boot() di feed yang mendeteksi worl_phase masih 'reply' + antrian tersisa
  history.back()
  // kalau balik lewat bfcache/SPA (script nggak di-reload), timer ini yg lanjut;
  // kalau benar-benar navigasi penuh, konteks mati & timer hilang sendiri.
  setTimeout(() => { if (!stopped && state.running) mainLoop() }, 4000)
  return true
}

// =====================================================================
// MODE MARKETPLACE: PENGUMPUL HARGA KOMPONEN BEKAS
// =====================================================================

// Daftar query komponen — sinkron dengan backend app/data/query_list.json
// (31 GPU + 12 CPU pasar Indonesia). Update manual kalau daftar backend berubah.
const MARKET_QUERIES = [
  // GPU
  'RTX 3050', 'RTX 3060', 'RTX 3060 Ti', 'RTX 3070', 'RTX 4060', 'RTX 4060 Ti',
  'RTX 4070', 'RX 5500 XT', 'RX 5600 XT', 'RX 5700', 'RX 5700 XT', 'RX 6400',
  'RX 6500 XT', 'RX 6600', 'RX 6600 XT', 'RX 6650 XT', 'RX 6700 XT', 'RX 6750 XT',
  'RX 6800', 'RX 6800 XT', 'RX 6900 XT', 'RX 6950 XT', 'RX 7600', 'RX 7600 XT',
  'RX 7700 XT', 'RX 7800 XT', 'RX 7900', 'RX 7900 XT', 'RX 9060 XT', 'RX 9070', 'RX 9070 XT',
  // CPU
  'Ryzen 5 5600', 'Ryzen 5 7600', 'Ryzen 7 7700', 'Ryzen 5 3600', 'Ryzen 5 5500',
  'Core i5 12400', 'Core i5 13400', 'Core i5 11400', 'Core i5 10400',
  'Core i7 12700', 'Core i7 13700', 'Core i7 11700',
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
// Struktur asli (hasil probe DOM 2026-08-24): leaf spans dalam urutan dokumen =
// [badge waktu opsional "Just listed", IMG, HARGA "IDR3,700,000", JUDUL, LOKASI].
// Harga = span leaf pertama yang match ^(idr|rp); judul = span setelah harga;
// lokasi = span terakhir.
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
  // judul: teks non-harga pertama SETELAH harga (sebelum harga cuma badge "Just listed")
  for (let i = priceIdx + 1; i < texts.length; i++) {
    if (/^(just|baru saja)/i.test(texts[i])) continue
    title = texts[i]
    break
  }
  // lokasi: leaf terakhir selain harga/judul
  location = texts.length > priceIdx + 2 ? texts[texts.length - 1] : ''

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

// Scan semua card marketplace yang tampak sekarang (collect-as-you-go).
async function scanMarketplace(query) {
  if (stopped || !state.running || state.mode !== 'fb_marketplace') return
  // kandidat card: anchor langsung ke item ATAU container dgn anchor di dalamnya
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
      const stats = await bumpStats('pcQuestions')
      await send({
        site: 'facebook_marketplace',
        keyword: query,
        page_url: location.href,
        type: 'marketplace_listing',
        items: [item],
      })
      setBadge(
        `▶ ${query}: ${stats.pcQuestions} listing total`,
        `query ${idxOfQuery(query) + 1}/${MARKET_QUERIES.length}`,
        '#166534',
      )
      chrome.storage.local.set({ worl_progress: marketProgressText() })
    } catch (_) {}
  }
}

// posisi query saat ini dalam antrian (untuk badge)
let QUEUE_INDEX = { q: '', i: 0 }
function idxOfQuery(q) {
  return QUEUE_INDEX.i
}

// ================= RUNNER MULTI-QUERY MARKETPLACE =================
// Satu query = satu navigasi penuh (SPA). Setelah scroll mentok -> query berikutnya.
// Progres disimpan di storage supaya aman reload/re-inject content script.

const MKEY = {
  queue: 'worl_mkt_queue',       // array query tersisa
  current: 'worl_mkt_current',   // query yang sedang dipindai
  counts: 'worl_mkt_counts',     // {query: jumlah listing}
}

function marketProgressText() {
  // dipanggil sinkron tanpa await; badge sudah menampilkan progres live.
  return 'marketplace: lihat badge'
}

async function marketStart() {
  const fullQueue = [...MARKET_QUERIES]
  await chrome.storage.local.set({
    [MKEY.queue]: fullQueue,
    [MKEY.counts]: {},
    worl_stats: { scanned: 0, questions: 0, pcQuestions: 0 },
  })
  setBadge('Marketplace: mulai', `${MARKET_QUERIES.length} query di antrian`, '#1e3a8a')
  await marketNext()
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
  const url = 'https://www.facebook.com/marketplace/search/?query=' + encodeURIComponent(current)
  setBadge('Marketplace', `menuju: ${current}`, '#1e3a8a')
  chrome.storage.local.set({ worl_progress: `Marketplace — menuju query: ${current}` })
  // SPA navigation: FB handle sendiri; content script tetap hidup.
  // Kalau ini load pertama di halaman lain, location.assign bikin re-inject — boot() lanjutkan.
  if (location.href.startsWith('https://www.facebook.com/marketplace/search')) {
    history.replaceState(null, '', url)
    // pancing FB router supaya render hasil query baru; fallback reload kalau SPA diam
    window.dispatchEvent(new PopStateEvent('popstate'))
    setTimeout(async () => {
      if (!location.href.includes('query=') || location.href === url) return
      // URL tidak berubah sesuai target -> paksa reload penuh
      if (decodeURIComponent((location.href.match(/query=([^&]+)/) || [])[1] || '') !== current) {
        location.assign(url)
      }
    }, 2500)
  } else {
    location.assign(url)
  }
}

async function runMarketCollector() {
  const st = await chrome.storage.local.get([MKEY.current, MKEY.queue])
  const current = st[MKEY.current]
  const queueNow = st[MKEY.queue] || []
  if (!current) { await marketNext(); return }
  QUEUE_INDEX = { q: current, i: MARKET_QUERIES.length - queueNow.length }

  setBadge('Marketplace: ' + current, `query ${QUEUE_INDEX.i + 1}/${MARKET_QUERIES.length} — render awal…`, '#1e3a8a')
  await sleep(jitter(2600, 3400))

  mo = new MutationObserver(() => {
    clearTimeout(mo._t)
    mo._t = setTimeout(() => scanMarketplace(current), 700)
  })
  mo.observe(document.body, { childList: true, subtree: true })

  const startedAt = Date.now()
  const TIME_LIMIT_MS = 3 * 60 * 1000 // 3 menit per query cukup utk ~30-60 card
  let idle = 0
  while (!stopped && state.on && state.running) {
    const se = document.scrollingElement || document.documentElement
    const before = se.scrollTop
    se.scrollTop = before + 900
    await sleep(jitter(2300, 3200)) // render floor FB (pengalaman feed v7)
    await scanMarketplace(current)

    const moved = (document.scrollingElement || se).scrollTop - before
    if (moved < 40) {
      idle++
      if (idle >= 3) break // hasil habis / throttle — lanjut query berikutnya
    } else idle = 0
    if (Date.now() - startedAt >= TIME_LIMIT_MS) break
  }

  mo?.disconnect()
  // catat jumlah utk query ini lalu lanjut
  const done = ((await chrome.storage.local.get(STATS_KEY))[STATS_KEY] || {}).pcQuestions || 0
  const countsFinal = (await chrome.storage.local.get(MKEY.counts))[MKEY.counts] || {}
  const prevQueryCount = countsFinal[current] || 0
  const perQuery = done - Object.entries(countsFinal).reduce((a, [, v]) => a + v, 0) + prevQueryCount
  countsFinal[current] = Math.max(0, perQuery)
  await chrome.storage.local.set({ [MKEY.counts]: countsFinal })
  await send({
    site: 'facebook_marketplace',
    keyword: current,
    page_url: location.href,
    type: 'session_summary',
    items: [{ name: `SELESAI QUERY: ${current}`, description: `listing query ini: ${countsFinal[current]}`, url: location.href }],
  })
  setBadge(`✓ ${current}`, `${countsFinal[current]} listing — lanjut…`, '#166534')
  chrome.storage.local.set({ worl_progress: `✓ ${current}: ${countsFinal[current]} listing` })
  // hapus query pertama dari antrian lalu lanjut
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

// ================= BOOT =================

function finishSession() {
  stopped = true
  chrome.storage.local.set({ running: false })
}

async function mainLoop() {
  if (!state.on || !state.running || stopped) return

  if (state.mode === 'fb_marketplace') {
    // resume-safe: kalau antrian belum ada -> mulai baru; kalau ada -> lanjut query sekarang
    const q = await chrome.storage.local.get(MKEY.queue)
    if (!(q[MKEY.queue] || []).length && !(await chrome.storage.local.get(MKEY.current))[MKEY.current]) {
      await marketStart()
    } else {
      await runMarketCollector()
    }
    return
  }
  if (state.mode !== 'fb_feed') { finishSession(); return }

  // Fase cek-jawaban aktif? (diset finishCollect sebelum navigasi pertama)
  const ph = await chrome.storage.local.get('worl_phase')
  const phase = ph.worl_phase || 'scan'

  if (phase === 'reply') {
    // di halaman permalink: hitung & update, lalu balik ke feed
    const handled = await continueReplyCheck()
    if (!handled) {
      // kita di feed (balik dari permalink) — lanjut permalink berikutnya
      const q = await chrome.storage.local.get('worl_reply_queue')
      if ((q.worl_reply_queue || []).length && state.running && !stopped) {
        await sleep(2000)
        await startNextReply()
      } else {
        await endReplyPhase()
      }
    }
    return
  }

  await runQuestionCollector()
}

async function boot() {
  if (!stopped) return
  stopped = false
  window.worlPing = () => true // penanda versi script utk popup (ensureContentScript)
  ensureBadge()
  setBadge('WorL siap', state.mode === 'fb_marketplace' ? 'mode marketplace — menunggu mulai…' : 'menunggu…')
  mainLoop()
}

chrome.storage.local.get(Object.keys(state), (s) => {
  state = { ...state, ...s }
  if (state.on && state.running) boot()
})

chrome.storage.onChanged.addListener((changes) => {
  for (const [k, v] of Object.entries(changes)) if (k in state) state[k] = v.newValue
  if (state.on && state.running) boot()
  else if (!stopped) hardStop()
})
