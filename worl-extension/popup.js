// Popup v6.1: dua mode — FB Feed (pertanyaan worth-it) + FB Marketplace (harga komponen bekas).
// v6.1 FIX: klik tombol kini SELALU inject/refresh content script ke tab aktif via
// chrome.scripting.executeScript — reload ekstensi tidak meng-inject ulang script ke
// tab lama, penyebab "klik tapi tidak terjadi apa-apa". Feedback status tampil di popup.
const toggle = document.getElementById('toggle')
const controls = document.getElementById('controls')
const btnStop = document.getElementById('btnStop')
const btnScan = document.getElementById('btnScan')
const btnMarket = document.getElementById('btnMarket')
const keywordInput = document.getElementById('keyword')
const maxItemsInput = document.getElementById('maxItems')
const checkRepliesInput = document.getElementById('checkReplies')
const statusEl = document.getElementById('status')

async function restore() {
  const s = await chrome.storage.local.get(['on', 'keyword', 'maxItems', 'checkReplies', 'running', 'worl_progress'])
  toggle.checked = !!s.on
  if (s.keyword) keywordInput.value = s.keyword
  if (s.maxItems) maxItemsInput.value = s.maxItems
  checkRepliesInput.checked = !!s.checkReplies
  updateUI(!!s.on, s.running)
  if (s.running && s.worl_progress) statusEl.textContent = '▶ ' + s.worl_progress
}

function updateUI(on, running) {
  controls.classList.toggle('hidden', !on)
  btnStop.classList.toggle('hidden', !(on && running))
  btnScan.disabled = !!running
  btnMarket.disabled = !!running
}

function setStatus(msg, isError = false) {
  statusEl.textContent = msg
  statusEl.style.color = isError ? '#b91c1c' : '#0f766e'
}

// Pastikan content script versi AKTIF ada di tab sebelum memicu mode apa pun.
// Balikin {ok, url} — ok=false berarti tab bukan facebook.com.
async function ensureContentScript(tabId) {
  try {
    const [res] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => ({ worlActive: typeof window.worlPing === 'function' }),
    })
    if (res?.result?.worlActive) return { ok: true } // script baru sudah terpasang
  } catch (_) { /* belum ada script sama sekali */ }
  try {
    await chrome.scripting.executeScript({ target: { tabId }, files: ['content.js'] })
    return { ok: true }
  } catch (e) {
    return { ok: false, error: e.message }
  }
}

function fail(msg, detail) {
  setStatus(msg + (detail ? ` (${detail})` : ''), true)
  chrome.storage.local.set({ running: false })
}

btnScan.addEventListener('click', async () => {
  const keyword = keywordInput.value.trim()
  const maxItems = Math.max(1, parseInt(maxItemsInput.value, 10) || 30)
  const checkReplies = checkRepliesInput.checked

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  if (!(tab.url || '').includes('facebook.com')) {
    setStatus('Buka facebook.com dulu di tab ini, lalu klik lagi.', true)
    return
  }
  const inj = await ensureContentScript(tab.id)
  if (!inj.ok) return fail('Gagal inject script', inj.error)

  if (keyword) {
    await chrome.tabs.update(tab.id, { url: 'https://www.facebook.com/search/posts/?q=' + encodeURIComponent(keyword) })
  }
  await chrome.storage.local.set({
    on: true, running: true, mode: 'fb_feed', site: 'facebook_feed',
    keyword: keyword || '(semua)', maxItems, checkReplies, worl_phase: 'scan',
  })
  window.close()
})

// MODE MARKETPLACE: satu klik = scan SEMUA query komponen bekas (GPU+CPU) berurutan.
btnMarket.addEventListener('click', async () => {
  btnMarket.disabled = true
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    const url = tab.url || ''
    // halaman login FB tidak bisa dipakai — marketplace butuh sesi login
    if (/\/login\b/.test(url)) {
      setStatus('Tab masih di halaman LOGIN Facebook. Login dulu, buka facebook.com, lalu klik lagi.', true)
      return
    }
    if (!url.includes('facebook.com')) {
      setStatus('Buka facebook.com dulu di tab ini (harus sudah login), lalu klik tombolnya lagi.', true)
      return
    }
    setStatus('Memeriksa script…')
    const inj = await ensureContentScript(tab.id)
    if (!inj.ok) return fail('Gagal inject script — reload ekstensi & tab lalu coba lagi', inj.error)

    // reset state marketplace lama biar mulai dari query pertama
    await chrome.storage.local.set({
      on: true, running: true, mode: 'fb_marketplace', site: 'facebook_marketplace',
      worl_mkt_queue: null, worl_mkt_current: null, worl_mkt_counts: {},
      worl_phase: 'scan',
      worl_progress: 'Menyiapkan query pertama…',
    })
    setStatus('Mulai! Lihat badge hijau di kanan-bawah tab FB.')
    // kalau tab tidak di marketplace, arahkan ke sana; boot()/storage listener di content
    // script akan memulai scan begitu storage.onChanged fire.
    if (!url.includes('/marketplace')) {
      await chrome.tabs.update(tab.id, { url: 'https://www.facebook.com/marketplace/' })
      return // jangan close popup — biar user sempat baca status
    }
    setTimeout(() => window.close(), 1200)
  } catch (e) {
    fail('Error tak terduga', e.message)
  } finally {
    btnMarket.disabled = false
  }
})

btnStop.addEventListener('click', async () => {
  await chrome.storage.local.set({ running: false })
  const tabs = await chrome.tabs.query({})
  for (const t of tabs) {
    chrome.tabs.sendMessage(t.id, { cmd: 'stop' }).catch(() => {})
  }
  updateUI(true, false)
  setStatus('Berhenti.')
})
