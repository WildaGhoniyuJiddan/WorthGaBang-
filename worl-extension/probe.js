// Probe minimal: bukti apakah manifest content_scripts jalan sama sekali.
// Tidak tergantung kode/content.js mana pun. Membuat div kecil pojok kiri atas.
(function () {
  try {
    if (document.getElementById('worl-probe')) return
    var d = document.createElement('div')
    d.id = 'worl-probe'
    d.textContent = 'WORL-PROBE-AKTIF'
    d.style.cssText = 'position:fixed;top:0;left:0;z-index:2147483647;background:#ff00aa;color:#fff;padding:2px 6px;font-size:11px;font-family:monospace;border-radius:0 0 4px 0;'
    ;(document.body || document.documentElement).appendChild(d)

    // Tangkap error script lain (content.js isolated world error tidak sampai sini,
    // tapi uncaught di main world ya). Simpan utk dibaca via CDP.
    window.addEventListener('error', function (ev) {
      try {
        d.textContent = 'ERR:' + String(ev.message || '').slice(0, 60)
      } catch (_) {}
    })

    // Uji akses chrome.* dari world ini:
    setTimeout(function () {
      try {
        var info = []
        info.push('chrome=' + typeof chrome)
        if (typeof chrome !== 'undefined' && chrome.storage) info.push('storage=ada')
        else info.push('storage=tidak')
        var el = document.getElementById('worl-probe')
        if (el) el.textContent = info.join('|')
      } catch (e) {
        var el2 = document.getElementById('worl-probe')
        if (el2) el2.textContent = 'PROBE-ERR:' + String(e.message).slice(0, 40)
      }
    }, 300)
  } catch (e) {
    try { document.title = '[P-ERR]' + e.message } catch (_) {}
  }
})()
