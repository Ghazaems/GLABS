# Morning Ghazker — Quant Cockpit

Dashboard decision-support untuk menyaring saham IDX secara otomatis. Sistem menghitung trend, support/resistance, Wyckoff, VWAP, comparative strength terhadap IHSG, dan skor komposit. Keputusan serta eksekusi transaksi tetap dilakukan manusia.

## Menjalankan lokal

```powershell
pip install -r requirements.txt
python main.py
python -m http.server 8000 --directory web
```

Lalu buka `http://localhost:8000`.

## Fitur cockpit

- Klik ticker atau kartu analisis untuk membuka chart candlestick.
- Overlay VWAP, support/resistance, dan batas trading range.
- Marker serta penjelasan SC, BC, AR, ST, Spring, UT, SOS, SOW, LPS, dan LPSY.
- Tab Trend, VWAP, comparative strength vs IHSG, dan kontribusi skor.
- Checklist manual sebelum eksekusi; tidak ada auto-order atau koneksi broker.
- Pipeline otomatis mengekspor 180 candle terbaru per ticker ke dashboard.

## Otomatisasi

Workflow `.github/workflows/daily-screening.yml` menjalankan screening Senin–Jumat setelah bursa tutup dan memperbarui data dashboard. Detail deployment tersedia di `DEPLOY.md`.

## Batasan

Label Wyckoff bersifat heuristik dan interpretatif. Gunakan dashboard sebagai penyaring kandidat dan alat bantu keputusan, bukan rekomendasi investasi atau mesin eksekusi.
