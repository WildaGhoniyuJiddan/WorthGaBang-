// WorL background service worker (Bug 4).
// Fetch ke backend HANYA dari sini — context ekstensi, dilindungi host_permissions
// (CORS-safe). Content script kirim via chrome.runtime.sendMessage({type:'worl_send'}).
// Retry 2x percobaan ulang (3 total), delay 1.5s, balikin {ok, status} ke content script.

const BACKEND = 'http://localhost:8787/collect'

async function postWithRetry(payload, attempts = 3) {
  let lastStatus = 0
  for (let i = 0; i < attempts; i++) {
    try {
      const r = await fetch(BACKEND, {
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

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === 'worl_send') {
    postWithRetry(msg.payload).then(sendResponse)
    return true // async sendResponse
  }
})
