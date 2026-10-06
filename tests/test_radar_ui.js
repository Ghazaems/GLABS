const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm");
const source=fs.readFileSync("web/radar.js","utf8");
const html=fs.readFileSync("web/index.html","utf8");
assert(html.indexOf('id="nav-radar"')>html.indexOf('id="nav-rotation"'));
assert(html.includes('id="view-radar"'));
assert(html.includes('id="radar-home-body"'));
for(const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)){
  if(match[1].trim())new Function(match[1]);
}
function fixture(data,ok=true){
  const nodes={},controls={};
  const make=id=>({innerHTML:"",textContent:"",querySelectorAll(selector){
    const attr=selector.match(/^\[([^\]]+)\]$/)?.[1];
    if(!attr)return [];
    const found=[...this.innerHTML.matchAll(new RegExp(attr+'="([^"]*)"',"g"))];
    return found.map(m=>{
      const key=attr+":"+m[1],camel=attr.replace(/^data-/,"").replace(/-([a-z])/g,(_,c)=>c.toUpperCase());
      const el={dataset:{[camel]:m[1]},onclick:null};
      controls[key]=el;return el;
    });
  }});
  nodes["radar-root"]=make("radar-root");
  nodes["radar-home-body"]=make("radar-home-body");
  const context={console,window:{addEventListener(){},dashboardData:{market_data_date:"2026-10-02",watchlist:[{ticker:"AAAA"}]}},
    document:{getElementById:id=>{
      if(nodes[id])return nodes[id];
      if(!Object.values(nodes).some(n=>n.innerHTML.includes('id="'+id+'"')))return null;
      return nodes[id]=make(id);
    }},
    fetch:async()=>({ok,status:ok?200:404,json:async()=>data})};
  vm.runInNewContext(source,context);
  return {nodes,controls,api:context.window.GLABSRadar};
}
const risk={ticker:"AAAA",kind:"composite",before:"Beli",after:"Jual",title:"Melemah",
  meaning:"Fixture risk only",group:"risk",priority:1};
const better={...risk,kind:"rotation",before:"Improving",after:"Leading",title:"Baru Leading",
  meaning:"Fixture opportunity only",group:"opportunity",priority:4};
const full={...risk,kind:"full_vwap",before:"HOLD",after:"EXIT",title:"Struktur bullish rusak"};
const data={schema_version:1,status:"ok",market_data_date:"2026-10-02",
  previous_session:"2026-10-01",comparison_status:"ready",
  coverage:{common:1,new_tickers:[],missing_tickers:[]},
  modes:Object.fromEntries(["daily","weekly","swing"].map(s=>[s,{
    events:s==="daily"?[risk,better]:[],rotation_baseline_available:true}])),
  full_vwap_events:[full]};
(async()=>{
  const app=fixture(data);
  await app.api.open("daily");
  assert.equal((app.nodes["radar-list"].innerHTML.match(/class="radar-item"/g)||[]).length,1);
  assert(app.nodes["radar-list"].innerHTML.includes("<summary>Kenapa?</summary>"));
  assert(app.nodes["radar-list"].innerHTML.includes("Sinyal campuran"));
  assert(app.nodes["radar-root"].innerHTML.includes("<summary>Pilihan analisis</summary>"));
  assert(!app.nodes["radar-root"].innerHTML.includes("Baru masuk Leading"));
  app.controls["data-filter:opportunity"].onclick();
  assert(app.nodes["radar-list"].innerHTML.includes("<b>Baru Leading."));
  app.controls["data-scope:full_vwap"].onclick();
  assert(app.nodes["radar-list"].innerHTML.includes("HOLD"));
  assert(app.nodes["radar-list"].innerHTML.includes("EXIT"));
  assert(app.nodes["radar-root"].innerHTML.includes("bukan sinyal Daily/Weekly/Swing terpisah"));
  const search=app.nodes["radar-search"];search.oninput({target:{value:"ZZZZ"}});
  assert(app.nodes["radar-list"].innerHTML.includes("Tidak ada perubahan"));
  assert.equal(search,app.nodes["radar-search"]);
  search.oninput({target:{value:"AAAA"}});
  assert(app.nodes["radar-list"].innerHTML.includes("EXIT"));
  app.api.home("weekly");
  assert(app.nodes["radar-home-body"].innerHTML.includes("Tidak ada perubahan"));
  const unavailable=fixture({},false);await unavailable.api.open();
  assert(unavailable.nodes["radar-root"].innerHTML.includes("HTTP 404"));
  assert(!unavailable.nodes["radar-home-body"].innerHTML.includes("AAAA"));
  const noBaseline=fixture({...data,comparison_status:"baseline_unavailable",
    modes:Object.fromEntries(["daily","weekly","swing"].map(s=>[s,{events:[],rotation_baseline_available:false}]))});
  await noBaseline.api.open();
  assert(noBaseline.nodes["radar-root"].innerHTML.includes("Belum ada data pembanding"));
  console.log("Radar UI contracts passed");
})().catch(e=>{console.error(e);process.exitCode=1});
