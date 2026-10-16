(() => {
  const state = { data: null, ticker: null, mode: "wyckoff", layers: {wyckoff:true,trend:true,vwap:true} };
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
  const current = () => {
    const raw = state.data.watchlist.find(x => x.ticker === state.ticker) || state.data.watchlist[0];
    const config = window.getAnalysisStyle?.();
    if (!raw || !config) return raw;
    // Project the selected horizon for display only; never mutate screening data.
    return { ...raw, score: raw[config.scoreKey], signal: raw[config.signalKey],
      trend: raw[config.trendKey], wyckoff: raw[config.wyckoffKey],
      score_breakdown: raw[config.bdKey], support: raw[config.supportKey],
      resistance: raw[config.resistanceKey], comparative_strength: raw[config.csKey],
      vwap: raw[config.vwapKey] };
  };
  const colorForSignal = s => s === "beli" ? "#4ade80" : s === "jual" ? "#f87171" : "#facc15";
  const colorForVwap = signal => signal === "BUY" ? "#4ade80" : signal === "HOLD" ? "#60a5fa" : signal === "WAIT" ? "#facc15" : signal === "REDUCE" ? "#ff9f0a" : "#f87171";
  const positionLabel = p => p === "above" ? "Harga di atas" : p === "below" ? "Harga di bawah" : "Harga setara";
  const slopeLabel = n => n == null ? "—" : `${n > 0 ? "+" : ""}${Number(n).toFixed(2)}%`;

  function makeChart(stock, layers=state.layers) {
    if (!stock.price_history?.length) return {svg:'<p class="empty-event">Histori harga asli belum tersedia. Tidak ada chart estimasi.</p>',isReal:false};
    const raw = stock.price_history;
    const data = raw.slice(-100), W=820,H=390, top=22,bottom=34,left=12,right=68, volH=68, volGap=28;
    const plotH=H-bottom-top-volH-volGap, plotW=W-left-right;
    const volBottom=H-bottom, volTop=volBottom-volH;
    const volumeValue=d=>Number.isFinite(d.volume)&&d.volume>=0?d.volume:0;
    const volumeLabel=n=>n>=1e9?fmt(n/1e9)+' M':n>=1e6?fmt(n/1e6)+' jt':n>=1e3?fmt(n/1e3)+' rb':fmt(n);
    const values=data.flatMap(d=>[d.high,d.low,...(layers.vwap?[d.vwap_5??d.vwap,d.vwap_20,d.vwap_60]:[])]).filter(Number.isFinite);
    [...(layers.trend?[stock.support,stock.resistance]:[]),...(layers.wyckoff?[stock.wyckoff?.tr_low,stock.wyckoff?.tr_high]:[])].filter(Number.isFinite).forEach(v=>values.push(v));
    const min=Math.min(...values)*.985,max=Math.max(...values)*1.015, span=max-min||1;
    const x=i=>left+(i+.5)*plotW/data.length, y=v=>top+(max-v)/span*plotH;
    const candleW=Math.max(2,plotW/data.length*.58), maxVol=Math.max(...data.map(volumeValue),1);
    let svg=`<svg class="chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Chart ${esc(stock.ticker)}">`;
    for(let i=0;i<5;i++){const yy=top+i*plotH/4,val=max-i*span/4;svg+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" stroke="#252525"/><text x="${W-right+8}" y="${yy+4}" fill="#777" font-size="10">${fmt(val)}</text>`}
    svg+=`<line x1="${left}" y1="${volTop-7}" x2="${W-right}" y2="${volTop-7}" stroke="#252525"/><text x="${left}" y="${volTop-12}" fill="#888" font-size="10">Volume</text><text x="${W-right+8}" y="${volTop+9}" fill="#777" font-size="9">${data.some(d=>Number.isFinite(d.volume)&&d.volume>=0)?volumeLabel(Math.max(...data.map(volumeValue))):"—"}</text><line x1="${left}" y1="${volBottom}" x2="${W-right}" y2="${volBottom}" stroke="#252525"/>`;
    data.forEach((d,i)=>{const up=d.close>=d.open,c=up?"#4ade80":"#f87171",xx=x(i);svg+=`<line x1="${xx}" y1="${y(d.high)}" x2="${xx}" y2="${y(d.low)}" stroke="${c}"/><rect x="${xx-candleW/2}" y="${Math.min(y(d.open),y(d.close))}" width="${candleW}" height="${Math.max(1,Math.abs(y(d.open)-y(d.close)))}" fill="${c}" rx=".5"/><rect x="${xx-candleW/2}" class="volume-bar" y="${volBottom-volumeValue(d)/maxVol*volH}" width="${candleW}" height="${volumeValue(d)/maxVol*volH}" fill="${c}" opacity=".55"/>`});
    const vwapLines=[['vwap_5','#60a5fa',1.7],['vwap_20','#a78bfa',1.5],['vwap_60','#f59e0b',1.5]];
    if(layers.vwap)vwapLines.forEach(([key,color,width])=>{const path=data.map((d,i)=>{const value=d[key]??(key==='vwap_5'?d.vwap:null);return Number.isFinite(value)?`${i?'L':'M'}${x(i)},${y(value)}`:''}).join(' ');if(path)svg+=`<path data-layer="vwap" d="${path}" fill="none" stroke="${color}" stroke-width="${width}"/>`});
    const levels=[...(layers.trend?[['Support',stock.support,'#4ade80'],['Resistance',stock.resistance,'#f87171']]:[]),...(layers.wyckoff?[['TR Low',stock.wyckoff?.tr_low,'#facc15'],['TR High',stock.wyckoff?.tr_high,'#facc15']]:[])];
    levels.forEach(([label,v,c])=>{if(!Number.isFinite(v))return;const yy=y(v);svg+=`<line data-layer="${label.startsWith('TR ')?'wyckoff':'trend'}" x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" stroke="${c}" stroke-dasharray="5 5" opacity=".72"/><text x="${left+5}" y="${yy-4}" fill="${c}" font-size="10">${label} ${fmt(v)}</text>`});
    (layers.wyckoff?stock.wyckoff?.events||[]:[]).forEach((e,i)=>{const idx=Math.max(0,data.findIndex(d=>String(e.date).startsWith(d.date)));const pos=idx<0?Math.max(0,data.length-1-i*5):idx;svg+=`<circle data-layer="wyckoff" cx="${x(pos)}" cy="${y(data[pos].high)-11}" r="10" fill="#facc15"/><text x="${x(pos)}" y="${y(data[pos].high)-7.5}" fill="#111" text-anchor="middle" font-size="8" font-weight="700">${esc(e.type)}</text>`});
    svg+=`<text x="${left}" y="${H-8}" fill="#666" font-size="10">${esc(data[0]?.date||'')}</text><text x="${W-right}" y="${H-8}" fill="#666" font-size="10" text-anchor="end">${esc(data.at(-1)?.date||'')}</text></svg>`;
    return {svg, isReal: !!stock.price_history?.length};
  }

  function makeVolatilityChart(stock) {
    const v = stock.volatility;
    const hist = (v.price_history || []).slice(-90);
    const W=820,H=390, top=22,bottom=32,left=12,right=68;
    const plotH=H-bottom-top, plotW=W-left-right;
    const histN = hist.length, fcN = (v.upper_band_95||[]).length, totalN = histN + fcN;
    const values = hist.map(d=>d.close).concat(v.upper_band_95||[]).concat(v.lower_band_95||[]);
    const min=Math.min(...values)*.97, max=Math.max(...values)*1.03, span=max-min||1;
    const x=i=>left+(i+.5)*plotW/totalN, y=val=>top+(max-val)/span*plotH;
    let svg=`<svg class="chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Forecast volatilitas ${esc(stock.ticker)}">`;
    for(let i=0;i<5;i++){const yy=top+i*plotH/4,val=max-i*span/4;svg+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" stroke="#252525"/><text x="${W-right+8}" y="${yy+4}" fill="#777" font-size="10">${fmt(val)}</text>`}
    let path=''; hist.forEach((d,i)=>{path+=`${i?'L':'M'}${x(i)},${y(d.close)}`}); svg+=`<path d="${path}" fill="none" stroke="#4ade80" stroke-width="1.8"/>`;
    if(fcN){
      const startIdx=histN-1, lastClose=hist.length?hist[hist.length-1].close:v.last_price;
      let up=`M${x(startIdx)},${y(lastClose)}`, low=`M${x(startIdx)},${y(lastClose)}`;
      v.upper_band_95.forEach((u,i)=>{up+=` L${x(startIdx+1+i)},${y(u)}`});
      v.lower_band_95.forEach((l,i)=>{low+=` L${x(startIdx+1+i)},${y(l)}`});
      svg+=`<path d="${up}" fill="none" stroke="#60a5fa" stroke-width="1.3" stroke-dasharray="5 4"/><path d="${low}" fill="none" stroke="#60a5fa" stroke-width="1.3" stroke-dasharray="5 4"/><line x1="${x(startIdx)}" y1="${top}" x2="${x(startIdx)}" y2="${H-bottom}" stroke="#444" stroke-dasharray="2 3"/>`;
    }
    svg+=`<text x="${left}" y="${H-10}" fill="#666" font-size="10">${esc(hist[0]?.date||'')}</text><text x="${W-right}" y="${H-10}" fill="#666" font-size="10" text-anchor="end">+${fcN} hari ke depan</text></svg>`;
    return {svg, isReal: true, isVolatility: true};
  }

  function technicalPanel(stock) {
    const wy=stock.wyckoff||{}, events=wy.events||[];
    if(state.mode==='volatility'){
      const v=stock.volatility;
      if(!v||v.status!=='ok') return `<div class="panel"><h3>FORECAST VOLATILITAS</h3><p class="empty-event">Data volatilitas belum tersedia untuk saham ini (butuh minimal ~120 hari data historis).</p></div>`;
      const last=Math.min((v.upper_band_95||[]).length,(v.lower_band_95||[]).length)-1;
      return `<div class="panel"><h3>FORECAST VOLATILITAS (GARCH)</h3><div class="metric-row"><span>Regime</span><b>${esc(v.regime)}</b></div><div class="metric-row"><span>Vol. forecast harian</span><b>${v.current_forecast_vol_pct}%</b></div><div class="metric-row"><span>Vol. historis 60 hari</span><b>${v.hist_vol_60d_pct}%</b></div><div class="metric-row"><span>Band 10 hari (95%)</span><b>${fmt(v.lower_band_95?.[last])} – ${fmt(v.upper_band_95?.[last])}</b></div><p class="empty-event">Ini rentang wajar pergerakan harga berdasar pola volatilitas historis, BUKAN tebakan harga pasti dan BUKAN sinyal beli/jual. Dipakai sebagai referensi lebar stop-loss / risk sizing.</p></div>`;
    }
    if(state.mode==='wyckoff') return `<div class="panel"><h3>PETA WYCKOFF</h3><div class="metric-row"><span>Bias</span><b>${esc(wy.bias||'unclear')}</b></div><div class="metric-row"><span>Fase</span><b>${esc(wy.phase||'unclear')}</b></div><div class="metric-row"><span>Trading range</span><b>${fmt(wy.tr_low)} — ${fmt(wy.tr_high)}</b></div><div class="event-list">${events.length?events.map(e=>`<div class="event-item"><span class="event-code">${esc(e.type)}</span><div class="event-desc"><b>${esc(String(e.date||'').slice(0,10))}</b><br>${esc(descriptions[e.type]||'Event Wyckoff terdeteksi oleh rule engine.')}</div></div>`).join(''):`<p class="empty-event">Belum ada event Wyckoff yang lolos aturan. Ini bukan berarti tidak ada setup; artinya struktur saat ini belum cukup jelas untuk diberi label otomatis.</p>`}</div></div>`;
    if(state.mode==='trend') return `<div class="panel"><h3>STRUKTUR TREND</h3><div class="metric-row"><span>Status</span><b>${esc(stock.trend)}</b></div><div class="metric-row"><span>Support terdekat</span><b>${fmt(stock.support)}</b></div><div class="metric-row"><span>Resistance terdekat</span><b>${fmt(stock.resistance)}</b></div><p class="empty-event">Swing high dan swing low pada chart membantu memeriksa apakah urutannya membentuk HH/HL, LH/LL, atau sideways.</p></div>`;
    if(state.mode==='vwap') {
      const a=stock.vwap_analysis||{};
      const horizons=[['Daily',a.vwap_fast],['Weekly',a.vwap_medium],['Swing',a.vwap_swing]];
      const horizonRows=horizons.map(([label,v])=>`<div class="metric-row"><span>${label} · ${v?.window||'—'}D</span><b>${fmt(v?.value)} · ${positionLabel(v?.position)} · slope ${slopeLabel(v?.slope_pct)}</b></div>`).join('');
      const reasons=(a.reasons||[]).map(reason=>`<li>${esc(reason)}</li>`).join('');
      return `<div class="panel"><h3>KEPUTUSAN VWAP MULTI-HORIZON</h3><div class="metric-row"><span>Sinyal Full VWAP</span><b style="color:${colorForVwap(stock.vwap_signal)}">${esc(stock.vwap_signal||'WAIT')}</b></div><div class="metric-row"><span>Regime</span><b>${esc(a.regime||'—')}</b></div>${horizonRows}<div class="metric-row"><span>RVOL / ATR</span><b>${fmt(a.rvol)}× / ${fmt(a.atr)}</b></div><div class="metric-row"><span>Protective stop</span><b>${fmt(a.protective_stop)}</b></div><div class="metric-row"><span>Eksekusi model</span><b>${a.execution==='next_session_open'?'Open sesi berikutnya':'Tidak ada entry baru'}</b></div>${reasons?`<ul class="checklist" style="margin-top:12px">${reasons}</ul>`:'<p class="empty-event">Data belum cukup atau belum ada alasan terkonfirmasi.</p>'}<p class="empty-event">Confidence sengaja tidak ditampilkan sebagai persentase sebelum kalibrasi out-of-sample tersedia.</p></div>`;
    }
    if(state.mode==='strength') return `<div class="panel"><h3>KEKUATAN RELATIF VS IHSG</h3><div class="metric-row"><span>Status</span><b>${esc(stock.comparative_strength?.relative_strength_trend)}</b></div><div class="metric-row"><span>Rasio awal</span><b>${fmt(stock.comparative_strength?.ratio_start)}</b></div><div class="metric-row"><span>Rasio kini</span><b>${fmt(stock.comparative_strength?.ratio_now)}</b></div><p class="empty-event">Rasio yang meningkat berarti saham mengungguli IHSG pada jendela pengamatan, bukan menjamin harga akan naik.</p></div>`;
    return `<div class="panel"><h3>KONTRIBUSI SKOR</h3>${Object.entries(stock.score_breakdown||{}).map(([k,v])=>`<div class="metric-row"><span>${esc(k.replace('_',' '))}</span><b>${v>0?'+':''}${v}</b></div>`).join('')}</div>`;
  }


  const componentNames = {trend:'Tren',wyckoff:'Wyckoff',vwap:'VWAP',comparative:'Vs IHSG',comparative_strength:'Vs IHSG',sr:'Support / resistance',support_resistance:'Support / resistance'};
  function summaryFor(stock, mode) {
    const rows=[], wy=stock.wyckoff||{}, a=stock.vwap_analysis||{};
    let title='Data belum cukup', reason='Belum ada kesimpulan yang bisa ditampilkan.', next='Tunggu pembaruan data.';
    if(mode==='wyckoff'){
      const labels={
        accumulation:['Ada tanda akumulasi','Struktur mengarah ke penguatan, tetapi belum memastikan harga akan naik.','Tunggu harga menguat dengan volume dan support tetap bertahan.'],
        distribution:['Ada tanda distribusi','Struktur mengarah ke pelemahan.','Waspadai support jebol; hindari mengejar kenaikan.'],
        conflicting:['Arah belum jelas','Tanda penguatan dan pelemahan saling bertentangan.','Tunggu arah harga dan volume lebih jelas.'],
        unclear:['Pola belum jelas','Belum cukup bukti untuk menyimpulkan akumulasi atau distribusi.','Pantau dulu; jangan mengambil keputusan dari pola ini saja.']
      };
      [title,reason,next]=labels[wy.bias]||labels.unclear;
      if(Number.isFinite(wy.tr_low)&&Number.isFinite(wy.tr_high)) rows.push(['Batas area harga',fmt(wy.tr_low)+' – '+fmt(wy.tr_high)]);
      const latest=[...(wy.events||[])].filter(e=>/^\d{4}-\d{2}-\d{2}/.test(String(e.date||''))).sort((x,y)=>String(y.date).localeCompare(String(x.date)))[0];
      if(latest) rows.push(['Event terakhir',String(latest.type||'—')+' · '+String(latest.date).slice(0,10)]);
    } else if(mode==='trend'){
      const labels={
        uptrend:['Tren masih naik','Arah struktur harga mendukung penguatan.','Perhatikan apakah support tetap bertahan saat harga melemah.'],
        downtrend:['Tren masih turun','Arah struktur harga belum mendukung penguatan.','Tunggu struktur membaik; waspadai support jebol.'],
        sideways:['Harga masih mendatar','Belum ada arah tren yang dominan.','Tunggu harga keluar dari area pergerakan dengan konfirmasi volume.']
      };
      [title,reason,next]=labels[stock.trend]||[title,reason,next];
      if(Number.isFinite(stock.support))rows.push(['Support',fmt(stock.support)]);
      if(Number.isFinite(stock.resistance))rows.push(['Resistance',fmt(stock.resistance)]);
    } else if(mode==='vwap'){
      const labels={
        BUY:['VWAP mendukung peluang beli','Model VWAP memberi sinyal BUY. Ini bukan perintah transaksi.','Periksa konfirmasi harga dan batas risiko sebelum entry.'],
        HOLD:['VWAP mendukung tahan posisi','Model VWAP memberi sinyal HOLD, bukan entry baru.','Pantau apakah arah harga masih mendukung posisi.'],
        WAIT:['VWAP belum mendukung entry','Model VWAP memberi sinyal WAIT.','Tunggu konfirmasi; tidak ada entry baru dari model.'],
        REDUCE:['VWAP meminta kurangi risiko','Model VWAP memberi sinyal REDUCE.','Evaluasi posisi dan batas risiko sebelum mengambil tindakan.'],
        AVOID:['VWAP belum layak untuk entry','Model VWAP memberi sinyal AVOID.','Hindari entry dari model ini sampai kondisi membaik.'],
        EXIT:['VWAP memberi sinyal keluar','Model VWAP memberi sinyal EXIT.','Evaluasi posisi; jangan mengabaikan batas risiko.']
      };
      [title,reason,next]=(Object.keys(a).length?labels[stock.vwap_signal]:null)||[title,reason,next];
      if(Number.isFinite(a.protective_stop))rows.push(['Batas risiko model',fmt(a.protective_stop)]);
    } else if(mode==='strength'){
      const status=stock.comparative_strength?.relative_strength_trend;
      if(status==='outperforming') [title,reason,next]=['Lebih kuat dibanding IHSG','Kinerja relatif saham mengungguli IHSG pada periode yang dihitung.','Cek tren harga juga: mengungguli IHSG belum tentu berarti harga naik.'];
      if(status==='underperforming') [title,reason,next]=['Tertinggal dari IHSG','Kinerja relatif saham lebih lemah dibanding IHSG pada periode yang dihitung.','Jangan mengandalkan kekuatan relatif untuk mendukung entry saat ini.'];
    } else if(mode==='volatility'){
      const v=stock.volatility;
      if(v?.status==='ok' && Number.isFinite(v.current_forecast_vol_pct)){
        title='Perkiraan gerak harian '+fmt(v.current_forecast_vol_pct)+'%';
        reason='Volatilitas mengukur besar gerakan, bukan arah naik atau turun.';
        next='Gunakan untuk menilai lebar stop dan ukuran posisi, bukan sinyal beli/jual.';
        const upper=v.upper_band_95||[],lower=v.lower_band_95||[],last=Math.min(upper.length,lower.length)-1;
        if(last>=0&&Number.isFinite(lower[last])&&Number.isFinite(upper[last]))rows.push(['Rentang '+(last+1)+' hari · 95%',fmt(lower[last])+' – '+fmt(upper[last])]);
      } else reason='Histori atau hasil forecast belum memadai untuk saham ini.';
    } else {
      const labels={
        beli:['Kandidat untuk dipantau','Gabungan indikator menghasilkan sinyal beli, bukan kepastian untung.','Tunggu konfirmasi harga dan siapkan batas risiko.'],
        jual:['Risiko lebih dominan','Gabungan indikator menghasilkan sinyal jual.','Evaluasi posisi; hindari entry hanya karena harga terlihat murah.'],
        pantau:['Belum ada dukungan kuat','Gabungan indikator belum mendukung keputusan beli atau jual yang kuat.','Pantau dulu sampai indikator lebih searah.']
      };
      [title,reason,next]=labels[stock.signal]||[title,reason,next];
      if(Number.isFinite(stock.score))rows.push(['Skor gabungan',fmt(stock.score)+' · skala −100 hingga +100']);
      const parts=Object.entries(stock.score_breakdown||{}).filter(([,v])=>Number.isFinite(v)&&v!==0);
      const strongest=parts.sort((x,y)=>Math.abs(y[1])-Math.abs(x[1]))[0];
      if(strongest)rows.push(['Pengaruh terbesar',(componentNames[strongest[0]]||strongest[0])+' · '+(strongest[1]>0?'mendukung':'menekan')]);
    }
    return {title,reason,next,rows};
  }
  function modePanel(stock){
    const s=summaryFor(stock,state.mode);
    return '<div class="panel analysis-brief"><h3>INTINYA</h3><h4>'+esc(s.title)+'</h4><p>'+esc(s.reason)+'</p><div class="analysis-next"><span>Yang perlu diperhatikan</span><p>'+esc(s.next)+'</p></div>'+s.rows.map(([label,value])=>'<div class="metric-row"><span>'+esc(label)+'</span><b>'+esc(value)+'</b></div>').join('')+'<details class="analysis-details"><summary>Lihat detail teknis</summary>'+technicalPanel(stock)+'</details></div>';
  }

  function layerControls(){
    const eye='<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>';
    return '<div class="chart-layer-controls" aria-label="Tampilan indikator chart">'+[['wyckoff','Wyckoff'],['trend','Trend'],['vwap','VWAP']].map(([key,label])=>{
      const shown=state.layers[key],action=shown?'Sembunyikan':'Tampilkan';
      return '<button type="button" class="chart-layer-toggle '+(shown?'':'is-hidden')+'" data-layer-toggle="'+key+'" aria-pressed="'+shown+'" aria-label="'+action+' '+label+'" title="'+action+' '+label+'"><svg viewBox="0 0 24 24" aria-hidden="true">'+eye+(shown?'':'<path d="m3 3 18 18"/>')+'</svg><span>'+label+'</span></button>';
    }).join('')+'</div>';
  }

  function render() {
    const stock=current();
    const activityRecord=window.GlabsActivity.record(stock.ticker,state.data.market_data_date);
    const chartStock=stock;
    const priceDate=stock.last_price_date||stock.price_history?.at(-1)?.date||'tidak diketahui';
    const stale=!window.GlabsFreshness.isCurrent(stock,state.data);
    const isForecast=state.mode==='volatility'&&stock.volatility?.status==='ok';
    const chart=isForecast?makeVolatilityChart(stock):makeChart(chartStock);
    const pct=Math.max(0,Math.min(100,(stock.score+100)/2));
    document.getElementById('analysis-content').innerHTML=`<div class="drawer-shell"><div class="drawer-top"><div><div class="drawer-kicker">Decision-support cockpit · eksekusi manual</div><h2 class="drawer-title">${esc(stock.ticker)} <span style="color:var(--text-secondary)">${fmt(stock.last_close)}</span></h2><div class="drawer-sub">Skor ${stock.score} · komposit <span style="color:${colorForSignal(stock.signal)}">${esc(stock.signal.toUpperCase())}</span> · Full VWAP <span style="color:${colorForVwap(stock.vwap_signal)}">${esc(stock.vwap_signal||'WAIT')}</span> · data ${esc(priceDate)}${stale?' · <strong>TERTINGGAL · sinyal historis, bukan sesi terkini</strong>':''}</div></div><button class="close-btn" aria-label="Tutup">×</button></div><div class="ticker-strip">${state.data.watchlist.map(x=>`<button class="ticker-chip ${x.ticker===stock.ticker?'active':''}" data-ticker="${esc(x.ticker)}">${esc(x.ticker)}</button>`).join('')}</div><div class="chart-wrap"><div class="chart-toolbar"><b>${state.mode==='volatility'?'Forecast volatilitas':'Price structure'}</b><div class="chart-legend">${state.mode==='volatility'?'<span><i class="legend-dot" style="background:#4ade80"></i>Harga historis</span><span><i class="legend-dot" style="background:#60a5fa"></i>Band 95%</span>':'<span><i class="legend-dot" style="background:#4ade80"></i>Naik</span><span><i class="legend-dot" style="background:#f87171"></i>Turun</span>'+(state.layers.vwap?'<span><i class="legend-dot" style="background:#60a5fa"></i>VWAP 5D</span><span><i class="legend-dot" style="background:#a78bfa"></i>VWAP 20D</span><span><i class="legend-dot" style="background:#f59e0b"></i>VWAP 60D</span>':'')}</div></div>${!isForecast?layerControls():''}${chart.svg}${!isForecast?window.GlabsActivity.panel(stock,state.data.market_data_date):''}<div class="chart-note">${state.mode==='volatility'?'Band = rentang wajar 95%, bukan tebakan harga pasti.':(chart.isReal?'OHLC hasil screening otomatis.':'Histori harga asli tidak tersedia; tidak ada estimasi buatan.')}</div></div><div class="mode-tabs">${[['wyckoff','Wyckoff'],['trend','Trend'],['vwap','VWAP'],['strength','Vs IHSG'],['volatility','Volatilitas'],['score','Skor']].map(([k,l])=>`<button class="mode-tab ${state.mode===k?'active':''}" data-mode="${k}">${l}</button>`).join('')}</div><div class="analysis-grid">${modePanel(stock)}<div class="panel analysis-overall"><h3>SINYAL GABUNGAN</h3><div class="decision-box">${decisionText(stock)}</div><p class="analysis-risk-note">Sinyal tiap tab bisa berbeda. Keputusan akhir tetap perlu konfirmasi harga dan batas risiko.</p></div></div></div>`;
    bindDrawer();
  }

  function decisionText(s){if(!window.GlabsFreshness.isCurrent(s,state.data))return '<b>Sinyal historis.</b> Harga terakhir bukan sesi screening terkini atau tanggalnya belum terverifikasi. Jangan dipakai sebagai keputusan sesi hari ini.';if(s.signal==='beli')return '<b>Kandidat untuk dipantau.</b> Tunggu konfirmasi sebelum entry.';if(s.signal==='jual')return '<b>Risiko lebih dominan.</b> Evaluasi posisi dan batas risiko.';return '<b>Pantau dulu.</b> Belum ada dukungan indikator yang kuat.'}
  function bindDrawer(){document.querySelectorAll('[data-layer-toggle]').forEach(b=>b.onclick=()=>{const key=b.dataset.layerToggle;if(Object.hasOwn(state.layers,key)){state.layers[key]=!state.layers[key];render()}});document.querySelector('.close-btn').onclick=close;document.querySelectorAll('.ticker-chip').forEach(b=>b.onclick=()=>{state.ticker=b.dataset.ticker;showSelected()});document.querySelectorAll('.mode-tab').forEach(b=>b.onclick=()=>{state.mode=b.dataset.mode;render()})}
  let detailRequest=0;
  async function showSelected(){
    const request=++detailRequest,ticker=state.ticker;
    const content=document.getElementById('analysis-content');
    if(window.GlabsData){
      content.innerHTML='<div class="panel"><button class="close-btn" aria-label="Tutup">×</button><p role="status">Memuat histori '+esc(ticker)+'…</p></div>';
      content.querySelector('.close-btn').onclick=close;
      try{await window.GlabsData.detail(ticker);}
      catch(_){
        if(request!==detailRequest)return;
        content.innerHTML='<div class="panel"><button class="close-btn" aria-label="Tutup">×</button><p>Histori belum dapat dimuat. Muat ulang halaman jika pembaruan data baru saja diterbitkan.</p></div>';
        content.querySelector('.close-btn').onclick=close;
        return;
      }
    }
    if(request!==detailRequest)return;
    render();
    window.GlabsActivity.load(state.data.market_data_date,ticker);
  }
  function open(ticker,mode){
    if(!state.data)return;
    state.ticker=ticker||state.data.watchlist[0]?.ticker;
    state.mode=mode==='activity'?'wyckoff':mode||'wyckoff';
    document.getElementById('analysis-drawer').classList.add('open');
    document.getElementById('drawer-backdrop').classList.add('open');
    document.getElementById('analysis-drawer').setAttribute('aria-hidden','false');
    showSelected();
  }
  function close(){detailRequest++;document.getElementById('analysis-drawer').classList.remove('open');document.getElementById('drawer-backdrop').classList.remove('open');document.getElementById('analysis-drawer').setAttribute('aria-hidden','true')}
  function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2300)}
  function boot(data){state.data=data;document.querySelectorAll('.wl-row').forEach(row=>{const name=row.querySelector('.t')?.childNodes[0]?.textContent?.trim();if(data.watchlist.some(x=>x.ticker===name)){row.dataset.ticker=name;row.onclick=()=>open(name)}});const search=document.getElementById('ticker-search');search.onkeydown=e=>{if(e.key==='Enter'){const q=search.value.trim().toUpperCase();const found=data.watchlist.find(x=>x.ticker.includes(q));found?open(found.ticker,'score'):toast('Ticker belum ada di watchlist.')}};document.getElementById('drawer-backdrop').onclick=close;document.addEventListener('keydown',e=>{if(e.key==='Escape')close()});}
  window.addEventListener('activity-ready',()=>{if(state.data&&document.getElementById('analysis-drawer').classList.contains('open'))render()});
  window.addEventListener('dashboard-ready',e=>boot(e.detail));
  if(window.dashboardData) boot(window.dashboardData);

  window.openAnalysis = open; // exposed supaya card di halaman lain (mis. Watchlist per-komponen) bisa buka chart yang sama
})();
