/* Public GLABS math; never labels this as proprietary JdK RRG. */
(function(){
"use strict";
const finite=n=>Number.isFinite(n)&&n>0;
function history(row){return (row.chart_history||row.history||[]).filter(p=>/^\d{4}-\d{2}-\d{2}$/.test(p.date)&&new Date(p.date+"T12:00:00Z").getUTCDay()%6!==0&&finite(p.close)&&finite(p.benchmark)).sort((a,b)=>a.date.localeCompare(b.date));}
function periods(row,interval){
 const h=history(row); if(interval==="daily")return h;
 const groups=new Map();
 for(const p of h){const d=new Date(p.date+"T12:00:00Z");d.setUTCDate(d.getUTCDate()-((d.getUTCDay()+6)%7));groups.set(d.toISOString().slice(0,10),p);}
 return [...groups.values()];
}
function quadrant(s,m){if(Math.abs(s-100)<1e-8||Math.abs(m-100)<1e-8)return "Neutral";return s>100?(m>100?"Leading":"Weakening"):(m>100?"Improving":"Lagging");}
function calculate(row,settings){
 const h=periods(row,settings.interval),L=settings.lookback,m=settings.momentum,s=settings.smooth;
 const ratios=h.map(p=>p.close/p.benchmark),strength=h.map(()=>null),trail=[];
 for(let i=L+s-1;i<h.length;i++){
   strength[i]=100*Array.from({length:s},(_,j)=>ratios[i-j]/ratios[i-j-L]).reduce((a,b)=>a+b,0)/s;
   if(strength[i-m]!=null)trail.push({date:h[i].date,strength:strength[i],momentum:100*strength[i]/strength[i-m]});
 }
 if(trail.length<2)return null;
 const last=trail.at(-1),prev=trail.at(-2),q=quadrant(last.strength,last.momentum),before=quadrant(prev.strength,prev.momentum);
 const dx=last.strength-prev.strength,dy=last.momentum-prev.momentum;
 const phase=q!==before?before+" → "+q:dx>0&&dy>0?"Menguat":dx<0&&dy<0?"Melemah":dx>0?"Kekuatan naik · momentum turun":dy>0?"Momentum pulih · kekuatan turun":"Stabil";
 return {...row,...last,quadrant:q,phase,delta_strength:dx,delta_momentum:dy,speed:Math.hypot(dx,dy),trail,periods:h.length};
}
function rangeStart(end,range){const d=new Date(end+"T12:00:00Z"),months={ "1M":1,"3M":3,"6M":6,"1Y":12 }[range];const day=d.getUTCDate();d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()-months);const year=d.getUTCFullYear(),month=d.getUTCMonth();const last=new Date(Date.UTC(year,month+1,0)).getUTCDate();d.setUTCDate(Math.min(day,last));return d.toISOString().slice(0,10);}
function movement(rows,end,range,relative,benchmark={symbol:"COMPOSITE",name:"IHSG (Composite)"}){
 const start=rangeStart(end,range),candidates=rows.map(r=>({row:r,history:history(r).filter(p=>p.date<=end)})).filter(r=>r.history.length);
 const tolerance=new Date(start+"T12:00:00Z");tolerance.setUTCDate(tolerance.getUTCDate()+7);const maxStart=tolerance.toISOString().slice(0,10);
 const missing=candidates.filter(r=>r.history[0].date>maxStart).map(r=>r.row.symbol);
 const all=candidates.filter(r=>r.history[0].date<=maxStart);
 if(!all.length)return {series:[],available:false,start:candidates.map(r=>r.history[0].date).sort().at(-1)||start,end,missing};
 const common=all[0].history.filter(p=>p.date>=start).map(p=>p.date).filter(date=>all.every(r=>r.history.some(p=>p.date===date)));
 if(common.length<2)return {series:[],available:false,start,end,missing};
 const first=common[0],series=all.map(({row,history:h})=>{const lookup=new Map(h.map(p=>[p.date,p])),base=lookup.get(first);
 return {symbol:row.symbol,name:row.name,points:common.map(date=>{const p=lookup.get(date);return {date,value:relative?100*((p.close/base.close)/(p.benchmark/base.benchmark)-1):100*(p.close/base.close-1)};})};});
 const firstRow=new Map(all[0].history.map(p=>[p.date,p])),base=firstRow.get(first).benchmark;
 series.push({symbol:benchmark.symbol,name:benchmark.name,benchmark:true,points:common.map(date=>({date,value:relative?0:100*(firstRow.get(date).benchmark/base-1)}))});
 // One-year is never silently represented by a shorter dataset.
 const coverageStart=all.map(r=>r.history[0].date).sort().at(-1);
 return {series,available:coverageStart<=maxStart,start:first,end:common.at(-1),requestedStart:start,missing};
}
function alignHistory(prices,benchmark){
 const byDate=new Map(prices),out=[];let lastMissing=-1;
 for(const [date,b] of benchmark){
  const c=byDate.get(date);
  if(!finite(c)||!finite(b)){lastMissing=out.length;out.push(null);}
  else out.push({date,close:c,benchmark:b});
 }
 return out.slice(lastMissing+1).filter(Boolean);
}
const api={history,periods,quadrant,calculate,rangeStart,movement,alignHistory};
if(typeof module!=="undefined"&&module.exports)module.exports=api;else window.GLABSRotationCore=api;
})();