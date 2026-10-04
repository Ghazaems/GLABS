const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm");
const C=require("../web/rotation-core.js"),source=fs.readFileSync("web/rotation.js","utf8"),html=fs.readFileSync("web/index.html","utf8");
assert(html.indexOf('id="nav-rotation"')>html.indexOf('id="nav-laporan"'));
assert(html.indexOf('src="rotation-core.js"')<html.indexOf('src="rotation.js"'));
new Function(source);
const dates=[];for(let i=0;i<390;i++){const d=new Date(Date.UTC(2025,8,8+i));if(d.getUTCDay()%6!==0)dates.push(d.toISOString().slice(0,10));}
const h=dates.map((date,i)=>({date,close:100+i,benchmark:100+i}));
const matching={symbol:"MATCH",name:"Fixture only",history:h};
assert.equal(C.calculate(matching,{interval:"daily",lookback:20,momentum:5,smooth:3}).quadrant,"Neutral");
assert(C.periods(matching,"weekly").length<C.periods(matching,"daily").length);
for(const p of C.periods(matching,"weekly"))assert(h.some(b=>b.date===p.date));
const relative=C.movement([matching],dates.at(-1),"1M",true);
assert(relative.available);assert(relative.series[0].points.every(p=>Math.abs(p.value)<1e-9));
assert.equal(C.movement([matching],dates.at(-1),"1M",false).series[0].points[0].value,0);
assert.equal(C.movement([{...matching,history:h.slice(-100)}],dates.at(-1),"1Y",false).available,false);
assert.equal(C.rangeStart("2026-03-31","1M"),"2026-02-28");
assert.equal(C.calculate({...matching,history:h.slice(-5)},{interval:"daily",lookback:20,momentum:5,smooth:3}),null);
const end=dates.at(-1);
function fixture(data,ok=true){
 const nodes={},controls={};
 const make=id=>({innerHTML:"",textContent:"",hidden:false,tagName:"div",dataset:{},classList:{toggle(){}},setAttribute(){},
 querySelectorAll(selector){
   const attr=selector.match(/^\[([^\]]+)\]$/)?.[1];if(!attr)return [];
   const text=this.innerHTML+(id==="rotation-root"?Object.entries(nodes).filter(([k])=>k!==id).map(([,n])=>n.innerHTML).join(""):""),found=[...text.matchAll(new RegExp(attr+'="([^"]*)"',"g"))];
   return found.map(m=>{const key=attr+":"+m[1],camel=attr.replace(/^data-/,"").replace(/-([a-z])/g,(_,c)=>c.toUpperCase());
     const el=make(key);el.dataset[camel]=m[1];controls[key]=el;return el;});
 },querySelector(){return null;}});
 nodes["rotation-root"]=make("rotation-root");
 const context={console,window:{GLABSRotationCore:C,dashboardData:{market_data_date:end}},
 document:{getElementById:id=>{
   if(nodes[id])return nodes[id];
   if(!Object.values(nodes).some(n=>n.innerHTML.includes('id="'+id+'"')))return null;
   return nodes[id]=make(id);}},
 fetch:async()=>({ok,status:ok?200:404,json:async()=>data})};
 vm.runInNewContext(source,context);return {nodes,controls,api:context.window.GLABSRotation};
}
const row={...matching,symbol:"AAAA",sector:"IDXFINANCE",status:"ok",members:3,chart_history:h};
const other={...row,symbol:"BBBB",history:h.map((p,i)=>({...p,close:p.close*(1+i/2000)})),chart_history:h.map((p,i)=>({...p,close:p.close*(1+i/2000)}))};
const data={schema_version:1,status:"ok",market_data_date:end,coverage:{valid:2,requested:2,excluded:[]},classification:{as_of:"2026-02-03"},methodology:{},
 modes:{weekly:{sectors:[{...row,symbol:"IDXFINANCE",name:"Finance fixture"}],stocks:[row,other]}}};
(async()=>{
 const app=fixture(data);await app.api.open("weekly");
 for(const label of ["Settings","Rotation Map","Compare stocks","Sector Movement","Foreign Flow","Normalized","vs COMPOSITE"])assert(app.nodes["rotation-root"].innerHTML.includes(label),label);
 const tail=app.nodes["rotation-tail"];tail.oninput({target:{value:"10"}});
 assert(app.nodes["rotation-map-body"].innerHTML.includes("<svg"));
 const search=app.nodes["rotation-search"];search.oninput({target:{value:"not-found"}});
 assert(app.nodes["rotation-map-body"].innerHTML.includes("Tidak ada"));
 assert.equal(search,app.nodes["rotation-search"]);
 search.oninput({target:{value:"IDXFINANCE"}});
 assert(app.nodes["rotation-map-body"].innerHTML.includes("<svg"));
 app.nodes["rotation-reset-filter"].onclick();
 app.controls["data-map-symbol:IDXFINANCE"].onclick();
 assert(app.nodes["rotation-inspector"].innerHTML.includes("IDXFINANCE"));
 app.controls["data-drill:IDXFINANCE"].onclick();
 assert(app.nodes["rotation-root"].innerHTML.includes("Rotasi saham dalam IDXFINANCE"));
 app.controls["data-interval:weekly"].onclick();
 assert(app.nodes["rotation-root"].innerHTML.includes("penutupan akhir minggu"));
 assert(app.nodes["rotation-root"].innerHTML.includes("Rotation Map"));
 app.nodes["rotation-compare"].oninput({target:{value:"AAAA"}});
 app.controls["data-add-pick:AAAA"].onclick();
 assert(app.nodes["rotation-root"].innerHTML.includes('data-remove-pick="AAAA"'));
 app.controls["data-range:3M"].onclick();
 assert(app.nodes["rotation-root"].innerHTML.includes('data-range="3M" class="active"'));
 app.controls["data-relative:true"].onclick();
 assert(app.nodes["rotation-root"].innerHTML.includes("Return rasio harga/IHSG"));
 const broken=fixture({},false);await broken.api.open();assert(broken.nodes["rotation-root"].innerHTML.includes("HTTP 404"));
 const invalid=fixture({});await invalid.api.open();assert(invalid.nodes["rotation-root"].innerHTML.includes("Kontrak data tidak valid"));
 console.log("Rotation core and reference-flow UI contracts passed");
})().catch(error=>{console.error(error);process.exitCode=1});
