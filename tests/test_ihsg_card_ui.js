const assert=require("node:assert/strict");
const {model,points}=require("../web/ihsg-card.js");
const make=value=>({schema_version:1,symbol:"^JKSE",market_data_date:"2026-10-13",source:{provider:"purbayasadewa.id",session:"2026-10-13"},history:[{date:"2026-10-12",close:100},{date:"2026-10-13",close:value}]});
assert.equal(model(make(101),"2026-10-13").tone,"up");
assert.equal(model(make(99),"2026-10-13").tone,"down");
assert.equal(model(make(100),"2026-10-13").tone,"flat");
assert.equal(model(make(101),"2026-10-13").pct,1);
for(const v of [null,NaN,Infinity,0,-1,true,"101"])assert.throws(()=>model(make(v),"2026-10-13"));
assert.throws(()=>model(make(101),"2026-10-14"));
const stale=make(101);stale.history.pop();assert.throws(()=>model(stale,"2026-10-13"));
const duplicate=make(101);duplicate.history.push(duplicate.history[1]);assert.throws(()=>model(duplicate,"2026-10-13"));
const future=make(101);future.history.push({date:"2026-10-14",close:103});assert.throws(()=>model(future,"2026-10-13"));
const invalid=make(101);invalid.history[0].date="2026-02-31";assert.throws(()=>model(invalid,"2026-10-13"));
const wrong=make(101);wrong.source.provider="demo";assert.throws(()=>model(wrong,"2026-10-13"));
const mismatch=make(101);mismatch.source.session="2026-10-12";assert.throws(()=>model(mismatch,"2026-10-13"));
for(const close of [99,100,101])for(const p of points(make(close).history)){assert(Number.isFinite(p.x)&&Number.isFinite(p.y));assert(p.y>=0&&p.y<=100);}
console.log("IHSG card UI: real-date, up/down/flat, invalid data and chart coordinate tests passed");
