# Deploy — 100% Gratis

## 1. Push ke GitHub
```
cd stock-screener
git init
git add .
git commit -m "initial commit"
gh repo create stock-screener --private --source=. --push
# atau bikin repo manual di github.com lalu:
# git remote add origin <url-repo-kamu>
# git push -u origin main
```

## 2. Cron job otomatis (sudah dikonfigurasi)
File `.github/workflows/daily-screening.yml` sudah ada — otomatis jalan
target pertama tiap Senin-Jumat jam 16:15 WIB (GitHub dapat terlambat), generate `web/dashboard_data.json` baru,
lalu commit balik ke repo. Gratis (GitHub Actions free tier: 2000 menit/bulan
untuk repo privat, unlimited untuk repo publik).

Test manual dulu tanpa nunggu jadwal:
GitHub repo -> tab **Actions** -> pilih "Daily Stock Screening" -> **Run workflow**

## 3. Hosting dashboard (pilih salah satu)

### Opsi A — GitHub Pages (paling simpel, satu ekosistem)
1. Repo -> **Settings** -> **Pages**
2. Source: **Deploy from branch** -> branch `main` -> folder `/web`
3. Selesai. URL: `https://<username>.github.io/stock-screener/`
4. Karena Actions commit `dashboard_data.json` ke repo yang sama, Pages
   otomatis serve data terbaru tanpa rebuild manual.

### Opsi B — Vercel/Netlify (kalau nanti mau custom domain/lebih cepat)
1. Import repo di vercel.com atau netlify.com
2. Root directory: `web`
3. Build command: `node build-data.cjs` (diatur oleh `web/vercel.json`; menghasilkan ringkasan ringan dan histori lazy-load)
4. Deploy otomatis tiap kali ada push baru ke `main`

## Catatan penting
- `storage/screener.db` ikut ter-commit tiap hari (histori sinyal). Kalau
  database makin besar dan bikin repo berat, pertimbangkan pindah ke
  Supabase/Postgres free tier nanti — bukan masalah mendesak di awal.
- Kalau workflow gagal (misal yfinance rate-limit/berubah struktur), GitHub
  otomatis kirim email notifikasi ke kamu — jadi tidak akan gagal diam-diam.

## Pemicu screening yang andal (opsional, disarankan)
Cron GitHub Actions bersifat best-effort: pada repo ini hanya 1-2 dari 16 slot
per hari yang benar-benar jalan, dan sering baru malam WIB. Untuk target 16:15 WIB,
aktifkan pemicu dari Vercel:

1. Buat fine-grained PAT (GitHub -> Settings -> Developer settings) untuk repo
   `Ghazaems/GLABS` dengan izin **Actions: write** dan **Contents: read**.
2. Vercel -> project `glabs-ghazaems` -> Settings -> Environment Variables:
   - `GH_DISPATCH_TOKEN` = PAT di atas
   - `CRON_SECRET` = teks acak panjang
3. Deploy ulang. `web/vercel.json` sudah menjadwalkan `/api/cron-screening`
   setiap hari 09:20 UTC (16:20 WIB). Endpoint hanya memicu `workflow_dispatch`;
   gate freshness di workflow tetap menentukan perlu-tidaknya screening.

Tanpa kedua env var, endpoint menjawab 503 dan tidak melakukan apa pun.

- `idx_fetcher.py` masih stub, belum masuk pipeline otomatis — aman untuk
  dijalankan cron sekarang, cuma belum ada data sentimen berita.
