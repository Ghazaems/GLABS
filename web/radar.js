(() => {
  "use strict";
  const state={data:null,loading:null,style:"daily",scope:"timeframe",filter:"all",query:"",limit:30};
  const styles={daily:"Daily · 5D",weekly:"Weekly · 20D",swing:"Swing · 60D"};
  const colors={risk:"#ff453a",opportunity:"#32d74b",watch:"#ffd60a"};
  const labels={risk:"Evaluasi risiko",opportunity:"Membaik",watch:"Pantau"};
  const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const root=()=>document.getElementById("radar-root");
  function groups(events) {
    const map=new Map();
    for(const e of events){
      if(!map.has(e.ticker))map.set(e.ticker,{ticker:e.ticker,events:[]});
      map.get(e.ticker).events.push(e);
    }
    return [...map.values()].map(r=>({...r,primary:r.events[0]}));
  }
  const events=()=>state.scope==="full_vwap"?state.data.full_vwap_events:state.data.modes[state.style].events;
  function visible() {
    return groups(events()).filter(r=>(state.filter==="all"||r.events.some(e=>e.group===state.filter))&&
      (!state.query||r.ticker.toLowerCase().includes(state.query.toLowerCase())))
      .map(r=>({...r,primary:state.filter==="all"?r.primary:r.events.find(e=>e.group===state.filter)}));
  }
  function transition(e){return '<div class="radar-change"><span>'+esc(e.kind==="composite"?"Komposit":e.kind==="rotation"?"Rotasi":e.kind==="vwap_focus"?"Kondisi VWAP":"Full VWAP")+'</span><span>'+esc(e.before)+'</span><span aria-label="berubah menjadi">→</span><b>'+esc(e.after)+'</b></div>';}
  function card(r) {
    const p=r.primary;
    return '<article class="radar-item"><div class="radar-item-head"><span class="radar-ticker">'+esc(r.ticker)+'</span><span class="radar-tag" style="--radar-color:'+colors[p.group]+'">'+labels[p.group]+'</span></div><p class="radar-meaning"><b>'+esc(p.title)+'.</b> '+esc(p.meaning)+'</p>'+transition(p)+
      (r.events.length>1?'<details><summary>'+ (r.events.length-1)+' perubahan lainnya</summary>'+r.events.slice(1).map(e=>transition(e)+'<p>'+esc(e.meaning)+'</p>').join("")+'</details>':'')+
      '<button class="radar-action" data-analysis="'+esc(r.ticker)+'">Buka analisis saham →</button></article>';
  }
  function bindAnalysis(parent) {
    parent.querySelectorAll("[data-analysis]").forEach(b=>b.onclick=()=>{
      const ticker=b.dataset.analysis;
      if(window.dashboardData?.watchlist?.some(r=>r.ticker===ticker)&&window.openAnalysis)window.openAnalysis(ticker,"vwap");
    });
  }
  function renderList(){
    const target=document.getElementById("radar-list");if(!target)return;
    const list=visible();
    target.innerHTML=list.length?list.slice(0,state.limit).map(card).join("")+
      (list.length>state.limit?'<button class="radar-control" id="radar-more">Tampilkan 30 lagi ('+(list.length-state.limit)+' tersisa)</button>':''):
      '<div class="radar-status">Tidak ada perubahan sesuai pilihan ini. Sinyal yang tetap sama tidak diulang sebagai sinyal baru.</div>';
    bindAnalysis(target);
    const more=document.getElementById("radar-more");if(more)more.onclick=()=>{state.limit+=30;renderList();};
    const count=document.getElementById("radar-count");if(count)count.textContent=list.length+" saham dengan perubahan";
  }
  function render(){
    if(!state.data||!root())return;
    const d=state.data, mode=d.modes[state.style];
    const latest=window.dashboardData?.market_data_date;
    const stale=latest&&latest!==d.market_data_date;
    const counts=Object.fromEntries(Object.keys(labels).map(g=>[g,groups(events()).filter(r=>r.events.some(e=>e.group===g)).length]));
    root().innerHTML='<div class="greet-row"><div class="greet"><h1>Radar <em>Sinyal</em></h1><p>'+esc(d.market_data_date)+(d.previous_session?' dibanding screening '+esc(d.previous_session):' · belum ada sesi pembanding')+'</p></div></div>'+
      (stale?'<div class="radar-status">Radar belum menyamai screening '+esc(latest)+'. Hasil di bawah masih bertanggal '+esc(d.market_data_date)+'.</div>':'')+
      '<p class="radar-summary">Lihat apa yang <b>baru berubah</b>, bukan daftar sinyal yang berulang.</p>'+
      '<div class="radar-toolbar"><div class="radar-tabs" aria-label="Jenis analisis radar">'+[["timeframe","Per timeframe"],["full_vwap","Full VWAP 5/20/60"]].map(([s,l])=>'<button data-scope="'+s+'" class="'+(state.scope===s?"active":"")+'" aria-pressed="'+(state.scope===s)+'">'+l+'</button>').join("")+'</div>'+
      (state.scope==="timeframe"?'<div class="radar-tabs" aria-label="Horizon radar">'+Object.keys(styles).map(s=>'<button data-style="'+s+'" class="'+(state.style===s?"active":"")+'" aria-pressed="'+(state.style===s)+'">'+s[0].toUpperCase()+s.slice(1)+'</button>').join("")+'</div>':'')+'</div>'+
      '<p class="radar-note">'+(state.scope==="timeframe"?esc(styles[state.style])+': perubahan komposit, kondisi VWAP horizon ini, dan rotasi saham.':'BUY/HOLD/WAIT/REDUCE/EXIT/AVOID berasal dari Full VWAP gabungan; bukan sinyal Daily/Weekly/Swing terpisah.')+' Risiko ditampilkan lebih dahulu, bukan ranking keuntungan.</p>'+
      (d.comparison_status!=="ready"?'<div class="radar-status">Belum ada screening sebelumnya dengan metode yang kompatibel. Tidak ada perubahan yang dibuat-buat.</div>':'')+
      (state.scope==="timeframe"&&!mode.rotation_baseline_available?'<div class="radar-status">Pembanding rotasi sebelumnya belum tersedia. “Baru masuk Leading” akan muncul setelah ada dua sesi rotasi berbeda yang tersimpan.</div>':'')+
      '<div class="radar-filters">'+[["all","Semua"],...Object.entries(labels)].map(([g,l])=>'<button class="radar-filter '+(state.filter===g?"active":"")+'" data-filter="'+g+'">'+l+(g==="all"?"":" · "+counts[g])+'</button>').join("")+'<input class="radar-control" id="radar-search" type="search" placeholder="Cari saham…" aria-label="Cari saham di radar" value="'+esc(state.query)+'"></div>'+
      '<p class="radar-note" id="radar-count"></p><div class="radar-list" id="radar-list"></div>'+
      '<details class="radar-note" style="margin-top:20px"><summary>Cakupan &amp; cara membaca</summary><p>'+d.coverage.common+' saham ditemukan di kedua sesi. Saham baru ('+d.coverage.new_tickers.length+') dan saham hilang ('+d.coverage.missing_tickers.length+') tidak dianggap sebagai perubahan sinyal.</p><p>Setiap angka hitungan kategori adalah jumlah saham unik. Satu saham dapat memiliki perubahan membaik sekaligus risiko pada analisis berbeda.</p><p>Harga per saham harus sesuai tanggal screening. Perubahan metode/setting tidak dibandingkan sebagai sinyal baru. Saat akhir pekan atau libur, gunakan sesi screening terakhir—bukan tanggal komputer.</p><p>Perubahan sinyal bukan kepastian profit. REDUCE/EXIT perlu dibaca bersama kepemilikan posisi dan rencana risiko Anda.</p><a href="radar_data.json" target="_blank" rel="noopener">Data audit</a></details>';
    root().querySelectorAll("[data-scope]").forEach(b=>b.onclick=()=>{state.scope=b.dataset.scope;state.filter="all";state.query="";state.limit=30;render();});
    root().querySelectorAll("[data-style]").forEach(b=>b.onclick=()=>{state.style=b.dataset.style;state.filter="all";state.query="";state.limit=30;render();});
    root().querySelectorAll("[data-filter]").forEach(b=>b.onclick=()=>{state.filter=b.dataset.filter;state.limit=30;render();});
    document.getElementById("radar-search").oninput=e=>{state.query=e.target.value;state.limit=30;renderList();};
    renderList();
  }
  function home(style){
    if(styles[style])state.style=style;
    const el=document.getElementById("radar-home-body");if(!el)return;
    const d=state.data;
    if(!d){el.innerHTML='<p class="radar-note">Memuat perubahan screening…</p>';return;}
    const date=window.dashboardData?.market_data_date;
    if(date&&date!==d.market_data_date){el.innerHTML='<p class="radar-note">Radar masih bertanggal '+esc(d.market_data_date)+', belum menyamai screening '+esc(date)+'.</p>';return;}
    const list=groups(d.modes[state.style].events).slice(0,3);
    el.innerHTML='<p class="radar-note">'+esc(styles[state.style])+' · '+esc(d.market_data_date)+(d.previous_session?' vs '+esc(d.previous_session):'')+'</p>'+
      (d.comparison_status!=="ready"?'<p class="radar-note">Pembanding valid belum tersedia; tidak ada sinyal baru yang diasumsikan.</p>':
       list.length?'<div class="radar-home-grid">'+list.map(r=>'<button class="radar-home-item" data-radar-ticker="'+esc(r.ticker)+'"><strong>'+esc(r.ticker)+'</strong><span>'+esc(r.primary.title)+'</span><small>'+esc(r.primary.before)+' → '+esc(r.primary.after)+'</small></button>').join("")+'</div>':'<p class="radar-note">Tidak ada perubahan '+esc(styles[state.style])+'. Bukan berarti tidak ada sinyal aktif.</p>');
    el.querySelectorAll("[data-radar-ticker]").forEach(b=>b.onclick=()=>{
      state.scope="timeframe";state.filter="all";state.query=b.dataset.radarTicker;
      if(window.showView)window.showView("radar");
    });
  }
  async function load(){
    if(state.data)return state.data;
    if(state.loading)return state.loading;
    state.loading=(async()=>{
      try{
        const response=await fetch("radar_data.json",{cache:"no-store"});
        if(!response.ok)throw new Error("HTTP "+response.status);
        const d=await response.json();
        if(d.schema_version!==1||d.status!=="ok"||!Array.isArray(d.full_vwap_events)||
          !Object.keys(styles).every(s=>Array.isArray(d.modes?.[s]?.events)))throw new Error("Kontrak radar tidak valid");
        state.data=d;home();render();return d;
      }catch(e){
        const el=document.getElementById("radar-home-body");if(el)el.innerHTML='<p class="radar-note">Hasil radar belum dapat dimuat. Tidak ada sinyal contoh.</p>';
        if(root())root().innerHTML='<div class="radar-status">Radar belum dapat dimuat ('+esc(e.message)+').<br><button class="radar-control" id="radar-retry">Coba muat ulang</button></div>';
        const retry=document.getElementById("radar-retry");if(retry)retry.onclick=()=>open(state.style);
      }finally{state.loading=null;}
    })();return state.loading;
  }
  async function open(style){if(styles[style])state.style=style;await load();render();}
  window.GLABSRadar={open,home};
  window.addEventListener("dashboard-ready",()=>{home(typeof currentStyle!=="undefined"?currentStyle:"daily");load();});
  if(window.dashboardData){home(typeof currentStyle!=="undefined"?currentStyle:"daily");load();}
})();
