// Offline tests for the Vercel Cron -> GitHub workflow_dispatch trigger.
// No real credentials, network calls or screening changes.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../web/api/cron-screening.js"), "utf8");

async function call({ method = "GET", authorization, env = {}, reply = { status: 204 }, throwError } = {}) {
  const requests = [];
  const sandbox = {
    module: { exports: {} },
    process: { env },
    Buffer,
    console,
    require,
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (throwError) throw throwError;
      return { status: reply.status };
    },
  };
  vm.runInNewContext(source, sandbox);
  const res = {
    headers: {},
    setHeader(name, value) { this.headers[name.toLowerCase()] = value; },
    status(code) { this.code = code; return this; },
    json(body) { this.data = body; },
  };
  await sandbox.module.exports({ method, headers: authorization ? { authorization } : {} }, res);
  return { res, requests };
}

(async () => {
  const env = { CRON_SECRET: "test-only-secret", GH_DISPATCH_TOKEN: "test-only-token" };

  let r = await call({ method: "POST", env, authorization: "Bearer test-only-secret" });
  assert.equal(r.res.code, 405);
  assert.equal(r.requests.length, 0);

  r = await call({ env: {} });
  assert.equal(r.res.code, 503);
  assert.equal(r.requests.length, 0);

  r = await call({ env: { CRON_SECRET: "test-only-secret" } });
  assert.equal(r.res.code, 503);

  r = await call({ env, authorization: "Bearer wrong" });
  assert.equal(r.res.code, 401);
  assert.equal(r.requests.length, 0);

  r = await call({ env });
  assert.equal(r.res.code, 401);

  r = await call({ env, authorization: "Bearer test-only-secret" });
  assert.equal(r.res.code, 200);
  assert.equal(r.res.data.dispatched, "daily-screening.yml");
  assert.equal(r.requests.length, 1);
  assert.equal(
    r.requests[0].url,
    "https://api.github.com/repos/Ghazaems/GLABS/actions/workflows/daily-screening.yml/dispatches"
  );
  assert.equal(r.requests[0].options.method, "POST");
  assert.equal(JSON.parse(r.requests[0].options.body).ref, "main");
  assert.equal(r.requests[0].options.headers.Authorization, "Bearer test-only-token");
  assert.ok(!JSON.stringify(r.res.data).includes("test-only"));

  r = await call({ env, authorization: "Bearer test-only-secret", reply: { status: 403 } });
  assert.equal(r.res.code, 502);
  assert.equal(r.res.data.status, 403);
  assert.ok(!JSON.stringify(r.res.data).includes("test-only"));

  r = await call({ env, authorization: "Bearer test-only-secret", throwError: new Error("network down") });
  assert.equal(r.res.code, 502);
  assert.equal(r.res.data.error, "github_unreachable");

  const vercel = JSON.parse(fs.readFileSync(path.join(__dirname, "../web/vercel.json"), "utf8"));
  assert.deepEqual(vercel.crons, [{ path: "/api/cron-screening", schedule: "20 9 * * *" }]);
  const middleware = fs.readFileSync(path.join(__dirname, "../web/middleware.js"), "utf8");
  const publicSet = (middleware.match(/const PUBLIC = new Set\(\[([^\]]*)\]\)/) || [])[1] || "";
  assert.ok(publicSet.includes('"/api/cron-screening"'), "cron endpoint must bypass the session gate");
  assert.ok(!publicSet.includes('"/api/chat"'), "chat stays behind the gate");

  console.log("Cron screening trigger: auth, dispatch, failure and deploy wiring passed.");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
