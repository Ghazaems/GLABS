// Vercel serverless function (Node.js runtime).
// Taruh API key Gemini di Vercel: Project Settings -> Environment Variables -> GEMINI_API_KEY
// JANGAN taruh API key di kode/frontend.

const SYSTEM_INSTRUCTION = `Kamu adalah asisten dashboard saham "Morning Ghazker" (GLABS).
Kamu punya akses ke data screening watchlist (harga terakhir, trend, Wyckoff, VWAP mingguan,
comparative strength vs IHSG, skor komposit, dan sinyal beli/pantau/jual) untuk saham-saham
IDX yang dipantau sistem ini.

ATURAN:
- Kalau pertanyaan menyangkut ticker atau data yang ada di watchlist, jawab berdasarkan data
  JSON yang diberikan dan sebut angka spesifiknya (skor, breakdown, dsb). Jangan mengarang
  angka yang tidak ada di data.
- Kalau pertanyaan di luar data ini (pengetahuan umum, saham lain di luar watchlist, dll),
  boleh dijawab pakai pengetahuan umum, tapi sebutkan jelas bahwa itu bukan dari data
  screening sistem ini.
- Jawab singkat, jelas, bahasa Indonesia santai tapi informatif. Hindari jawaban bertele-tele.
- Ini decision-support, bukan sinyal eksekusi otomatis atau rekomendasi investasi resmi -
  ingatkan itu kalau relevan (misalnya saat user menanyakan apakah harus beli/jual).`;

const MODEL = "gemini-3.6-flash";
const MAX_QUESTION_CHARS = 2000;
const MAX_WATCHLIST_ITEMS = 500;
const MAX_FILE_BASE64_CHARS = 6_000_000;
const ALLOWED_FILE_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/webp",
  "application/pdf",
  "text/plain",
]);

function compactRow(row) {
  if (!row || typeof row !== "object") return null;
  return {
    ticker: row.ticker,
    last_price_date: row.last_price_date,
    last_close: row.last_close,
    signal_daily: row.signal_daily,
    signal: row.signal,
    signal_swing: row.signal_swing,
    vwap_signal: row.vwap_signal,
    vwap_analysis: row.vwap_analysis && {
      status: row.vwap_analysis.status,
      signal: row.vwap_analysis.signal,
      regime: row.vwap_analysis.regime,
      protective_stop: row.vwap_analysis.protective_stop,
      reasons: row.vwap_analysis.reasons,
    },
    score_daily: row.score_daily,
    score: row.score,
    score_swing: row.score_swing,
  };
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "private, no-store");
  res.setHeader("X-Content-Type-Options", "nosniff");
  if (req.method !== "POST") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    res.status(500).json({ error: "GEMINI_API_KEY belum diset di environment variables Vercel." });
    return;
  }

  const { question, watchlist, generated_at, file } = req.body || {};
  if (!question || typeof question !== "string" || !question.trim()) {
    res.status(400).json({ error: "Pertanyaan kosong." });
    return;
  }
  if (question.length > MAX_QUESTION_CHARS) {
    res.status(413).json({ error: "Pertanyaan terlalu panjang." });
    return;
  }

  const compactWatchlist = (
    Array.isArray(watchlist) ? watchlist : []
  ).slice(0, MAX_WATCHLIST_ITEMS).map(compactRow).filter(Boolean);

  const dataBlock = `Data watchlist (digenerate ${generated_at || "tidak diketahui"}):\n` +
    JSON.stringify(compactWatchlist);

  const prompt = `${SYSTEM_INSTRUCTION}\n\n${dataBlock}\n\nPertanyaan user: ${question}`;

  const parts = [{ text: prompt }];
  if (file && typeof file.data === "string" && typeof file.mimeType === "string") {
    if (
      file.data.length > MAX_FILE_BASE64_CHARS
      || !ALLOWED_FILE_TYPES.has(file.mimeType)
    ) {
      res.status(413).json({ error: "File terlalu besar atau tipe tidak diizinkan." });
      return;
    }
    parts.push({ inlineData: { mimeType: file.mimeType, data: file.data } });
  }

  const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${apiKey}`;

  try {
    const geminiRes = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contents: [{ parts }] }),
    });

    const json = await geminiRes.json();

    if (!geminiRes.ok) {
      res.status(geminiRes.status).json({
        error: json?.error?.message || "Gagal memanggil Gemini API.",
      });
      return;
    }

    const answer = json?.candidates?.[0]?.content?.parts?.[0]?.text
      || "Maaf, tidak ada jawaban dari AI.";
    res.status(200).json({ answer });
  } catch (err) {
    res.status(500).json({ error: err.message || "Terjadi kesalahan server." });
  }
};
