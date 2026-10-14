(() => {
  const catalog = [
    ["^GSPC","S&P 500","AS"],["^IXIC","Nasdaq Composite","AS"],["^DJI","Dow Jones","AS"],
    ["^N225","Nikkei 225","Jepang"],["^HSI","Hang Seng","Hong Kong"],
    ["000001.SS","Shanghai Composite","China"],["^GDAXI","DAX P","Jerman"],["^FTSE","FTSE 100","Inggris"]
  ];
  const esc = x => String(x ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const number = x => Number(x).toLocaleString("id-ID",{minimumFractionDigits:2,maximumFractionDigits:2});
  function render(feed) {
    const rows = new Map((feed?.schema_version === 1 && Array.isArray(feed.indices) ? feed.indices : []).map(x=>[x.symbol,x]));
    return catalog.map(([symbol,name,region])=>{
      const row=rows.get(symbol);
      const valid=row && ["ok","cached"].includes(row.status) && Number.isFinite(row.close) && row.close>0 && Number.isFinite(row.change_pct) && /^\d{4}-\d{2}-\d{2}$/.test(row.date);
      const direction=valid ? row.change_pct>0?"up":row.change_pct<0?"down":"flat" : "flat";
      const title=valid ? "Penutupan "+row.date+" · "+region+(row.status==="cached"?" · Data terakhir tersimpan; fetch terbaru gagal":"") : "Data belum tersedia";
      return '<div class="global-index-row" title="'+esc(title)+'"><div class="global-index-name">'+esc(name)+
        '<small>'+esc(region)+(valid?' · '+esc(row.date.slice(5).split("-").reverse().join("/")):'')+
        (row?.status==="cached"?' · tersimpan':'')+'</small></div><span class="global-index-close">'+
        (valid?number(row.close):"—")+'</span><span class="global-index-change '+direction+'">'+
        (valid?(row.change_pct>0?"+":"")+number(row.change_pct)+"%":"—")+'</span></div>';
    }).join("");
  }
  if(typeof module==="object" && module.exports){module.exports={render};return;}
  async function boot(){
    const body=document.getElementById("global-indices-body"),note=document.getElementById("global-indices-note");
    if(!body)return;
    body.innerHTML=window.GlabsLoading?.html("rows","Memuat indeks global…") || "Memuat indeks global…";
    try {
      const response=await fetch("global_indices_data.json",{cache:"no-store"});
      if(!response.ok)throw new Error("Feed unavailable");
      const feed=await response.json();
      if(feed.schema_version!==1 || !Array.isArray(feed.indices))throw new Error("Invalid feed");
      body.innerHTML=render(feed);
      note.textContent="Penutupan terakhir · tanggal tiap pasar berbeda";
    } catch(_){
      body.innerHTML=render(null);
      note.textContent="Data indeks global belum dapat dimuat.";
    }
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();
})();
