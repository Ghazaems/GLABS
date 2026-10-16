(() => {
  let overviewPromise, overview;
  const pending = new Map();
  async function json(url, cache = 'force-cache') {
    const response = await fetch(url, { cache });
    if (!response.ok) throw Error('Data HTTP ' + response.status);
    return response.json();
  }
  function once(key, task) {
    if (!pending.has(key)) pending.set(key, task().catch(error => { pending.delete(key); throw error; }));
    return pending.get(key);
  }
  async function loadOverview() {
    if (!overviewPromise) overviewPromise = json('dashboard_overview.json', 'no-store').then(data => {
      if (data.ui_assets?.schema_version !== 1 || !Array.isArray(data.watchlist)) throw Error('Invalid overview');
      overview = data;
      return data;
    }).catch(error => { overviewPromise = null; throw error; });
    return overviewPromise;
  }
  async function detail(ticker) {
    const data = await loadOverview(), assets = data.ui_assets;
    const row = data.watchlist.find(item => item.ticker === ticker);
    if (!row) throw Error('Ticker tidak tersedia');
    return once('stock:' + ticker, async () => {
      const result = await json(assets.details_base + encodeURIComponent(ticker) + '.json');
      if (result.source_sha256 !== assets.dashboard_sha256 || result.stock?.ticker !== ticker ||
          result.market_data_date !== data.market_data_date) throw Error('Detail tidak cocok dengan screening');
      Object.assign(row, result.stock);
      return row;
    });
  }
  async function activity(session, ticker) {
    const { ui_assets: assets } = await loadOverview();
    if (assets.activity_session !== session) throw Error('Indikator belum sesuai sesi screening');
    return once('activity:' + ticker, async () => {
      const data = await json(assets.activity_base + encodeURIComponent(ticker) + '.json');
      if (data.source_sha256 !== assets.activity_sha256 || data.market_data_date !== session)
        throw Error('Indikator tidak cocok dengan screening');
      return data;
    });
  }
  async function rotation(history = false) {
    const { ui_assets: assets } = await loadOverview();
    return once('rotation:' + history, async () => {
      const data = await json(history ? assets.rotation_history : assets.rotation);
      if (!history) for (const kind of ['stocks', 'sectors']) {
        for (const row of data.modes?.weekly?.[kind] || []) {
          row.chart_history = (row.packed_history || []).map(([date, close, benchmark]) => ({ date, close, benchmark }));
          delete row.packed_history;
        }
      }
      return data;
    });
  }
  window.GlabsData = { overview: loadOverview, detail, activity, rotation };
})();
