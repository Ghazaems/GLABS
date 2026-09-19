// Vercel Routing Middleware: jalan sebelum file statis & fungsi API.
// Tanpa cookie sesi yang valid:
//   - halaman (browser minta HTML)  -> ditampilkan gate.html (URL tetap sama)
//   - semua yang lain (JSON, JS, CSS, /api/chat) -> 401
// Dengan cookie valid: lanjut normal ke dashboard.

export const config = { matcher: "/((?!_vercel/).*)" };

// boleh dibuka tanpa login
const PUBLIC = new Set(["/gate.html", "/api/unlock", "/hero.mp4", "/favicon.ico"]);

const enc = new TextEncoder();

async function hmacHex(secret, message) {
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function safeEqual(a, b) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

async function hasSession(request) {
  const secret = process.env.SESSION_SECRET;
  if (!secret) return false; // belum dikonfigurasi = tertutup
  const m = (request.headers.get("cookie") || "").match(/(?:^|;\s*)gk_session=([^;]+)/);
  if (!m) return false;
  const [exp, sig] = m[1].split(".");
  if (!exp || !sig) return false;
  if (!(Number(exp) > Date.now() / 1000)) return false;
  return safeEqual(sig, await hmacHex(secret, exp));
}

const NO_STORE = { "cache-control": "private, no-store" };

export default async function middleware(request) {
  const url = new URL(request.url);
  const path = url.pathname;

  if (await hasSession(request)) {
    if (path === "/gate.html" || path === "/gate") {
      return new Response(null, { status: 307, headers: { location: "/", ...NO_STORE } });
    }
    return new Response(null, { headers: { "x-middleware-next": "1" } }); // lanjut
  }

  if (PUBLIC.has(path)) {
    return new Response(null, { headers: { "x-middleware-next": "1" } });
  }

  const wantsPage =
    request.method === "GET" && (request.headers.get("accept") || "").includes("text/html");
  if (wantsPage) {
    return new Response(null, {
      headers: { "x-middleware-rewrite": new URL("/gate.html", request.url).toString(), ...NO_STORE },
    });
  }

  return new Response(JSON.stringify({ error: "Unauthorized" }), {
    status: 401,
    headers: { "content-type": "application/json", ...NO_STORE },
  });
}
