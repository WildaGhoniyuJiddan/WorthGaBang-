// Popup v6.2: UI tipis — semua logika di background service worker.
// Klik = kirim pesan ke background; hasil status ditampilkan di popup.
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
  if (s.running && s.worl_progress) setStatus('▶ ' + s.worl_progress)
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

btnScan.addEventListener('click', async () => {
  setStatus('Memulai…')
  const r = await chrome.runtime.sendMessage({
    type: 'worl_feed_start',
    opts: {
      keyword: keywordInput.value.trim(),
      maxItems: Math.max(1, parseInt(maxItemsInput.value, 10) || 30),
      checkReplies: checkRepliesInput.checked,
    },
  })
  setStatus(r?.msg || JSON.stringify(r), !r?.ok)
  if (r?.ok) setTimeout(() => window.close(), 1500)
})

btnMarket.addEventListener('click', async () => {
  btnMarket.disabled = true
  setStatus('Menyiapkan query pertama…')
  // Timeout 8 dtk: kalau background mati/error, jangan tunggu selamanya.
  const r = await Promise.race([
    chrome.runtime.sendMessage({ type: 'worl_market_start' }).catch(() => null),
    new Promise((res) => setTimeout(() => res(null), 8000)),
  ])
  if (!r) {
    setStatus('Background tidak merespons. Buka brave://extensions → WorL Collector → klik icon service worker utk lihat error.', true)
    btnMarket.disabled = false
    return
  }
  setStatus(r.msg || JSON.stringify(r), !r.ok)
  btnMarket.disabled = false
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

toggle.addEventListener('change', async () => {
  await chrome.storage.local.set({ on: toggle.checked })
  updateUI(toggle.checked, false)
})

restore()
