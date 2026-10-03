(() => {
  "use strict";
  const Q = {Leading:"#32d74b",Improving:"#60a5fa",Weakening:"#ffd60a",Lagging:"#ff453a",Neutral:"#a1a1aa"};
  const INFO = {Leading:"Kuat · momentum naik",Improving:"Relatif lemah · momentum pulih",Weakening:"Kuat · momentum melemah",Lagging:"Lemah · momentum turun"};
  const LABEL = {daily:"Daily · 5D",weekly:"Weekly · 20D",swing:"Swing · 60D"};
  const state = {data:null,loading:null,style:"weekly",scope:"sectors",sector:"",filter:"",query:"",sort:"rank",selected:"",tail:5};
  const root = () => document.getElementById("rotation-root");
  const esc = v => String(v ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const num = (v,d=2) => Number.isFinite(v)?v.toLocaleString("id-ID",{maximumFractionDigits:d,minimumFractionDigits:d}):"—";
  const pct = v => (v>0?"+":"")+num(v)+"%";
  const badge = q => '<span class="rotation-badge" style="--q-color:'+ (Q[q]||Q.Neutral)+'">'+esc(q)+'</span>';
  const mode = () => state.data.modes[state.style];
  const scopeRows = () => state.scope==="sectors"?mode().sectors.filter(r=>r.status==="ok"):mode().stocks.filter(r=>r.sector===state.sector);
  function rows() {
    const result = scopeRows().filter(r=>(!state.filter||r.quadrant===state.filter)&&
      (!state.query||(r.symbol+" "+r.name).toLowerCase().includes(state.query.toLowerCase())));
    if(state.sort!=="rank") result.sort((a,b)=>(b[state.sort]??-Infinity)-(a[state.sort]??-Infinity)||a.symbol.localeCompare(b.symbol));
    return result;
  }
  function picked() { return scopeRows().find(r=>r.symbol===state.selected)||null; }
  function mapMarkup(list) {
    if(!list.length) return '<p class="rotation-muted">Tidak ada hasil valid untuk pilihan ini.</p>';
    const all=list.flatMap(r=>r.trail.slice(-state.tail));
    const sx=Math.max(2,...all.map(p=>Math.abs(p.strength-100)))*1.18;
    const sy=Math.max(2,...all.map(p=>Math.abs(p.momentum-100)))*1.18;
    const x=v=>60+(v-(100-sx))/(2*sx)*560, y=v=>34+(100+sy-v)/(2*sy)*350;
    let svg='<svg class="rotation-map" viewBox="0 0 680 440" role="img" aria-label="Peta kekuatan relatif dan momentum terhadap IHSG">';
    svg+='<rect x="60" y="34" width="280" height="175" fill="#60a5fa" opacity=".04"/><rect x="340" y="34" width="280" height="175" fill="#32d74b" opacity=".04"/><rect x="60" y="209" width="280" height="175" fill="#ff453a" opacity=".04"/><rect x="340" y="209" width="280" height="175" fill="#ffd60a" opacity=".04"/>';
    for(let i=0;i<=4;i++){
      const px=60+i*140,py=34+i*87.5;
      svg+='<path d="M'+px+' 34V384 M60 '+py+'H620" stroke="rgba(255,255,255,'+(i===2?".23":".06")+')" stroke-dasharray="'+(i===2?"0":"3 5")+'"/>';
      svg+='<text x="'+px+'" y="404" text-anchor="middle" fill="#858585" font-size="10">'+num(100-sx+i*sx/2,1)+'</text>';
      svg+='<text x="51" y="'+(py+4)+'" text-anchor="end" fill="#858585" font-size="10">'+num(100+sy-i*sy/2,1)+'</text>';
    }
    svg+='<text x="75" y="53" fill="#60a5fa" opacity=".7" font-size="11">IMPROVING</text><text x="607" y="53" text-anchor="end" fill="#32d74b" opacity=".7" font-size="11">LEADING</text><text x="75" y="375" fill="#ff453a" opacity=".7" font-size="11">LAGGING</text><text x="607" y="375" text-anchor="end" fill="#ffd60a" opacity=".7" font-size="11">WEAKENING</text>';
    svg+='<text x="340" y="430" text-anchor="middle" fill="#999" font-size="11">Kekuatan relatif vs IHSG →</text><text x="14" y="209" transform="rotate(-90 14 209)" text-anchor="middle" fill="#999" font-size="11">Momentum relatif →</text>';
    for(const r of list){
      const tail=r.trail.slice(-state.tail),p=tail[tail.length-1],chosen=state.selected===r.symbol;
      const color=Q[r.quadrant]||Q.Neutral;
      svg+='<g class="rotation-track" data-symbol="'+esc(r.symbol)+'" tabindex="0" role="button" aria-label="'+esc(r.symbol+" "+r.quadrant)+'" opacity="'+(state.selected&&!chosen?".35":".85")+'"><title>'+esc(r.name+" · "+r.quadrant+" · "+r.phase)+'</title>';
      svg+='<polyline points="'+tail.map(t=>x(t.strength).toFixed(2)+","+y(t.momentum).toFixed(2)).join(" ")+'" fill="none" stroke="'+color+'" stroke-width="'+(chosen?2.7:1.5)+'" stroke-linecap="round" stroke-linejoin="round"/>';
      tail.slice(0,-1).forEach((t,i)=>{svg+='<circle cx="'+x(t.strength)+'" cy="'+y(t.momentum)+'" r="1.8" fill="'+color+'" opacity="'+(.25+.6*i/tail.length)+'"/>';});
      svg+='<circle cx="'+x(p.strength)+'" cy="'+y(p.momentum)+'" r="'+(chosen?6:4)+'" fill="'+color+'" stroke="#111" stroke-width="1.5"/>';
      if(chosen) svg+='<circle cx="'+x(p.strength)+'" cy="'+y(p.momentum)+'" r="10" fill="none" stroke="'+color+'" opacity=".4"/>';
      if(state.scope==="sectors"||chosen) svg+='<text x="'+Math.min(595,x(p.strength)+9)+'" y="'+(y(p.momentum)-8)+'" fill="'+color+'" font-size="10">'+esc(r.symbol)+'</text>';
      svg+='</g>';
    }
    return svg+'</svg>';
  }
  function movement(r) {
    const hist=r.history.slice(-40); if(hist.length<2)return "";
    const values=hist.map(p=>[100*p.close/hist[0].close,100*p.benchmark/hist[0].benchmark]);
    const lo=Math.min(...values.flat())*.99,hi=Math.max(...values.flat())*1.01,span=hi-lo||1;
    const x=i=>8+i*254/(hist.length-1),y=v=>12+(hi-v)/span*96;
    const line=k=>values.map((p,i)=>x(i).toFixed(2)+","+y(p[k]).toFixed(2)).join(" ");
    return '<svg viewBox="0 0 270 140" role="img" aria-label="Performa ternormalisasi 40 sesi, titik awal 100"><path d="M8 108H262" stroke="#333"/><polyline points="'+line(1)+'" fill="none" stroke="#777" stroke-dasharray="3 4" stroke-width="1.5"/><polyline points="'+line(0)+'" fill="none" stroke="'+(Q[r.quadrant]||Q.Neutral)+'" stroke-width="2"/><text x="8" y="132" fill="#858585" font-size="9">'+esc(hist[0].date)+'</text><text x="262" y="132" text-anchor="end" fill="#858585" font-size="9">'+esc(hist.at(-1).date)+'</text></svg><p class="rotation-muted">Garis warna: pilihan · abu-abu: IHSG<br>40 sesi · dinormalisasi dari 100</p>';
  }
  function inspectorMarkup() {
    const r=picked();
    if(!r)return '<h2>Detail rotasi</h2><p class="rotation-muted">Klik titik atau baris untuk melihat arah rotasi dan performanya.</p>';
    const positive=r.relative_return_pct>0;
    const conclusion=r.quadrant==="Leading"?"Mengungguli IHSG dan momentum relatif menguat.":r.quadrant==="Improving"?"Masih tertinggal IHSG, tetapi momentum relatif mulai pulih.":r.quadrant==="Weakening"?"Masih unggul terhadap IHSG, tetapi momentumnya melemah.":r.quadrant==="Lagging"?"Tertinggal IHSG dengan momentum relatif melemah.":"Berada pada batas; belum ada arah relatif yang jelas.";
    return '<h2>'+esc(r.symbol)+'</h2><div class="rotation-big">'+esc(r.name)+'</div>'+badge(r.quadrant)+'<p class="rotation-muted">'+conclusion+'</p><div class="rotation-metric"><span>Perubahan fase</span><b>'+esc(r.phase)+'</b></div><div class="rotation-metric"><span>Return '+mode().lookback+'D</span><b>'+pct(r.return_pct)+'</b></div><div class="rotation-metric"><span>Relatif vs IHSG</span><b style="color:'+(positive?Q.Leading:Q.Lagging)+'">'+pct(r.relative_return_pct)+'</b></div>'+
      (r.members?'<div class="rotation-metric"><span>Cakupan basket</span><b>'+r.members+' saham</b></div><div class="rotation-metric"><span>Mengungguli IHSG</span><b>'+num(r.breadth_pct,0)+'%</b></div>':'')+movement(r)+'<p class="rotation-muted">Kondisi relatif, bukan instruksi BUY/SELL. Leading tetap bisa turun jika IHSG turun lebih dalam.</p>'+
      (state.scope==="sectors"?'<button class="rotation-control" id="rotation-drill">Lihat saham sektor ini →</button>':'');
  }
  function tableMarkup(list) {
    if(!list.length)return '<p class="rotation-muted">Tidak ada hasil sesuai filter.</p>';
    return '<div class="rotation-table-wrap"><table class="rotation-table"><thead><tr><th>'+(state.scope==="sectors"?"Sektor":"Saham")+'</th><th>Kondisi</th><th class="numeric">Kekuatan</th><th class="numeric">Momentum</th><th class="numeric">vs IHSG '+mode().lookback+'D</th><th>Arah</th></tr></thead><tbody>'+list.map(r=>'<tr class="'+(state.selected===r.symbol?"selected":"")+'"><td><button data-symbol="'+esc(r.symbol)+'"><b>'+esc(r.symbol)+'</b><br><span class="rotation-muted">'+esc(r.name)+'</span></button></td><td>'+badge(r.quadrant)+'</td><td class="numeric">'+num(r.strength)+'</td><td class="numeric">'+num(r.momentum)+'</td><td class="numeric" style="color:'+(r.relative_return_pct>0?Q.Leading:Q.Lagging)+'">'+pct(r.relative_return_pct)+'</td><td>'+esc(r.phase)+'</td></tr>').join("")+'</tbody></table></div>';
  }
  function choose(symbol) {
    state.selected=symbol;render();
  }
  function render() {
    const data=state.data;if(!data||!root())return;
    const list=rows(),all=scopeRows(),sectors=mode().sectors;
    if(!sectors.some(r=>r.symbol===state.sector))state.sector=sectors.find(r=>r.status==="ok")?.symbol||sectors[0]?.symbol||"";
    const leading=mode().sectors.filter(r=>r.quadrant==="Leading").slice(0,3);
    const improving=mode().sectors.filter(r=>r.quadrant==="Improving").slice(0,3);
    const summary=leading.length?'<b>'+esc(leading.map(r=>r.name).join(", "))+'</b> sedang memimpin relatif terhadap IHSG.':improving.length?'<b>'+esc(improving.map(r=>r.name).join(", "))+'</b> menunjukkan pemulihan momentum relatif.':"Belum ada sektor Leading atau Improving pada horizon ini.";
    const oldDate=window.dashboardData?.market_data_date;
    const stale=oldDate&&oldDate!==data.market_data_date;
    const classification=data.classification||{};
    root().innerHTML='<div class="greet-row"><div class="greet"><h1>Rotasi <em>Sektor</em></h1><p>'+esc(LABEL[state.style])+' · penutupan '+esc(data.market_data_date)+' · benchmark IHSG</p></div></div>'+
      (stale?'<div class="rotation-status rotation-error">Data rotasi belum menyamai screening terbaru ('+esc(oldDate)+'). Hasil di bawah masih bertanggal '+esc(data.market_data_date)+'. Pembaruan otomatis sedang diperlukan.</div>':'')+
      '<p class="rotation-summary">'+summary+'</p><p class="rotation-muted">Membaca kepemimpinan relatif, bukan aliran dana atau kepastian harga naik. Basket sektor mencakup saham GLABS, bukan indeks sektoral IDX resmi.</p>'+
      '<div class="rotation-toolbar"><div class="rotation-tabs" aria-label="Horizon rotasi">'+Object.keys(LABEL).map(s=>'<button data-style="'+s+'" class="'+(state.style===s?"active":"")+'" aria-pressed="'+(state.style===s)+'">'+s[0].toUpperCase()+s.slice(1)+'</button>').join("")+'</div>'+
      '<div class="rotation-tabs" aria-label="Jenis peta"><button data-scope="sectors" class="'+(state.scope==="sectors"?"active":"")+'">Peta sektor</button><button data-scope="stocks" class="'+(state.scope==="stocks"?"active":"")+'">Saham per sektor</button></div><select class="rotation-control" id="rotation-sector" aria-label="Pilih sektor">'+sectors.map(r=>'<option value="'+esc(r.symbol)+'" '+(state.sector===r.symbol?"selected":"")+'>'+esc(r.name)+' ('+r.members+')</option>').join("")+'</select></div>'+
      '<div class="rotation-quadrants">'+Object.keys(INFO).map(q=>'<button data-quadrant="'+q+'" class="rotation-quadrant '+(state.filter===q?"active":"")+'" style="--q-color:'+Q[q]+'" aria-pressed="'+(state.filter===q)+'">'+q+'<strong>'+all.filter(r=>r.quadrant===q).length+'</strong><small>'+INFO[q]+'</small></button>').join("")+'</div>'+
      '<p class="rotation-muted">'+list.length+' / '+all.length+' '+(state.scope==="sectors"?"sektor":"saham")+' ditampilkan'+(all.some(r=>r.quadrant==="Neutral")?" · "+all.filter(r=>r.quadrant==="Neutral").length+" netral":"")+(state.filter?' · klik kondisi aktif untuk hapus filter':'')+'</p>'+
      '<div class="rotation-layout"><section class="rotation-panel"><div class="rotation-table-toolbar"><h2>'+ (state.scope==="sectors"?"Peta rotasi sektor":"Rotasi saham · "+esc(sectors.find(r=>r.symbol===state.sector)?.name||""))+'</h2><label class="rotation-muted">Jejak <select class="rotation-control" id="rotation-tail" aria-label="Panjang jejak">'+[5,10,20].map(v=>'<option value="'+v+'" '+(state.tail===v?"selected":"")+'>'+v+' sesi</option>').join("")+'</select></label></div>'+ '<div id="rotation-map-body">'+mapMarkup(list)+'</div>'+'<p class="rotation-muted">Titik = penutupan terakhir · jejak = sesi sebelumnya. Garis 100 memisahkan empat kondisi.</p></section><aside class="rotation-panel rotation-inspector">'+inspectorMarkup()+'</aside></div>'+
      '<section class="rotation-panel"><div class="rotation-table-toolbar"><h2>'+ (state.scope==="sectors"?"Ranking sektor":"Saham dalam sektor terpilih")+'</h2><input class="rotation-control" id="rotation-search" aria-label="Cari di daftar rotasi" placeholder="Cari nama atau kode…" value="'+esc(state.query)+'"><select class="rotation-control" id="rotation-sort" aria-label="Urutkan rotasi">'+[["rank","Kondisi → momentum"],["momentum","Momentum tertinggi"],["strength","Kekuatan tertinggi"],["relative_return_pct","Return relatif tertinggi"]].map(([v,l])=>'<option value="'+v+'" '+(state.sort===v?"selected":"")+'>'+l+'</option>').join("")+'</select></div><div id="rotation-table-body">'+tableMarkup(list)+'</div></section>'+
      '<details class="rotation-method"><summary>Cakupan, sumber &amp; metode</summary><p>'+data.coverage.valid+' dari '+data.coverage.requested+' saham dashboard lolos syarat 100 sesi lengkap. Universe terbatas pada saham yang tersedia di GLABS; bukan semua emiten BEI.</p><p>Klasifikasi IDX-IC: '+esc(classification.as_of)+' · '+esc(classification.refresh_status||"cache")+'. '+(classification.refresh_status==="cached_refresh_failed"?"Pembaruan sumber resmi gagal; menggunakan cache bertanggal, tanpa menebak sektor.":"")+'</p><p>'+esc(data.methodology.strength)+'<br>'+esc(data.methodology.momentum)+'<br>L = 5 / 20 / 60 sesi; m = 3 / 5 / 10 sesi. Weekly di sini horizon 20 hari bursa, bukan candle mingguan.</p><p>'+esc(data.methodology.sector)+'. '+esc(data.methodology.limitation)+'. '+esc(data.methodology.note)+'.</p><p>Sektor minimal 3 saham valid. Semua konstituen basket tetap selama 100 sesi, tanpa mengisi harga hilang. Ranking kondisi dan momentum bukan estimasi keuntungan.</p><p>Sektor tidak tersedia: '+esc(sectors.filter(r=>r.status!=="ok").map(r=>r.name+" ("+r.members+" saham)").join(", ")||"tidak ada")+'</p><details><summary>Saham tidak memenuhi syarat ('+data.coverage.excluded.length+')</summary><p>'+data.coverage.excluded.map(r=>esc(r.symbol)+": "+esc(r.reason)).join("<br>")+'</p></details><p><a href="https://www.idx.co.id/en/products/stocks/" target="_blank" rel="noopener">IDX-IC</a> · <a href="'+esc(classification.mirror_url||"https://www.idx.co.id")+'" target="_blank" rel="noopener">Asal snapshot klasifikasi</a> · <a href="sector_rotation_data.json" target="_blank" rel="noopener">Data audit</a></p></details>';
    bind();
  }
  function bind() {
    root().querySelectorAll("[data-style]").forEach(b=>b.onclick=()=>{state.style=b.dataset.style;state.selected="";render();});
    root().querySelectorAll("[data-scope]").forEach(b=>b.onclick=()=>{state.scope=b.dataset.scope;state.selected="";state.filter="";state.query="";render();});
    root().querySelectorAll("[data-quadrant]").forEach(b=>b.onclick=()=>{state.filter=state.filter===b.dataset.quadrant?"":b.dataset.quadrant;state.selected="";render();});
    root().querySelectorAll("[data-symbol]").forEach(b=>{b.onclick=()=>choose(b.dataset.symbol);if(b.tagName.toLowerCase()==="g")b.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();choose(b.dataset.symbol);}};});
    document.getElementById("rotation-sector").onchange=e=>{state.sector=e.target.value;state.scope="stocks";state.selected="";state.filter="";state.query="";render();};
    document.getElementById("rotation-sort").onchange=e=>{state.sort=e.target.value;render();};
    document.getElementById("rotation-tail").onchange=e=>{state.tail=Number(e.target.value);render();};
    document.getElementById("rotation-search").oninput=e=>{
      state.query=e.target.value;
      // Update only table/map: retain input focus and caret while typing.
      document.getElementById("rotation-table-body").innerHTML=tableMarkup(rows());
      root().querySelectorAll("#rotation-table-body [data-symbol]").forEach(b=>b.onclick=()=>choose(b.dataset.symbol));
      document.getElementById("rotation-map-body").innerHTML=mapMarkup(rows());
      root().querySelectorAll(".rotation-map [data-symbol]").forEach(b=>{b.onclick=()=>choose(b.dataset.symbol);b.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();choose(b.dataset.symbol);}};});
    };
    const drill=document.getElementById("rotation-drill");
    if(drill)drill.onclick=()=>{state.sector=state.selected;state.scope="stocks";state.selected="";state.filter="";state.query="";render();};
  }
  async function open(style) {
    if(LABEL[style])state.style=style;
    if(state.data){render();return;}
    if(state.loading)return state.loading;
    root().innerHTML='<p class="rotation-status" role="status">Memuat hasil rotasi sektor…</p>';
    state.loading=(async()=>{
      try {
        const response=await fetch("sector_rotation_data.json",{cache:"no-store"});
        if(!response.ok)throw new Error("HTTP "+response.status);
        const data=await response.json();
        if(data.schema_version!==1||data.status!=="ok"||
           !["daily","weekly","swing"].every(s=>Array.isArray(data.modes?.[s]?.sectors)&&Array.isArray(data.modes?.[s]?.stocks)))
          throw new Error("Kontrak data tidak valid");
        state.data=data;state.sector=data.modes[state.style].sectors.find(r=>r.status==="ok")?.symbol||"";render();
      } catch(error) {
        root().innerHTML='<div class="rotation-status rotation-error">Hasil rotasi belum dapat dimuat. Tidak ada angka/saham contoh yang ditampilkan.<br><span class="rotation-muted">'+esc(error.message)+'</span><br><button class="rotation-control" id="rotation-retry">Coba muat ulang</button></div>';
        document.getElementById("rotation-retry").onclick=()=>open(state.style);
      } finally {state.loading=null;}
    })();
    return state.loading;
  }
  window.GLABSRotation={open};
})();
