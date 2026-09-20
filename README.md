# WorthGaBang? (WorL) 💡
> **Platform Cek Kelayakan Harga Komponen PC, Laptop, dan Paket Bundle Rakitan di Pasar Indonesia**

---

## 📌 Apa itu WorthGaBang?

**WorthGaBang?** adalah platform cerdas yang membantu masyarakat, gamer, pelajar, dan perakit PC di Indonesia untuk mengetahui apakah harga suatu hardware komputer atau laptop yang mereka temukan di marketplace atau toko komputer **layak dibeli (worth it)** atau **kemahalan**.

Aplikasi ini menganalisis tawaran harga Anda secara instan dan membandingkannya dengan data riil pasar—menggabungkan data agregasi listing marketplace terpopuler dan katalog harga ritel resmi di Indonesia.

---

## ✨ Fitur Utama

1. **Cek Komponen PC Satuan**
   - **VGA / Kartu Grafis (GPU)**: NVIDIA GeForce RTX/GTX, AMD Radeon RX, Intel Arc.
   - **Prosesor (CPU)**: AMD Ryzen, Intel Core (generasi lama hingga Core Ultra / Generasi 14).
   - **Memori (RAM)**: DDR3, DDR4, DDR5 berbagai kapasitas (4GB hingga 64GB).
   - **Penyimpanan (Storage)**: SSD NVMe M.2, SSD SATA, HDD internal.
   - **Motherboard**: AM4, AM5, LGA1700, LGA1851 dari berbagai chipset.

2. **Cek Unit Laptop (Baru & Bekas)**
   - Mendukung ribuan varian laptop yang beredar di Indonesia: lini gaming (ROG, TUF, Legion, LOQ, Nitro, Predator, Victus, OMEN, Katana, Cyborg, Alienware), lini tipis/ultrabook (Zenbook, Swift, Yoga, XPS, MacBook), hingga laptop kerja dan edukasi (Vivobook, IdeaPad, Aspire, Pavilion, HP 14s, ThinkPad, Latitude, Axioo, Advan).

3. **Cek Paket Bundle Rakitan PC**
   - Masukkan beberapa komponen sekaligus (misal: Prosesor + Motherboard + GPU) dan bandingkan total harga paket bundling terhadap kalkulasi total harga pasar satuan.

4. **Analisis Lintas Pasar (Baru vs Bekas)**
   - Menghitung persentase penghematan tawaran unit bekas terhadap harga ritel resmi baru.
   - Mengingatkan Anda jika tawaran harga bekas ternyata sudah mendekati harga unit baru bergaransi resmi.

5. **Rekomendasi Alternatif Performa (Benchmark)**
   - Memberikan rekomendasi alternatif hardware sekelas atau ber-tier lebih tinggi pada rentang budget yang sama jika harga yang Anda masukkan dinilai kurang menguntungkan.

---

## 🚀 Panduan Penggunaan

Aplikasi dirancang agar sangat mudah digunakan oleh siapa saja:

```
[ Pilih Kategori ] ---> [ Masukkan Model & Harga ] ---> [ Dapatkan Analisis Seketika ]
```

### Langkah 1: Pilih Mode
Pilih salah satu dari 3 mode di bagian atas:
- **Komponen PC**: Untuk mengecek hardware satuan (GPU, CPU, RAM, Storage, Mobo).
- **Laptop**: Untuk mengecek unit laptop utuh.
- **Paket Bundle**: Untuk mengecek paket rakitan PC beberapa komponen.

### Langkah 2: Masukkan Data Barang
- **Nama Komponen / Seri Laptop**: Ketik model yang dicari (tersedia fitur rekomendasi otomatis/autocomplete).
  - *Contoh Komponen*: `RTX 4060`, `Ryzen 5 5600`, `RAM DDR4 16GB`, `SSD NVMe 1TB`.
  - *Contoh Laptop*: `Lenovo LOQ 15`, `ASUS TUF A15`, `MacBook Air M1`.
- **Harga yang Ditawarkan**: Masukkan angka harga (dalam Rupiah) yang tertera pada toko atau penjual yang Anda temukan.
- **Kondisi**: Pilih `Baru`, `Bekas / Second`, atau `Semua Kondisi`.

### Langkah 3: Klik "Analisis Harga"
Sistem akan memproses data dalam hitungan detik dan menampilkan:
- **Skor Kelayakan (0 - 100)** beserta label putusan:
  - 🟢 **Sangat Murah**: Harga jauh di bawah pasaran wajar (pastikan cek reputasi penjual dan fungsi fisik barang).
  - 🟢 **Worth It**: Penawaran yang bagus dan menguntungkan.
  - 🟡 **Wajar**: Harga sesuai dengan rata-rata/median pasar saat ini.
  - 🔴 **Kemahalan**: Harga di atas rata-rata pasar. Disarankan menawar atau mencari alternatif lain.
- **Estimasi Rentang Harga Wajar**: Rentang harga ideal untuk barang tersebut di pasar Indonesia saat ini.
- **Daftar Pembanding Nyata**: Rincian referensi harga yang digunakan sebagai acuan perbandingan (lengkap dengan sumber toko/pasar, status kondisi, dan tingkat kemiripan).

---

## 💻 Menjalankan Secara Lokal (Opsional)

Bagi Anda yang ingin menjalankan aplikasi ini di komputer sendiri untuk keperluan pengembangan atau pengujian:

### Prasyarat
- **Python** versi 3.11 atau lebih baru
- **Node.js** versi 18 atau lebih baru

### 1. Menjalankan Backend (FastAPI)
```powershell
# Masuk ke folder backend
cd backend

# Buat dan aktifkan virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Pasang dependensi
pip install -r requirements.txt

# Jalankan server API backend
python run.py
```
> Backend akan berjalan di `http://localhost:8000` (dokumentasi interaktif Swagger API di `http://localhost:8000/docs`).

### 2. Menjalankan Frontend (Next.js)
Buka jendela terminal baru:
```powershell
# Masuk ke folder frontend
cd frontend

# Pasang dependensi
npm install

# Jalankan server frontend
npm run dev
```
> Buka browser Anda dan akses `http://localhost:3000`.

---

## 🤝 Kontribusi & Saran

Aplikasi ini terus dikembangkan agar cakupan data hardware dan akurasi analisis semakin baik. Jika Anda memiliki saran perbaikan, model hardware baru yang ingin ditambahkan, atau menemukan bug:
1. Buat **Issue** baru pada repositori ini.
2. Kirimkan **Pull Request** dengan penjelasan perubahan yang Anda buat.

---

## 📄 Lisensi

Projek ini didistribusikan secara terbuka di bawah lisensi [MIT License](LICENSE).
