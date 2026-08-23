// legacy/marketplace-ecom.js — kode mode FB Marketplace & E-commerce dari v2/v6/v7.
// TIDAK di-load di manifest (Bug 6). Kalau butuh lagi:
//   1. daftarkan file ini di manifest content_scripts
//   2. balikin tombol "FB Marketplace"/"E-commerce" di popup.html + MODES di popup.js
// Fungsi bergantung state/send/setBadge/sleep dari content.js (urutan load: content.js dulu).

function parseFbList() {
  const out = []
  document.querySelectorAll('a[href*="/marketplace/item/"]').forEach((a) => {
    const text = a.textContent?.replace(/\s+/g, ' ').trim() || ''
    const pm = /Rp\s?[\d.,]+/.exec(text)
    if (!pm) return
    const after = text.slice(text.indexOf(pm[0]) + pm[0].length).trim()
    out.push({ name: after.split(' · ')[0] || after.slice(0, 120), price_text: pm[0], url: a.href.split('?')[0] })
  })
  return out
}
function parseTokpedList() {
  const out = []
  document.querySelectorAll('a[data-testid="linkProductContainer"], a[href*="/p/"]').forEach((a) => {
    const name = a.querySelector('[data-testid="spfPCSTitle"], [class*="title"]')?.textContent?.trim() || ''
    const priceText = a.querySelector('[data-testid="spfPSCPrice"], [class*="price"]')?.textContent?.trim() || ''
    if (name && priceText) out.push({ name, price_text: priceText, url: a.href.split('?')[0] })
  })
  return out
}
function parseShopeeList() {
  const out = []
  document.querySelectorAll('[data-sqe="link"]').forEach((a) => {
    const card = a.closest('li') || a
    const name =
      card.querySelector('[class*="ksB1I"], [data-testid="lblSKUProductTitle"]')?.textContent?.trim() ||
      a.getAttribute('aria-label') || ''
    const priceText = card.querySelector('[class*="vioxXd"], [class*="pmmxKx"]')?.textContent?.trim() || ''
    if (name && priceText) out.push({ name, price_text: priceText, url: a.href.split('?')[0] })
  })
  return out
}
const LIST_PARSERS = { facebook: parseFbList, tokopedia: parseTokpedList, shopee: parseShopeeList }

function parseFbDetail() {
  let desc = ''
  document.querySelectorAll('[data-ad-comet-preview], [dir="auto"] > span').forEach((el) => {
    const t = el.textContent?.trim() || ''
    if (t.length > desc.length && t.length < 5000) desc = t
  })
  const title = document.querySelector('h1, h2')?.textContent?.trim() || ''
  const priceEl = /Rp\s?[\d.,]+/.exec(document.body.textContent)?.[0] || ''
  return { title, description: desc.slice(0, 3000), price_text: priceEl }
}
function parseTokpedDetail() {
  const title = document.querySelector('h1[data-testid="llmPDPHeaderProductName"], h1')?.textContent?.trim() || ''
  let desc = ''
  document.querySelectorAll('[data-testid="llmPDPDescriptionContent"], #product-description, [class*="description"]').forEach((el) => {
    const t = el.textContent?.trim() || ''
    if (t.length > desc.length) desc = t
  })
  const priceEl = document.querySelector('[data-testid="llmPDPPriceAmount"], [class*="price"]')?.textContent?.trim() || ''
  return { title, description: desc.slice(0, 5000), price_text: priceEl }
}
function parseShopeeDetail() {
  const title = document.querySelector('h1[data-testid="product-item-name"], [class*="_44qnta"]')?.textContent?.trim() || ''
  let desc = ''
  document.querySelectorAll('[data-testid="product-item-description"], [class*="pqTWkA"]').forEach((el) => {
    const t = el.textContent?.trim() || ''
    if (t.length > desc.length) desc = t
  })
  const priceEl = document.querySelector('[class*="pypRxC"], [class*="_2v0HgN"]')?.textContent?.trim() || ''
  return { title, description: desc.slice(0, 5000), price_text: priceEl }
}
const DETAIL_PARSERS = { facebook: parseFbDetail, tokopedia: parseTokpedDetail, shopee: parseShopeeDetail }

let detailCount = 0
async function runDetailCrawl() {
  const items = LIST_PARSERS[state.site]?.() || []
  for (const item of items) {
    if (!state.running || stopped) return false
    const key = 'done_' + item.url
    const st = await chrome.storage.local.get(key)
    if (st[key]) continue
    await chrome.storage.local.set({ [key]: true })
    location.href = item.url + (item.url.includes('?') ? '&' : '?') + 'ref=worl_scraper'
    return true
  }
  return false
}
async function finishDetail() {
  const d = DETAIL_PARSERS[state.site]?.()
  setBadge(`detail ${detailCount + 1}/${state.maxItems}`, '', '#1e3a8a')
  await send({
    site: state.site,
    keyword: state.keyword,
    page_url: location.href,
    type: state.mode === 'fb_marketplace' ? 'post' : 'product_detail',
    items: [{ name: d.title, price_text: d.price_text, description: d.description, url: location.href }],
  })
  detailCount++
  if (detailCount >= state.maxItems) { finishSession(); return false }
  await sleep(800)
  history.back()
  return true
}
async function scrollAndNext() {
  window.scrollBy({ top: 900, behavior: 'smooth' })
  await sleep(1200)
  const atBottom = window.innerHeight + window.scrollY >= document.body.scrollHeight - 250
  if (!atBottom) return true
  for (const s of ['button.shopee-icon-button--right', 'button[aria-label*="Berikutnya"]', 'button[aria-label*="Next"]']) {
    const b = document.querySelector(s)
    if (b && !b.disabled) { b.click(); await sleep(3500); return true }
  }
  return false
}
