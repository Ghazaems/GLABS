
const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=require('node:fs').readFileSync(require('node:path').join(__dirname,'../web/cockpit.js'),'utf8');
new vm.Script(source);
var context={window:{addEventListener(){}},console};
vm.createContext(context);
vm.runInContext(source.replace('  window.openAnalysis = open;', '  window.__test={summaryFor,modePanel,state}; window.openAnalysis = open;'),context);
var test=context.window.__test, checks=0;
function check(ok){assert.ok(ok);checks++;}
var stock={signal:'pantau',score:-30,trend:'uptrend',support:187,resistance:254,wyckoff:{bias:'conflicting',tr_low:187,tr_high:254,events:[{type:'BC',date:'2026-04-30'},{type:'UT',date:'2026-08-28'},{type:'SOS',date:'2026-08-10'}]},score_breakdown:{trend:30,wyckoff:-40},vwap_signal:'WAIT',vwap_analysis:{regime:'sideways'},comparative_strength:{relative_strength_trend:'outperforming'}};
check(test.summaryFor(stock,'wyckoff').title==='Arah belum jelas');
check(test.summaryFor(stock,'wyckoff').rows.at(-1)[1].startsWith('UT'));
for(var mode of ['wyckoff','trend','vwap','strength','volatility','score']){
 test.state.mode=mode;
 var html=test.modePanel(stock);
 check(html.includes('INTINYA') && html.includes('<details') && !html.includes('NaN'));
 check(!html.includes('CHECKLIST MANUAL'));
 check(!/<details[^>]*open/.test(html));
}
for(var signal of ['BUY','HOLD','WAIT','REDUCE','EXIT','AVOID']){
 check(test.summaryFor({...stock,vwap_signal:signal},'vwap').title!=='Data belum cukup');
}
check(test.summaryFor({...stock,signal:'jual'},'score').title==='Risiko lebih dominan');
check(test.summaryFor({...stock,signal:'beli'},'score').title==='Kandidat untuk dipantau');
check(test.summaryFor(stock,'score').rows[0][1].includes('−100 hingga +100'));
check(test.summaryFor({...stock,volatility:{status:'ok',current_forecast_vol_pct:1.3,lower_band_95:[100,90],upper_band_95:[120,130]}},'volatility').rows[0][1]==='90 – 130');
for(var mode of ['wyckoff','trend','vwap','strength','volatility','score'])check(test.summaryFor({},mode).title.length>0);
var malicious={...stock,wyckoff:{bias:'unclear',events:[{type:'<img onerror=alert(1)>',date:'2026-10-09'}]}};
test.state.mode='wyckoff';
check(!test.modePanel(malicious).includes('<img'));
check(test.summaryFor({...stock,vwap_analysis:{}},'vwap').title==='Data belum cukup');
check(test.summaryFor({...stock,score_breakdown:{comparative_strength:15}},'score').rows.at(-1)[1].startsWith('Vs IHSG'));
console.log('Cockpit summary: '+checks+' checks passed');
