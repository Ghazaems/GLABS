(() => {
  const state = { data: null, ticker: null, mode: "wyckoff" };
  const descriptions = {
    SC: "Selling Climax: tekanan jual ekstrem dengan volume besar; sering menjadi awal penghentian tren turun.",
    BC: "Buying Climax: euforia beli ekstrem; waspadai berakhirnya tren naik.",
    AR: "Automatic Reaction/Rally: reaksi otomatis setelah climax yang membantu membentuk batas trading range.",
    ST: "Secondary Test: pengujian ulang area climax. Volume yang mengecil memperkuat validitas test.",
    Spring: "Spring: harga sempat menembus support lalu kembali ke range; potensi bear trap, tetap tunggu konfirmasi.",
    UT: "Upthrust: harga menembus resistance lalu kembali ke range; potensi bull trap.",
    SOS: "Sign of Strength: breakout dengan spread dan volume meningkat.",
    SOW: "Sign of Weakness: breakdown dengan spread dan volume meningkat.",
    LPS: "Last Point of Support: pullback pasca-SOS yang bertahan di atas support.",
    LPSY: "Last Point of Supply: rally lemah pasca-SOW yang tertahan resistance."
  };

  const fmt = n => n == null ? "—" : Number(n).toLocaleString("id-ID", { maximumFractionDigits: 2 });
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const current = () => state.data.watchlist.find(x => x.ticker === state.ticker) || state.data.watchlist[0];
  const colorForSignal = s => s === "beli" ? "#4ade80" : s === "jual" ? "#f87171" : "#facc15";

  function syntheticHistory(stock) {
    const count = 90, end = stock.last_close || 1000, low = stock.wyckoff?.tr_low || end * .82, high = stock.wyckoff?.tr_high || end * 1.13;
    let value = Math.min(high, Math.max(low, end * .9));
    return Array.from({length: count}, (_, i) => {
      const drift = (end - value) / (count - i);
      const wave = Math.sin(i * .57) * (high-low) * .018;
      const open = value; value = Math.min(high*1.02, Math.max(low*.98, value + drift + wave));
      return {date:`T-${count-i}`,open,high:Math.max(open,value)*1.008,low:Math.min(open,value)*.992,close:value,volume:1000000*(1+Math.abs(Math.sin(i*.33))),vwap:(open+value)/2};
    });
  }

  function makeChart(stock) {
    const raw = stock.price_history?.length ? stock.price_history : syntheticHistory(stock);
    const data = raw.slice(-100), W=820,H=390, top=22,bottom=62,left=12,right=68, volH=68;
    const plotH=H-bottom-top-volH, plotW=W-left-right;
    const values=data.flatMap(d=>[d.high,d.low,d.vwap]).filter(Number.isFinite);
    [stock.support,stock.resistance,stock.wyckoff?.tr_low,stock.wyckoff?.tr_high].filter(Number.isFinite).forEach(v=>values.push(v));
    const min=Math.min(...values)*.985,max=Math.max(...values)*1.015, span=max-min||1;
    const x=i=>left+(i+.5)*plotW/data.length, y=v=>top+(max-v)/span*plotH;
    const candleW=Math.max(2,plotW/data.length*.58), maxVol=Math.max(...data.map(d=>d.volume||0),1);
    let svg=`<svg class="chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Chart ${esc(stock.ticker)}">`;
    for(let i=0;i<5;i++){const yy=top+i*plotH/4,val=max-i*span/4;svg+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" stroke="#252525"/><text x="${W-right+8}" y="${yy+4}" fill="#777" font-size="10">${fmt(val)}</text>`}
    data.forEach((d,i)=>{const up=d.close>=d.open,c=up?"#4ade80":"#f87171",xx=x(i);svg+=`<line x1="${xx}" y1="${y(d.high)}" x2="${xx}" y2="${y(d.low)}" stroke="${c}"/><rect x="${xx-candleW/2}" y="${Math.min(y(d.open),y(d.close))}" width="${candleW}" height="${Math.max(1,Math.abs(y(d.open)-y(d.close)))}" fill="${c}" rx=".5"/><rect x="${xx-candleW/2}" y="${H-bottom+10+(1-(d.volume||0)/maxVol)*volH}" width="${candleW}" height="${(d.volume||0)/maxVol*volH}" fill="${c}" opacity=".28"/>`});
    const path=data.map((d,i)=>d.vwap?`${i?'L':'M'}${x(i)},${y(d.vwap)}`:'').join(' '); if(path)svg+=`<path d="${path}" fill="none" stroke="#60a5fa" stroke-width="1.5"/>`;
    const levels=[['Support',stock.support,'#4ade80'],['Resistance',stock.resistance,'#f87171'],['TR Low',stock.wyckoff?.tr_low,'#facc15'],['TR High',stock.wyckoff?.tr_high,'#facc15']];
    levels.forEach(([label,v,c])=>{if(!Number.isFinite(v))return;const yy=y(v);svg+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" stroke="${c}" stroke-dasharray="5 5" opacity=".72"/><text x="${left+5}" y="${yy-4}" fill="${c}" font-size="10">${label} ${fmt(v)}</text>`});
    (stock.wyckoff?.events||[]).forEach((e,i)=>{const idx=Math.max(0,data.findIndex(d=>String(e.date).startsWith(d.date)));const pos=idx<0?Math.max(0,data.length-1-i*5):idx;svg+=`<circle cx="${x(pos)}" cy="${y(data[pos].high)-11}" r="10" fill="#facc15"/><text x="${x(pos)}" y="${y(data[pos].high)-7.5}" fill="#111" text-anchor="middle" font-size="8" font-weight="700">${esc(e.type)}</text>`});
    svg+=`<text x="${left}" y="${H-8}" fill="#666" font-size="10">${esc(data[0]?.date||'')}</text><text x="${W-right}" y="${H-8}" fill="#666" font-size="10" text-anchor="end">${esc(data.at(-1)?.date||'')}</text></svg>`;
    return {svg, isReal: !!stock.price_history?.length};
  }

  function modePanel(stock) {
    const wy=stock.wyckoff||{}, events=wy.events||[];
    if(state.mode==='wyckoff') return `<div class="panel"><h3>PETA WYCKOFF</h3><div class="metric-row"><span>Bias</span><b>${esc(wy.bias||'unclear')}</b></div><div class="metric-row"><span>Fase</span><b>${esc(wy.phase||'unclear')}</b></div><div class="metric-row"><span>Trading range</span><b>${fmt(wy.tr_low)} — ${fmt(wy.tr_high)}</b></div><div class="event-list">${events.length?events.map(e=>`<div class="event-item"><span class="event-code">${esc(e.type)}</span><div class="event-desc"><b>${esc(String(e.date||'').slice(0,10))}</b><br>${esc(descriptions[e.type]||'Event Wyckoff terdeteksi oleh rule engine.')}</div></div>`).join(''):`<p class="empty-event">Belum ada event Wyckoff yang lolos aturan. Ini bukan berarti tidak ada setup; artinya struktur saat ini belum cukup jelas untuk diberi label otomatis.</p>`}</div></div>`;
    if(state.mode==='trend') return `<div class="panel"><h3>STRUKTUR TREND</h3><div class="metric-row"><span>Status</span><b>${esc(stock.trend)}</b></div><div class="metric-row"><span>Support terdekat</span><b>${fmt(stock.support)}</b></div><div class="metric-row"><span>Resistance terdekat</span><b>${fmt(stock.resistance)}</b></div><p class="empty-event">Swing high dan swing low pada chart membantu memeriksa apakah urutannya membentuk HH/HL, LH/LL, atau sideways.</p></div>`;
    if(state.mode==='vwap') {const diff=stock.last_close-(stock.vwap?.vwap||stock.last_close);return `<div class="panel"><h3>VWAP MINGGUAN</h3><div class="metric-row"><span>Harga</span><b>${fmt(stock.last_close)}</b></div><div class="metric-row"><span>VWAP 5 hari</span><b>${fmt(stock.vwap?.vwap)}</b></div><div class="metric-row"><span>Deviasi</span><b>${diff>=0?'+':''}${fmt(diff)} (${(diff/(stock.vwap?.vwap||1)*100).toFixed(2)}%)</b></div><p class="empty-event">Garis biru adalah VWAP. Gunakan sebagai referensi fair value, bukan pemicu entry tunggal.</p></div>`}
    if(state.mode==='strength') return `<div class="panel"><h3>KEKUATAN RELATIF VS IHSG</h3><div class="metric-row"><span>Status</span><b>${esc(stock.comparative_strength?.relative_strength_trend)}</b></div><div class="metric-row"><span>Rasio awal</span><b>${fmt(stock.comparative_strength?.ratio_start)}</b></div><div class="metric-row"><span>Rasio kini</span><b>${fmt(stock.comparative_strength?.ratio_now)}</b></div><p class="empty-event">Rasio yang meningkat berarti saham mengungguli IHSG pada jendela pengamatan, bukan menjamin harga akan naik.</p></div>`;
    return `<div class="panel"><h3>KONTRIBUSI SKOR</h3>${Object.entries(stock.score_breakdown||{}).map(([k,v])=>`<div class="metric-row"><span>${esc(k.replace('_',' '))}</span><b>${v>0?'+':''}${v}</b></div>`).join('')}</div>`;
  }

  function render() {
    const stock=current(), chart=makeChart(stock), pct=Math.max(0,Math.min(100,(stock.score+100)/2));
    document.getElementById('analysis-content').innerHTML=`<div class="drawer-shell"><div class="drawer-top"><div><div class="drawer-kicker">Decision-support cockpit · eksekusi manual</div><h2 class="drawer-title">${esc(stock.ticker)} <span style="color:var(--text-secondary)">${fmt(stock.last_close)}</span></h2><div class="drawer-sub">Skor ${stock.score} · <span style="color:${colorForSignal(stock.signal)}">${esc(stock.signal.toUpperCase())}</span> · data ${esc(state.data.generated_at?.slice(0,10)||'')}</div></div><button class="close-btn" aria-label="Tutup">×</button></div><div class="ticker-strip">${state.data.watchlist.map(x=>`<button class="ticker-chip ${x.ticker===stock.ticker?'active':''}" data-ticker="${esc(x.ticker)}">${esc(x.ticker)}</button>`).join('')}</div><div class="chart-wrap"><div class="chart-toolbar"><b>Price structure</b><div class="chart-legend"><span><i class="legend-dot" style="background:#4ade80"></i>Naik</span><span><i class="legend-dot" style="background:#f87171"></i>Turun</span><span><i class="legend-dot" style="background:#60a5fa"></i>VWAP</span><span><i class="legend-dot" style="background:#facc15"></i>Wyckoff/TR</span></div></div>${chart.svg}<div class="chart-note">${chart.isReal?'OHLC hasil screening otomatis.':'Preview estimasi; jalankan main.py agar chart memakai OHLC asli.'}</div></div><div class="mode-tabs">${[['wyckoff','Wyckoff'],['trend','Trend'],['vwap','VWAP'],['strength','Vs IHSG'],['score','Skor']].map(([k,l])=>`<button class="mode-tab ${state.mode===k?'active':''}" data-mode="${k}">${l}</button>`).join('')}</div><div class="analysis-grid">${modePanel(stock)}<div><div class="panel"><h3>RINGKASAN MESIN</h3><div class="metric-row"><span>Skor</span><b>${stock.score}/100</b></div><div class="score-meter"><i style="width:${pct}%"></i></div><div class="decision-box">${decisionText(stock)}</div></div><div class="panel" style="margin-top:14px"><h3>CHECKLIST MANUAL SEBELUM EKSEKUSI</h3><ul class="checklist"><li>□ <span><b>Konteks pasar:</b> periksa arah IHSG dan sektor.</span></li><li>□ <span><b>Invalidasi:</b> tentukan level sebelum entry.</span></li><li>□ <span><b>Risk sizing:</b> sesuaikan jarak stop dan risiko portofolio.</span></li><li>□ <span><b>Konfirmasi:</b> tunggu price action/volume, jangan hanya skor.</span></li></ul></div></div></div></div>`;
    bindDrawer();
  }

  function decisionText(s){if(s.signal==='beli')return `<b>Kandidat riset lanjut.</b> Struktur kuantitatif relatif konstruktif, tetapi entry tetap menunggu konfirmasi dan rencana risiko Anda.`;if(s.signal==='jual')return `<b>Risiko dominan.</b> Hindari entry impulsif; evaluasi invalidasi, perubahan struktur, dan apakah posisi perlu dikurangi secara manual.`;return `<b>Belum ada edge kuat.</b> Masukkan ke pantauan dan tunggu konfluensi indikator membaik.`}
  function bindDrawer(){document.querySelector('.close-btn').onclick=close;document.querySelectorAll('.ticker-chip').forEach(b=>b.onclick=()=>{state.ticker=b.dataset.ticker;render()});document.querySelectorAll('.mode-tab').forEach(b=>b.onclick=()=>{state.mode=b.dataset.mode;render()})}
  function open(ticker,mode){state.ticker=ticker||state.data.watchlist[0]?.ticker;state.mode=mode||'wyckoff';render();document.getElementById('analysis-drawer').classList.add('open');document.getElementById('drawer-backdrop').classList.add('open');document.getElementById('analysis-drawer').setAttribute('aria-hidden','false')}
  function close(){document.getElementById('analysis-drawer').classList.remove('open');document.getElementById('drawer-backdrop').classList.remove('open');document.getElementById('analysis-drawer').setAttribute('aria-hidden','true')}
  function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2300)}
  function boot(data){state.data=data;document.querySelectorAll('.wl-row').forEach(row=>{const name=row.querySelector('.t')?.childNodes[0]?.textContent?.trim();if(data.watchlist.some(x=>x.ticker===name)){row.dataset.ticker=name;row.onclick=()=>open(name)}});const cards=[['trend-text','trend'],['wyckoff-text','wyckoff'],['vwap-text','vwap'],['scoredist-text','score'],['cs-text','strength'],['sr-rows','trend'],['toppick-text','score']];cards.forEach(([id,mode])=>{const card=document.getElementById(id)?.closest('.card');if(card){card.dataset.action=mode;card.onclick=()=>open(mode==='wyckoff'?data.summary.strongest_accumulation?.ticker:null,mode)}});document.querySelectorAll('.pill').forEach(p=>{const text=p.textContent.trim();p.onclick=()=>text.includes('Wyckoff')?open(null,'wyckoff'):text.includes('trend')?open(null,'trend'):text.includes('VWAP')?open(null,'vwap'):toast('Fitur ini disiapkan sebagai decision-support, bukan eksekusi otomatis.')});const search=document.getElementById('ticker-search');search.onkeydown=e=>{if(e.key==='Enter'){const q=search.value.trim().toUpperCase();const found=data.watchlist.find(x=>x.ticker.includes(q));found?open(found.ticker,'score'):toast('Ticker belum ada di watchlist.')}};document.getElementById('drawer-backdrop').onclick=close;document.addEventListener('keydown',e=>{if(e.key==='Escape')close()});}
  window.addEventListener('dashboard-ready',e=>boot(e.detail));
  if(window.dashboardData) boot(window.dashboardData);
})();
