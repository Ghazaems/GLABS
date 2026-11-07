// Deterministic deployment assets, built from committed, validated publications.
// Original audit feeds, every ticker and all price history remain untouched.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const encode = value => JSON.stringify(value);
function compact(value) {
  if (Array.isArray(value)) return value.map(compact);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.entries(value).filter(([key]) => key !== 'price_history')
    .map(([key, item]) => [key, compact(item)]));
}
function build(web = __dirname, io = {}) {
  const write = io.write || ((relative, data) => {
    const output = path.join(web, relative);
    fs.mkdirSync(path.dirname(output), { recursive: true });
    fs.writeFileSync(output, encode(data));
  });
  const read = io.read || (name => {
    const bytes = fs.readFileSync(path.join(web, name));
    return { data: JSON.parse(bytes), sha: hash(bytes), bytes: bytes.length };
  });
  const dashboard = read('dashboard_data.json');
  if (!Array.isArray(dashboard.data.watchlist) || !dashboard.data.market_data_date)
    throw Error('Dashboard publication invalid; refusing UI build');
  const prefix = `ui-data/${dashboard.sha}`;
  const overview = compact(dashboard.data);
  for (const row of dashboard.data.watchlist) {
    if (!/^[A-Z0-9_-]+$/.test(row.ticker)) throw Error('Invalid ticker path');
    write(`${prefix}/stocks/${row.ticker}.json`, {
      source_sha256: dashboard.sha, market_data_date: dashboard.data.market_data_date, stock: row,
    });
  }
  const assets = { schema_version: 1, dashboard_sha256: dashboard.sha,
    details_base: `${prefix}/stocks/` };
  const activity = read('purbaya_activity_data.json');
  const { stocks, provider, method_version, market_data_date, generated_at } = activity.data;
  const metadata = { provider, method_version, market_data_date, generated_at };
  const activityBase = `ui-data/${activity.sha}/activity/`;
  for (const [ticker, item] of Object.entries(stocks || {})) {
    if (!/^[A-Z0-9_-]+$/.test(ticker)) throw Error('Invalid activity path');
    write(`${activityBase}${ticker}.json`, { ...metadata, source_sha256: activity.sha,
      stocks: { [ticker]: item } });
  }
  assets.activity_base = activityBase;
  assets.activity_sha256 = activity.sha;
  assets.activity_session = activity.data.market_data_date;
  // The rotation UI consumes the weekly base, then recalculates custom settings.
  // Other modes stay in the original audit feed, not downloaded three times.
  const rotation = read('sector_rotation_data.json');
  const reduced = { ...rotation.data, modes: { weekly: rotation.data.modes.weekly } };
  for (const kind of ['sectors', 'stocks']) {
    reduced.modes.weekly[kind] = reduced.modes.weekly[kind].map(row => {
      const { history, ...rest } = row;
      const { chart_history, ...fields } = rest;
      return { ...fields, packed_history: (chart_history || history || []).map(r => [r.date, r.close, r.benchmark]) };
    });
  }
  assets.rotation = `ui-data/${rotation.sha}/rotation.json`;
  write(assets.rotation, reduced);
  const extended = read('rotation_history_data.json');
  assets.rotation_history = `ui-data/${extended.sha}/rotation-history.json`;
  write(assets.rotation_history, extended.data);
  overview.ui_assets = assets;
  write('dashboard_overview.json', overview);
  const result = { original_bytes: dashboard.bytes,
    overview_bytes: Buffer.byteLength(encode(overview)), tickers: overview.watchlist.length };
  console.log('UI data build:', JSON.stringify(result));
  return result;
}
// Files that never need to be served as static assets. Build-only inputs are
// compacted/split into dashboard_overview.json + ui-data/, which the browser
// fetches instead. api/, middleware.js and vercel.json are Vercel server-side
// entries and must stay at the project root, not in the static output.
const SKIP_FILES = new Set([
  'build-data.cjs', 'vercel.json', 'middleware.js',
  'dashboard_data.json', 'dashboard_overview.json',
  'ic_data.json', 'wyckoff_ic_data.json', 'radar_snapshot.json',
]);
const SKIP_DIRS = new Set(['api', 'ui-data', 'dist', 'node_modules', '.git']);
function deploy(web = __dirname, out = path.join(web, 'dist')) {
  fs.rmSync(out, { recursive: true, force: true });
  fs.mkdirSync(out, { recursive: true });
  for (const entry of fs.readdirSync(web, { withFileTypes: true })) {
    if (entry.isFile() && !SKIP_FILES.has(entry.name))
      fs.copyFileSync(path.join(web, entry.name), path.join(out, entry.name));
    else if (entry.isDirectory() && !SKIP_DIRS.has(entry.name))
      fs.cpSync(path.join(web, entry.name), path.join(out, entry.name), { recursive: true });
  }
  const result = build(web, { write: (relative, data) => {
    const output = path.join(out, relative);
    fs.mkdirSync(path.dirname(output), { recursive: true });
    fs.writeFileSync(output, encode(data));
  }});
  const bytes = fs.readdirSync(out)
    .reduce((sum, name) => sum + size(path.join(out, name)), 0);
  console.log('Deployment output:', JSON.stringify({ dir: path.relative(web, out) || '.', bytes }));
  return result;
}
function size(target) {
  const stat = fs.statSync(target);
  if (!stat.isDirectory()) return stat.size;
  return fs.readdirSync(target).reduce((sum, name) => sum + size(path.join(target, name)), 0);
}
module.exports = { build, deploy, compact };
if (require.main === module) deploy();
