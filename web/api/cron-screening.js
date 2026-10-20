// Vercel Cron -> GitHub Actions workflow_dispatch untuk screening harian.
//
// Kenapa ada: cron GitHub Actions bersifat best-effort dan sering di-drop
// (terbukti hanya 1-2 dari 16 slot per hari yang benar-benar jalan), sehingga
// data sering baru terbit malam. Endpoint ini memberi pemicu yang dijamin
// jalan pada jam tetap, lalu workflow tetap memakai gate freshness sendiri
// (idempoten: kalau sesi sudah lengkap, run hanya skip dan tidak menulis ulang).
//
// Env vars di Vercel (Project Settings -> Environment Variables):
//   CRON_SECRET        teks acak panjang; Vercel mengirimnya sebagai Bearer
//   GH_DISPATCH_TOKEN  fine-grained PAT: Actions = write, Contents = read, repo GLABS saja
// Tanpa keduanya endpoint menjawab 503 dan tidak melakukan apa pun.
//
// Catatan: cron hanya memicu; tidak mengubah skor, ticker, atau histori.

const crypto = require("node:crypto");

const REPO = "Ghazaems/GLABS";
const WORKFLOW = "daily-screening.yml";
const GITHUB_API = "https://api.github.com";

function safeEqual(left, right) {
  const a = Buffer.from(String(left));
  const b = Buffer.from(String(right));
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

function bearer(req) {
  const header = req.headers && req.headers.authorization;
  const match = /^Bearer (.+)$/.exec(typeof header === "string" ? header : "");
  return match ? match[1] : "";
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  if (req.method !== "GET") {
    res.status(405).json({ ok: false, error: "method_not_allowed" });
    return;
  }

  const secret = process.env.CRON_SECRET;
  const token = process.env.GH_DISPATCH_TOKEN;
  if (!secret || !token) {
    // Jangan pernah lanjut tanpa kredensial; jangan bocorkan nama env yang kosong.
    res.status(503).json({ ok: false, error: "cron_trigger_not_configured" });
    return;
  }

  if (!safeEqual(bearer(req), secret)) {
    res.status(401).json({ ok: false, error: "unauthorized" });
    return;
  }

  try {
    const response = await fetch(
      `${GITHUB_API}/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "Content-Type": "application/json",
          "User-Agent": "GLABS-cron-screening",
        },
        body: JSON.stringify({ ref: "main" }),
      }
    );
    if (response.status !== 204) {
      res.status(502).json({ ok: false, error: "github_dispatch_failed", status: response.status });
      return;
    }
  } catch (error) {
    res.status(502).json({ ok: false, error: "github_unreachable" });
    return;
  }

  res.status(200).json({ ok: true, dispatched: WORKFLOW, ref: "main" });
};
