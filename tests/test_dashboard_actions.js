const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const cockpit = fs.readFileSync(path.join(__dirname,'../web/cockpit.js'),'utf8');
for(const m of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) new vm.Script(m[1]);
new vm.Script(cockpit);
assert.ok(!html.includes('Duplikat screener'));
assert.ok(!html.includes('<span class="link">'));
assert.ok(!cockpit.includes("document.querySelectorAll('.pill')"));
assert.ok(!cockpit.includes('data.summary.strongest_accumulation?.ticker'));
assert.ok(html.includes('topButton.dataset.ticker = tp?.ticker'));
assert.ok(html.includes('wyckoffButton.dataset.ticker = bestAccum?.ticker'));
assert.ok(html.includes('topButton.disabled = !tp'));
assert.ok(html.includes('wyckoffButton.disabled = !bestAccum'));
const source=html.slice(html.indexOf('function openOverviewDetail'),html.indexOf('function showView'));
const calls=[],search={value:'ANTM'}, context={window:{openAnalysis:(...a)=>calls.push(a)},document:{getElementById:()=>search},showView:n=>calls.push(n)};
vm.createContext(context);vm.runInContext(source,context);
context.openOverviewDetail({dataset:{ticker:'ADES'},disabled:false},'score');
assert.deepEqual(calls.pop(),['ADES','score']);
context.openOverviewDetail({dataset:{ticker:'MDKI'},disabled:false},'wyckoff');
assert.deepEqual(calls.pop(),['MDKI','wyckoff']);
context.openOverviewDetail({dataset:{ticker:''},disabled:true},'score');assert.equal(calls.length,0);
for(const kind of ['signal','watchlist','trend','vwap']) {
 search.value='ANTM';context.openOverviewList(kind);
 assert.equal(search.value,'');assert.equal(calls.pop(),kind==='watchlist'?'watchlist':'screener');
 if(kind!=='watchlist') assert.equal(context.SORT_STATE.key,{signal:'score',trend:'trend',vwap:'vwap_signal'}[kind]);
}
console.log('Dashboard actions: routes, ticker selection, empty state, syntax and placeholder checks passed.');
