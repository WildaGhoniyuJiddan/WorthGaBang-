// Popup v5: single-mode — FB Feed/Grup question collector saja.
// Marketplace/E-commerce pindah ke legacy/marketplace-ecom.js (lihat PRD Bug 6).
const toggle = document.getElementById('toggle')
const controls = document.getElementById('controls')
const btnStop = document.getElementById('btnStop')
const btnScan = document.getElementById('btnScan')
const keywordInput = document.getElementById('keyword')
const maxItemsInput = document.getElementById('maxItems')
const checkRepliesInput = document.getElementById('checkReplies')
const statusEl = document.getElementById('status')

async function restore() {
  const s = await chrome.storage.local.get(['on', 'keyword', 'maxItems', 'checkReplies', 'running'])
  toggle.checked = !!s.on
  if (s.keyword) keywordInput.value = s.keyword
  if (s.maxItems) maxItemsInput.value = s.maxItems
  checkRepliesInput.checked = !!s.checkReplies
  updateUI(!!s.on, s.running)
}

function updateUI(on, running) {
  controls.classList.toggle('hidden', !on)
  btnStop.classList.toggle('hidden', !(on && running))
  btnScan.disabled = !!running
  statusEl.textContent = running
    ? 'Scanning jalan — biarkan tab FB terbuka. CSV otomatis ke folder hasil\\ setelah selesai.'
    : ''
}

toggle.addEventListener('change', async () => {
  const on = toggle.checked
  await chrome.storage.local.set({ on })
  updateUI(on, false)
})

btnScan.addEventListener('click', async () => {
  const keyword = keywordInput.value.trim()
  const maxItems = Math.max(1, parseInt(maxItemsInput.value, 10) || 30)
  const checkReplies = checkRepliesInput.checked

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  // kalau keyword diisi dan tab aktif bukan halaman search FB, arahkan ke search
  if (keyword && !(tab.url || '').includes('facebook.com')) {
    await chrome.tabs.update(tab.id, { url: 'https://www.facebook.com/search/posts/?q=' + encodeURIComponent(keyword) })
  }
  await chrome.storage.local.set({
    on: true, running: true, mode: 'fb_feed', site: 'facebook_feed',
    keyword: keyword || '(semua)', maxItems, checkReplies,
  })
  window.close()
})

btnStop.addEventListener('click', async () => {
  await chrome.storage.local.set({ running: false })
  const tabs = await chrome.tabs.query({})
  for (const t of tabs) {
    chrome.tabs.sendMessage(t.id, { cmd: 'stop' }).catch(() => {})
  }
  updateUI(true, false)
})
