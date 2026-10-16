// Offline chat regression tests: no real credentials, network calls or screening changes.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "../web/api/chat.js"), "utf8");
async function call(responses, question = "halo", watchlist = [], env = { GEMINI_API_KEY: "test-only" }, file) {
  const requests = [];
  const sandbox = {
    module: { exports: {} }, process: { env }, AbortController,
    setTimeout: (fn, ms) => ms === 600 ? setTimeout(fn, 0) : setTimeout(fn, ms),
    clearTimeout,
    fetch: async (url, options) => {
      requests.push({ url, options });
      const item = responses.shift();
      if (item instanceof Error) throw item;
      assert.ok(item, "unexpected extra retry");
      return { ok: item.status === 200, status: item.status, json: async () => item.json };
    },
  };
  vm.runInNewContext(source, sandbox);
  const res = { setHeader() {}, status(n) { this.code = n; return this; }, json(x) { this.data = x; } };
  await sandbox.module.exports({ method: "POST", body: { question, watchlist, file } }, res);
  return { res, requests };
}
const ok = () => ({ status: 200, json: { candidates: [{ content: { parts: [{text:"hidden",thought:true},{text:"Halo!"},{text:"Siap."}] } }] } });
(async () => {
  let r = await call([ok()]);
  assert.equal(r.res.code, 200);
  assert.equal(r.res.data.answer, "Halo!\nSiap.");
  assert.ok(r.requests[0].url.includes("/gemini-3.5-flash-lite:generateContent"));
  assert.ok(!r.requests[0].url.includes("test-only"));
  assert.equal(r.requests[0].options.headers["x-goog-api-key"], "test-only");
  r = await call([{status:503,json:{}},ok()]);
  assert.equal(r.requests.length, 2); assert.equal(r.res.code, 200);
  r = await call([{status:503,json:{}},{status:503,json:{}}]);
  assert.equal(r.requests.length, 2); assert.equal(r.res.data.code,"provider_busy");
  for (const status of [400,403,404,429]) {
    r = await call([{status,json:{}}]);
    assert.equal(r.requests.length,1); assert.equal(r.res.code,status);
    if(status===429) assert.equal(r.res.data.code,"quota_exceeded");
  }
  r = await call([new Error("SECRET request URL"),new Error("SECRET request URL")]);
  assert.equal(r.res.code,502); assert.ok(!JSON.stringify(r.res.data).includes("SECRET"));
  const aborted = new Error("abort"); aborted.name = "AbortError";
  r = await call([aborted,aborted]); assert.equal(r.res.data.code,"provider_timeout");
  assert.equal(r.requests.length,2);
  r = await call([aborted,ok()]); assert.equal(r.res.code,200);
  r = await call([new Error('reset'),ok()]); assert.equal(r.res.code,200);
  const generation = JSON.parse(r.requests[0].options.body).generationConfig;
  assert.equal(generation.thinkingConfig.thinkingLevel,'minimal');
  assert.equal(generation.maxOutputTokens,1536);
  r = await call([{status:200,json:{candidates:[]}}]); assert.equal(r.res.data.code,"empty_response");
  const rows = Array.from({length:600},(_,i)=>({ticker:"X"+i,last_close:i+1}));
  rows.push({ticker:"ANTM",last_close:3050,score_daily:12,last_price_date:"2026-10-14"});
  r = await call([ok()],"Analisis ANTM",rows);
  let prompt = JSON.parse(r.requests[0].options.body).contents[0].parts[0].text;
  assert.ok(prompt.includes('"ticker":"ANTM"')); assert.ok(!prompt.includes('"ticker":"X0"'));
  assert.ok(prompt.includes('"score_daily":12'));
  r = await call([ok()],"Ringkas pasar",rows);
  prompt = JSON.parse(r.requests[0].options.body).contents[0].parts[0].text;
  assert.ok(prompt.includes('"selected_rows":40')); assert.ok(prompt.includes('"truncated":true'));
  r = await call([ok()],"halo",rows);
  prompt = JSON.parse(r.requests[0].options.body).contents[0].parts[0].text;
  assert.ok(prompt.includes('"selected_rows":0'));
  r = await call([],"",[]); assert.equal(r.res.code,400); assert.equal(r.requests.length,0);
  r = await call([],"halo",[],{}); assert.equal(r.res.code,500); assert.equal(r.requests.length,0);
  r = await call([],"halo",[],undefined,{data:"a",mimeType:"text/csv"});
  assert.equal(r.res.code,413); assert.equal(r.requests.length,0);
  console.log("Chat model, bounded retry, quota, timeout, redaction, context and validation tests passed.");
})().catch(e=>{console.error(e);process.exitCode=1;});
