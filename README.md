# Atlas MT5 — Release 1.0

Atlas adalah dashboard lokal untuk memantau analisis teknikal MetaTrader 5 (MT5), data makro, dan jurnal sinyal. Analisis makro dengan Gemini bersifat opsional dan hanya berjalan saat diminta.

> **Peringatan risiko:** Informasi dan sinyal Atlas bukan nasihat keuangan atau jaminan hasil. Trading dapat menyebabkan kerugian. Uji strategi di akun demo dan periksa seluruh pengaturan sebelum digunakan pada akun riil.

## Fitur

- Dashboard lokal untuk memantau simbol, timeframe, kondisi pasar, dan sinyal.
- Penanda BUY/SELL pada grafik untuk sinyal yang tersimpan di jurnal lokal.
- Preset strategi trend dan scalping, dengan analisis timeframe lebih tinggi.
- Halaman **Analisis Mandiri** dengan kalender ekonomi publik dan indikator makro dari FRED.
- Analisis makro Gemini opsional, menggunakan konfigurasi backend.
- Jurnal sinyal lokal dan fitur backtest yang tersedia di dashboard.
- Notifikasi Telegram opsional.
- Order sesuai sinyal dan entry manual di luar sinyal tersedia setelah order diizinkan saat aplikasi dijalankan. Entry manual wajib memakai SL/TP dan tetap dibatasi risiko serta konfirmasi.
- Auto Pilot dimulai dalam keadaan **OFF** dan hanya tersedia jika diizinkan saat aplikasi dijalankan.

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

Launcher default menjaga order manual tetap nonaktif. Untuk mengizinkan entry manual BUY/SELL tanpa sinyal strategi, jalankan monitor dari PowerShell secara interaktif dengan `--enable-order-sending`:

```powershell
python .\pro_regime_structure.py `
  --symbol XAUUSD.m `
  --timeframe M5 `
  --higher-timeframe M15 `
  --mode scalping `
  --terminal "C:\Program Files\MetaTrader 5\terminal64.exe" `
  --web `
  --enable-order-sending
```

Saat diminta, ketik persis `ENABLE LIVE ORDERS`. Setelah dashboard terbuka, isi volume, SL, dan TP, lalu pilih **Open BUY manual** atau **Open SELL manual** dan tinjau konfirmasi. Order manual tidak memerlukan sinyal, tetapi tetap harus lolos validasi SL/TP, spread, margin, dan batas risiko akun. Fitur ini mengirim order ke akun MT5 yang sedang login; mulai dari akun demo.

## Order dan keamanan

- Dashboard hanya mendengarkan pada `127.0.0.1` (localhost); jangan mengeksposnya ke internet atau jaringan publik.
- Launcher mengaktifkan ketersediaan Auto Pilot, tetapi Auto Pilot **dimulai OFF**. Jangan aktifkan kecuali Anda memahami risikonya dan telah memeriksa akun, batas risiko, serta pengaturan strategi.
- Entry manual di luar sinyal hanya tersedia setelah `--enable-order-sending` dan konfirmasi eksplisit di terminal. SL/TP, validasi risiko, serta konfirmasi dashboard tetap diwajibkan. Jangan mengandalkan sinyal sebagai pengganti keputusan dan pengelolaan risiko Anda sendiri.
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
