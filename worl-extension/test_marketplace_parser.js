// Self-check parser marketplace tanpa browser — struktur card ASLI dari probe DOM
// 2026-08-24: [badge "Just listed", IMG, HARGA "IDR3,700,000", JUDUL, LOKASI].
// Jalankan: node test_marketplace_parser.js
const src = require('fs').readFileSync('content.js', 'utf8')

function extractFn(name) {
  const m = src.match(new RegExp('function ' + name + '\\(text\\) \\{[\\s\\S]*?\\n\\}'))
  if (!m) { console.error(name + ' tidak ketemu'); process.exit(1) }
  return m[0]
}
eval(extractFn('parseRp'))

let fail = 0
function check(label, got, expect) {
  const ok = JSON.stringify(got) === JSON.stringify(expect)
  if (!ok) fail++
  console.log(`${ok ? 'OK  ' : 'FAIL'} ${label}: ${JSON.stringify(got)} (harus ${JSON.stringify(expect)})`)
}

// parseRp: format IDR marketplace + Rp legacy + sampah
check('IDR3,700,000', parseRp('IDR3,700,000'), 3700000)
check('IDR 12,500,000', parseRp('IDR 12,500,000'), 12500000)
check('Rp3.750.000', parseRp('Rp3.750.000'), 3750000)
check('IDR850,000', parseRp('IDR850,000'), 850000)
check('harga nego', parseRp('harga nego'), null)
check('""', parseRp(''), null)
check('null', parseRp(null), null)

console.log(fail ? `\n${fail} FAIL` : '\nSEMUA PASS')
process.exit(fail ? 1 : 0)
