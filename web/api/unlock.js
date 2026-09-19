// Vercel serverless function (Node.js runtime): POST /api/unlock  { "code": "1234" }
// Env vars (Vercel -> Project Settings -> Environment Variables):
//   ACCESS_CODE     kode akses 4 karakter, contoh: 8586
//   SESSION_SECRET  teks acak panjang (dipakai menandatangani cookie sesi)
// Mengganti SESSION_SECRET = semua sesi yang sedang login langsung tidak berlaku.

const crypto = require("crypto");

const SESSION_DAYS = 30;

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  if (req.method !== "POST") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const accessCode = process.env.ACCESS_CODE;
  const secret = process.env.SESSION_SECRET;
  if (!accessCode || !secret) {
    res.status(500).json({ error: "ACCESS_CODE / SESSION_SECRET belum diset di environment variables Vercel." });
    return;
  }

  let body = req.body;
  if (typeof body === "string") {
    try { body = JSON.parse(body); } catch (e) { body = {}; }
  }
  const given = body && typeof body.code === "string" ? body.code : "";

  // bandingkan lewat hash supaya waktu proses tidak membocorkan isi kode
  const a = crypto.createHash("sha256").update(given).digest();
  const b = crypto.createHash("sha256").update(accessCode).digest();
  if (!crypto.timingSafeEqual(a, b)) {
    res.status(401).json({ ok: false });
    return;
  }

  const exp = Math.floor(Date.now() / 1000) + SESSION_DAYS * 86400;
  const sig = crypto.createHmac("sha256", secret).update(String(exp)).digest("hex");
  res.setHeader(
    "Set-Cookie",
    `gk_session=${exp}.${sig}; Path=/; Max-Age=${SESSION_DAYS * 86400}; HttpOnly; Secure; SameSite=Lax`
  );
  res.status(200).json({ ok: true });
};
