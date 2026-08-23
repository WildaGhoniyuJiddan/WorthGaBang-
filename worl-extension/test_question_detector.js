// Test deteksi PERTANYAAN WORTH-IT-HARGA (spesifik: menilai harga/nilai, bukan tanya teknis).
const fs = require('fs')
const src = fs.readFileSync('content.js', 'utf8')

const start = src.indexOf('const WORTH_DOUBT')
const end = src.indexOf('const PC_TERMS')
const fn = new Function(src.slice(start, end) + '; return { isWorthQuestion }')
const { isWorthQuestion } = fn()

// return sekarang {is, reason} — bungkus biar kompatibel dgn format lama
function detect(text) {
  const r = isWorthQuestion(text)
  return r.is
}

const cases = [
  // [teks, harus terdeteksi]
  ['ryzen 5 5600 2nd harga 1.8jt worth it ga?', true],
  ['ini bagus ga ya di harga 5 juta?', true],
  ['RTX 3060 second 2.5jt layak ga?', true],
  ['vga rx 6600 dijual 2.9jt murah ga nih? worth ga?', true],
  ['laptop gaming bekas 7jt masuk akal ga ya harganya?', true],
  ['psu second 500rb overprice ga?', true],
  ['monitor 144hz second 900k gimana gan, worth it?', true],
  ['ryzen 5 5600 worth it kah buat upgrade dari 3600?', true], // worth eksplisit walau harga implisit
  ['beli laptop 10 jt dapet i7 gen 12, bagus ga sih harganya?', true],
  // bukan pertanyaan worth-harga
  ['gimana cara setting bios buat ram xmp?', false],        // tanya teknis
  ['apakah rtx 3060 masih layak buat 1080p di 2026?', false], // performa, tanpa harga
  ['Jual VGA RTX 2060 second mulus like new', false],        // jualan
  ['WTS keyboard mechanical murah', false],                  // jualan
  ['terima kasih min infonya', false],
  ['lapak laptop bekas mulus gan', false],
  // === kasus BARU Bug 1: post jualan pakai kata "worth" (dari PRD, harus FALSE) ===
  ['RTX 3060 dijual 2jt worth banget gan, buruan cepetan!', false],
  ['WTS ryzen 5 3600 harga 1.5jt worth it pasti, chat langsung', false],
  ['ready stock rtx 3060 harga 3jt worth banget, no php', false],
  // varian jualan lain
  ['dijual laptop gaming mulus, harga 6.5jt nego tipis, minat wa', false],
  ['preloved rx 6600 seharga 2.3jt garansi toko masih panjang, real pic, cod jaksel', false],
  // jualan TAPI ada keraguan eksplisit -> tetap pertanyaan (harus TRUE)
  ['jual rx 6600 2.9jt, worth ga ya beli?', true],
  ['ready stock psu 700w 1.2jt, layak gak sih diambil?', true],
]

let pass = 0
for (const [text, want] of cases) {
  const got = detect(text)
  const ok = got === want
  console.log(ok ? 'PASS' : 'FAIL', JSON.stringify(text.slice(0, 56)), '->', got)
  if (ok) pass++
}
console.log(`\n${pass}/${cases.length} pass`)
process.exit(pass === cases.length ? 0 : 1)
