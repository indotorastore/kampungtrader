# Atlas MT5 — Release 1.0

Atlas adalah dashboard lokal untuk memantau analisis teknikal MetaTrader 5 (MT5), data makro, dan jurnal sinyal. Analisis makro dengan Gemini bersifat opsional dan hanya berjalan saat diminta.

> **Peringatan risiko:** Informasi dan sinyal Atlas bukan nasihat keuangan atau jaminan hasil. Trading dapat menyebabkan kerugian. Uji strategi di akun demo dan periksa seluruh pengaturan sebelum digunakan pada akun riil.

## Fitur

- Dashboard lokal untuk memantau simbol, timeframe, kondisi pasar, dan sinyal.
- Pemindai scalping eksperimental memakai pullback EMA, pemicu candle, momentum RSI, arah MTF, dan jeda tiga candle M5 untuk meredam sinyal berulang. Aturan ini belum terbukti menguntungkan; jangan gunakan untuk order live sebelum hasil uji out-of-sample yang memadai.
- Panah BUY/SELL historis dihitung ulang hanya untuk timeframe chart terpilih. Panah BUY berada di bawah candle, SELL di atasnya; order tereksekusi memakai marker kotak. Preview LIVE pada candle berjalan ditandai terpisah dan dapat hilang sebelum candle ditutup.
- Setup BUY/SELL menampilkan Entry, SL, TP1, TP2, dan TP3 pada panel level dan grafik. Target berbasis risiko: trend 1R/2R/3R, scalping 0,8R/1,2R/1,6R. Saat mengirim order sesuai sinyal, MT5 tetap menerima TP2 sebagai satu-satunya take-profit; TP1 dan TP3 adalah level rekomendasi, bukan partial exit otomatis.
- Skor konfluensi BUY/SELL bukan probabilitas profit. Scalping tetap manual-only; keputusan order berada pada trader.
- Preset strategi trend dan scalping, dengan analisis timeframe lebih tinggi.
- Halaman **Analisis Mandiri** dengan kalender ekonomi publik dan indikator makro dari FRED.
- Analisis makro Gemini opsional, menggunakan konfigurasi backend.
- Jurnal sinyal lokal dan fitur backtest yang tersedia di dashboard.
- Notifikasi Telegram opsional.
- Order manual di luar sinyal tersedia selama terminal mengizinkan trading; tidak memerlukan flag startup. SL dan TP opsional, tetapi jika SL tidak dipasang potensi risiko tidak dibatasi.
- Posisi terbuka dipantau terhadap setup candle tertutup pada simbol/timeframe terpilih. Analisis BUY/SELL atau WATCH yang berlawanan menampilkan peringatan untuk mengevaluasi/menutup posisi; Atlas tidak menutup posisi otomatis. SL rekomendasi memakai ATR dan, bila tersedia, swing terkonfirmasi dengan buffer ATR; TP memakai kelipatan jarak risiko Entry–SL, sehingga level mengikuti volatilitas dan struktur SL.
- Auto Pilot dimulai dalam keadaan **OFF** dan hanya tersedia jika diizinkan saat aplikasi dijalankan; mode scalping selalu manual-only.
- Level TP1/TP2/TP3 adalah rekomendasi berbasis jarak Entry–SL dan bukan jaminan bahwa target akan tercapai. Order sesuai sinyal tetap memakai TP2; backtest juga mengevaluasi exit TP2, bukan urutan target bertahap.

## Persyaratan

- Windows dan MetaTrader 5 desktop yang sudah terpasang serta login ke akun.
- Python 3.10 atau lebih baru, dengan paket yang tercantum di [`requirements.txt`](./requirements.txt).
- Simbol broker yang ingin dianalisis, misalnya `XAUUSD.m`; nama simbol harus sesuai dengan yang tersedia di MT5.
- Koneksi internet untuk feed kalender ekonomi, data FRED, dan layanan Gemini opsional.

## Instalasi

1. Unduh atau clone repository ini.
2. Pastikan terminal MT5 sudah terpasang dan login.
3. Dari PowerShell pada folder project, pasang dependensi:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. (Opsional) Siapkan konfigurasi Gemini lokal:

   ```powershell
   Copy-Item .env.example .env
   ```

   Isi `GEMINI_API_KEY` dan, jika diperlukan, `GEMINI_MODEL` di `.env`. Simpan file ini secara privat—jangan unggah atau bagikan API key. Akses Gemini bergantung pada ketersediaan model, kuota, dan izin project Google.

## Menjalankan

Launcher Windows **Mulai Atlas.bat** memulai monitor dan dashboard dengan konfigurasi default project, lalu membuka browser di `http://127.0.0.1:8765/`. Launcher saat ini mengharapkan Python di `C:\Python314\python.exe` dan MT5 di `C:\Program Files\MetaTrader 5\terminal64.exe`; jika lokasi di komputer Anda berbeda, sesuaikan nilai tersebut di file `.bat`.

Alternatifnya, jalankan dari PowerShell dengan path terminal dan simbol yang sesuai:

```powershell
python .\pro_regime_structure.py `
  --symbol XAUUSD.m `
  --timeframe M5 `
  --higher-timeframe M15 `
  --mode scalping `
  --terminal "C:\Program Files\MetaTrader 5\terminal64.exe" `
  --web
```

Buka dashboard di `http://127.0.0.1:8765/` atau halaman analisis mandiri di `http://127.0.0.1:8765/analyst`. Tekan `Ctrl+C` pada jendela proses untuk menghentikan monitor.

### Entry manual di luar sinyal

Tombol **Open BUY manual** dan **Open SELL manual** tersedia tanpa `--enable-order-sending` dan tanpa setup sinyal. Isi volume; SL dan TP boleh dikosongkan atau diisi satu per satu. Jika SL diisi, levelnya tetap melewati validasi sisi harga dan batas risiko. **Tanpa SL, potensi rugi tidak dibatasi oleh Atlas**; tanpa TP, posisi tidak memiliki take-profit. Untuk aksi cepat, mode scalping pada akun **DEMO** mengirim order buka dan tutup tanpa dialog konfirmasi. Di mode lain atau akun LIVE, dialog konfirmasi tetap ditampilkan. Pastikan terminal MT5 yang sedang login benar-benar akun demo.

## Order dan keamanan

- Dashboard hanya mendengarkan pada `127.0.0.1` (localhost); jangan mengeksposnya ke internet atau jaringan publik.
- Launcher mengaktifkan ketersediaan Auto Pilot, tetapi Auto Pilot **dimulai OFF**. Jangan aktifkan kecuali Anda memahami risikonya dan telah memeriksa akun, batas risiko, serta pengaturan strategi.
- Order manual dan penutupan posisi dari dashboard tidak memerlukan flag startup; terminal/akun tetap harus mengizinkan trading. Dialog konfirmasi dilewati hanya untuk mode scalping pada akun DEMO; mode lain dan akun LIVE tetap meminta konfirmasi. SL/TP manual opsional. Tanpa SL, kerugian dapat melampaui batas risiko apa pun yang ditampilkan karena tidak ada batas SL pada order. Posisi tidak ditutup otomatis saat ada peringatan perubahan tren.
- File `.env` berisi rahasia dan dikecualikan dari Git. Jangan pernah menambahkan API key, data akun, log, atau database pribadi ke commit publik.
- Data makro dapat tertunda dan feed publik dapat berubah atau tidak tersedia. Periksa sumber dan waktu observasi sebelum menggunakannya.

## Struktur utama

| File | Keterangan |
| --- | --- |
| `pro_regime_structure.py` | Monitor MT5, server dashboard lokal, analisis, dan API backend. |
| `dashboard.html` | Dashboard pemantauan dan kontrol. |
| `analyst.html` | Halaman analisis mandiri, kalender, dan data makro. |
| `PemulaTrendPullback.mq5` | Source indikator MT5. |
| `Mulai Atlas.bat` | Launcher Windows. |
| `test_pro_regime_structure.py` | Pengujian unit dan regresi backend. |
| `.env.example` | Contoh konfigurasi Gemini tanpa API key. |
