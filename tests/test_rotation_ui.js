const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm");
const source=fs.readFileSync("web/rotation.js","utf8");
const html=fs.readFileSync("web/index.html","utf8");
assert(html.indexOf('id="nav-rotation"')>html.indexOf('id="nav-laporan"'));
assert(html.includes('id="view-rotation"'));
for(const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)){
  if(match[1].trim())new Function(match[1]);
}
function fixture(data,ok=true){
  const root={innerHTML:"",querySelectorAll:()=>[]},elements={};
  const context={console,window:{dashboardData:{market_data_date:"2026-10-02"}},
    document:{getElementById:id=>{
      if(id==="rotation-root")return root;
      if(!root.innerHTML.includes('id="'+id+'"'))return null;
      return elements[id]||(elements[id]={innerHTML:""});
    }},
    fetch:async()=>({ok,status:ok?200:404,json:async()=>data})};
  vm.runInNewContext(source,context);
  return {root,elements,api:context.window.GLABSRotation};
}
const row={symbol:"AAA",name:"Fixture only",sector:"IDXFINANCE",status:"ok",members:3,
  quadrant:"Leading",strength:102,momentum:101,relative_return_pct:2,return_pct:3,
  phase:"Menguat",trail:[{strength:101,momentum:100.5},{strength:102,momentum:101}],
  history:[]};
const data={schema_version:1,status:"ok",market_data_date:"2026-10-02",
  coverage:{valid:3,requested:3,excluded:[]},classification:{as_of:"2026-02-03"},
  methodology:{},modes:Object.fromEntries(["daily","weekly","swing"].map(s=>[s,{
    lookback:20,sectors:[{...row,symbol:"IDXFINANCE"}],stocks:[row]}]))};
(async()=>{
  const app=fixture(data);
  await app.api.open("weekly");
  assert(app.root.innerHTML.includes("Peta rotasi sektor"));
  assert(app.root.innerHTML.includes('id="rotation-map-body"'));
  app.elements["rotation-sector"].onchange({target:{value:"IDXFINANCE"}});
  assert(app.root.innerHTML.includes("Saham dalam sektor terpilih"));
  app.elements["rotation-search"].oninput({target:{value:"not-found"}});
  assert(app.elements["rotation-map-body"].innerHTML.includes("Tidak ada hasil"));
  app.elements["rotation-search"].oninput({target:{value:"AAA"}});
  assert(app.elements["rotation-map-body"].innerHTML.includes("<svg"));
  const broken=fixture({},false);await broken.api.open();
  assert(broken.root.innerHTML.includes("Tidak ada angka/saham contoh"));
  assert(broken.root.innerHTML.includes('id="rotation-retry"'));
  const invalid=fixture({});await invalid.api.open();
  assert(invalid.root.innerHTML.includes("Kontrak data tidak valid"));
  console.log("Rotation UI contracts passed");
})().catch(error=>{console.error(error);process.exitCode=1});
