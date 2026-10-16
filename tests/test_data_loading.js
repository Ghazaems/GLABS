const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/data-loader.js'),'utf8');
const sourceActivity=fs.readFileSync(require('node:path').join(__dirname,'../web/activity.js'),'utf8');
async function run(){
  const requests=[];
  let failures=0,wrong=false;
  const overview={market_data_date:'2026-10-16',watchlist:[{ticker:'AKKU',last_price_date:'2026-10-15',score:30}],ui_assets:{schema_version:1,dashboard_sha256:'hash',details_base:'stock/',activity_base:'activity/',activity_sha256:'activityhash',activity_session:'2026-10-16'}};
  const context={window:{dispatchEvent(){}},Event:class{},fetch:async(url)=>{
    requests.push(url);
    if(url==='dashboard_overview.json')return{ok:true,json:async()=>overview};
    if(url.startsWith('stock/')){
      if(failures++===0)throw Error('temporary offline');
      return{ok:true,json:async()=>({source_sha256:wrong?'wrong':'hash',market_data_date:'2026-10-16',stock:{...overview.watchlist[0],price_history:[{date:'2026-10-15',close:105}]}})};
    }
    if(url==='activity/AKKU.json')return{ok:true,json:async()=>({source_sha256:'activityhash',provider:'purbayasadewa.id',method_version:2,market_data_date:'2026-10-16',stocks:{AKKU:{status:'unavailable'}}})};
    throw Error('Unexpected request '+url);
  }};
  vm.createContext(context);vm.runInContext(source,context);vm.runInContext(sourceActivity,context);
  const api=context.window.GlabsData;
  await Promise.all([api.overview(),api.overview()]);
  assert.deepEqual(requests,['dashboard_overview.json'],'overview must not eagerly download histories/activity');
  await assert.rejects(api.detail('AKKU'));
  const [one,two]=await Promise.all([api.detail('AKKU'),api.detail('AKKU')]);
  assert.equal(one,two);assert.equal(failures,2,'deduplicate concurrent detail requests, allow retry after failure');
  assert.equal(one.last_price_date,'2026-10-15');assert.equal(one.score,30);
  await assert.rejects(api.detail('MISSING'));
  await assert.rejects(api.activity('2026-10-15','AKKU'));
  await context.window.GlabsActivity.load('2026-10-16','AKKU');
  assert.equal(context.window.GlabsActivity.record('AKKU','2026-10-16'),null);
  const calls=requests.length;
  await context.window.GlabsActivity.load('2026-10-16','AKKU');
  assert.equal(requests.length,calls,'unavailable ticker does not trigger a fetch loop');
  assert.ok(!requests.some(url=>url==='purbaya_activity_data.json'||url==='dashboard_data.json'));
  // A mismatched publication is never merged into a live row.
  const other={...context,window:{},fetch:async url=>({ok:true,json:async()=>url==='dashboard_overview.json'?overview:{source_sha256:'wrong',market_data_date:'2026-10-16',stock:{ticker:'AKKU',score:999}}})};
  vm.createContext(other);vm.runInContext(source,other);
  await assert.rejects(other.window.GlabsData.detail('AKKU'));
  assert.equal(overview.watchlist[0].score,30);
  console.log('Lazy data: deduplication, retry, session/SHA guard, no eager full feeds, no fabricated missing ticker.');
}
run().catch(error=>{console.error(error);process.exitCode=1});
