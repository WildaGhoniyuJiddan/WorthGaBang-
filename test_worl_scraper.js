// Test worl-scraper tanpa API key: verifikasi preprocess + struktur engine.
// Ekstraksi LLM butuh OPENAI_API_KEY — test itu terpisah.
const { chromium } = require('playwright')
const { WorLScraper, preprocess } = require('./worl-scraper')
const fs = require('fs')
const path = require('path')

async function main() {
  // 1) preprocess test: buka markdown tokopedia sebagai data URL, format text
  const browser = await chromium.launch()
  const page = await browser.newPage()
  const mdPath = path.join(__dirname, 'jina_tokped.md')
  await page.goto('data:text/plain,' + encodeURIComponent(fs.readFileSync(mdPath, 'utf8')))

  const pre = await preprocess(page, { format: 'text' })
  console.log('preprocess ok | url:', pre.url.slice(0, 40))
  console.log('content len:', pre.content.length)
  if (pre.content.length < 50) throw new Error('preprocess menghasilkan konten kosong')

  // 2) engine structure: WorLScraper bisa dibuat + method ada
  const scraper = new WorLScraper({ callExample: true }) // dummy model
  for (const m of ['extract', 'stream', 'generateCode']) {
    if (typeof scraper[m] !== 'function') throw new Error(`method hilang: ${m}`)
  }
  console.log('engine methods ok: extract, stream, generateCode')

  // 3) error handling: custom tanpa function harus throw
  try {
    await preprocess(page, { format: 'custom' })
    throw new Error('seharusnya throw')
  } catch (e) {
    if (!/formatFunction/.test(e.message)) throw e
    console.log('custom-format guard ok')
  }

  await browser.close()
  console.log('ALL CHECKS PASSED')
}

main().catch((e) => {
  console.error('FAIL:', e.message)
  process.exit(1)
})
