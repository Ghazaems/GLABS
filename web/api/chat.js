// Vercel serverless function (Node.js runtime).
// Taruh API key Gemini di Vercel: Project Settings -> Environment Variables -> GEMINI_API_KEY
// JANGAN taruh API key di kode/frontend.

const SYSTEM_INSTRUCTION = `Kamu adalah asisten dashboard saham "Morning Ghazker" (GLABS).
Kamu punya akses ke data screening watchlist (harga terakhir, trend, Wyckoff, VWAP mingguan,
comparative strength vs IHSG, skor komposit, dan sinyal beli/pantau/jual) untuk saham-saham
IDX yang dipantau sistem ini.

ATURAN:
- Tanggal sesi ditentukan screening_session_date. Harga/sinyal hanya terkini jika last_price_date valid dan sama persis dengan sesi itu. Tanggal hilang, berbeda, atau masa depan adalah historis/tidak terverifikasi; jangan menyebutnya sinyal beli hari ini.
- Field tanpa suffix (score, signal, trend, support, resistance, wyckoff_bias/phase) adalah Weekly, bukan Daily. Gunakan horizons.daily/weekly/swing untuk horizon terkait. Jika tidak tersedia, nyatakan belum tersedia; jangan mengganti Daily/Swing dengan Weekly.
- Kalau pertanyaan menyangkut ticker atau data yang ada di watchlist, jawab berdasarkan data
  JSON yang diberikan dan sebut angka spesifiknya (skor, breakdown, dsb). Jangan mengarang
  angka yang tidak ada di data.
- Kalau pertanyaan di luar data ini (pengetahuan umum, saham lain di luar watchlist, dll),
  boleh dijawab pakai pengetahuan umum, tapi sebutkan jelas bahwa itu bukan dari data
  screening sistem ini.
- Jawab singkat, jelas, bahasa Indonesia santai tapi informatif. Hindari jawaban bertele-tele.
- Ini decision-support, bukan sinyal eksekusi otomatis atau rekomendasi investasi resmi -
  ingatkan itu kalau relevan (misalnya saat user menanyakan apakah harus beli/jual).`;

const MODEL = "gemini-3.5-flash-lite";
// Two attempts fit inside the explicitly configured 60s function budget.
const REQUEST_TIMEOUT_MS = 22_000;
const MAX_ATTEMPTS = 2;
const MAX_QUESTION_CHARS = 2000;
const MAX_WATCHLIST_ITEMS = 40;
const MAX_FILE_BASE64_CHARS = 3_900_000;
const ALLOWED_FILE_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/webp",
  "application/pdf",
  "text/plain",
]);

function currentPrice(row,session) {
  const valid=value=>typeof value==="string" && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(value+"T00:00:00Z")) && new Date(value+"T00:00:00Z").toISOString().slice(0,10)===value;
  return valid(session)&&valid(row.last_price_date)&&session===row.last_price_date;
}
function compactHorizon(value) {
  if(!value||typeof value!=="object")return null;
  const scalar=v=>typeof v==="number"&&Number.isFinite(v)?v:typeof v==="string"?v.slice(0,120):null;
  return Object.fromEntries(["score","signal","trend","support","resistance","wyckoff_bias","wyckoff_phase","score_breakdown"].map(k=>[k,
    k==="score_breakdown" && value[k] && typeof value[k]==="object"
      ? Object.fromEntries(Object.entries(value[k]).slice(0,12).map(([key,v])=>[key.slice(0,40),scalar(v)]))
      : scalar(value[k])]));
}
function compactRow(row,session) {
  if (!row || typeof row !== "object") return null;
  return {
    ticker: row.ticker,
    horizons: Object.fromEntries(["daily","weekly","swing"].map(h=>[h,compactHorizon(row.horizons?.[h])])),
    trend: row.trend,
    support: row.support,
    resistance: row.resistance,
    wyckoff_bias: row.wyckoff_bias,
    wyckoff_phase: row.wyckoff_phase,
    last_price_date: row.last_price_date,
    is_current_session: currentPrice(row,session),
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
      reasons: Array.isArray(row.vwap_analysis.reasons) ? row.vwap_analysis.reasons.slice(0, 4).map(x => String(x).slice(0, 240)) : [],
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

  if (new TextEncoder().encode(JSON.stringify(req.body || {})).byteLength > 4_000_000) {
    res.status(413).json({ error: "Permintaan melebihi batas aman 4 MB.", code: "payload_too_large" });
    return;
  }
  const { question, watchlist, generated_at, file, screening_session_date, market_data_date, current_style } = req.body || {};
  if (!question || typeof question !== "string" || !question.trim()) {
    res.status(400).json({ error: "Pertanyaan kosong." });
    return;
  }
  if (question.length > MAX_QUESTION_CHARS) {
    res.status(413).json({ error: "Pertanyaan terlalu panjang." });
    return;
  }

  const rows = (Array.isArray(watchlist) ? watchlist : [])
    .filter((row) => row && typeof row.ticker === "string");
  const words = new Set(question.toUpperCase().match(/[A-Z0-9]+/g) || []);
  const matched = rows.filter((row) => words.has(row.ticker.toUpperCase().replace(/\.JK$/, "")));
  const greeting = /^(halo|hai|hi|hello|tes|test)\s*[!.?]*$/i.test(question.trim());
  const selected = greeting ? [] : (matched.length ? matched : rows);
  const compactWatchlist = selected.slice(0, MAX_WATCHLIST_ITEMS).map(row=>compactRow(row,screening_session_date)).filter(Boolean);
  // Explicit scope: a compact sample must never be presented as the complete market.
  const suppliedTotal = Number(req.body?.scope?.total_rows);
  const scope = {
    total_rows: Number.isInteger(suppliedTotal) && suppliedTotal >= rows.length && suppliedTotal <= 10000 ? suppliedTotal : rows.length,
    selected_rows: compactWatchlist.length,
    selection: greeting ? "tanpa data saham" : matched.length ? "ticker yang disebut" : "sampel awal, bukan ranking seluruh pasar",
    truncated: selected.length > compactWatchlist.length || req.body?.scope?.truncated === true,
  };
  const rawSummary=req.body?.summary || {}, count = value => Number.isInteger(value) && value>=0 && value<=10000 ? value : null;
  const summary={processed:count(rawSummary.processed),current_rows:count(rawSummary.current_rows),historical_rows:count(rawSummary.historical_rows),
    signal_counts:Object.fromEntries(["daily","weekly","swing"].map(h=>[h,Object.fromEntries(["beli","pantau","jual"].map(k=>[k,count(rawSummary.signal_counts?.[h]?.[k])]))])),
    note:"Agregat dashboard mencakup data historis; jangan disamakan dengan sinyal baru sesi terkini."};
  const dataBlock = `Data watchlist (digenerate ${generated_at || "tidak diketahui"}):\n` +
    JSON.stringify({ scope, summary, screening_session_date, market_data_date, current_style, rows: compactWatchlist }) +
    "\nJika data hanya sampel, jangan menyimpulkan ranking/jumlah seluruh pasar dari sampel. Nyatakan keterbatasan data." +
    "\nJika selection adalah tanpa data saham, data sengaja tidak dilampirkan untuk sapaan/tes; jangan mengatakan dashboard atau watchlist kosong.";

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

  const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`;
  const body = JSON.stringify({ contents: [{ parts }], generationConfig: {
    maxOutputTokens: 1536, thinkingConfig: { thinkingLevel: "minimal" },
  } });
  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const geminiRes = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-goog-api-key": apiKey },
        body,
        signal: controller.signal,
      });
      const json = await geminiRes.json().catch(() => ({}));
      if (!geminiRes.ok) {
        const temporary = [502, 503, 504].includes(geminiRes.status);
        if (temporary && attempt + 1 < MAX_ATTEMPTS) {
          clearTimeout(timer);
          await new Promise((resolve) => setTimeout(resolve, 600));
          continue;
        }
        const code = geminiRes.status === 429 ? "quota_exceeded"
          : temporary ? "provider_busy" : "provider_error";
        const error = code === "quota_exceeded"
          ? "Batas pemakaian Gemini tercapai. Tunggu kuota tersedia kembali atau cek limit proyek di AI Studio."
          : code === "provider_busy"
          ? "Gemini masih sibuk setelah dicoba ulang sekali. Silakan coba beberapa saat lagi."
          : "Gemini menolak permintaan. Periksa akses model dan konfigurasi API di server.";
        res.status(geminiRes.status).json({ error, code, model: MODEL });
        return;
      }
      const answer = (json?.candidates?.[0]?.content?.parts || [])
        .filter((part) => !part.thought && typeof part.text === "string")
        .map((part) => part.text).join("\n").trim();
      if (!answer) {
        res.status(502).json({ error: "Gemini tidak mengembalikan jawaban teks. Coba pertanyaan lain.", code: "empty_response" });
        return;
      }
      res.status(200).json({ answer, model: MODEL });
      return;
    } catch (err) {
      // A connection reset or timeout is transient too, not just HTTP 5xx.
      if (attempt + 1 < MAX_ATTEMPTS) {
        clearTimeout(timer);
        await new Promise((resolve) => setTimeout(resolve, 600));
        continue;
      }
      // Never return fetch errors containing credentials or upstream request URLs.
      res.status(err.name === "AbortError" ? 504 : 502).json({
        error: err.name === "AbortError"
          ? "AI terlalu lama merespons. Silakan coba lagi."
          : "Koneksi ke Gemini gagal. Silakan coba lagi.",
        code: err.name === "AbortError" ? "provider_timeout" : "provider_network",
      });
      return;
    } finally {
      clearTimeout(timer);
    }
  }
};

module.exports.config = { maxDuration: 60 };
