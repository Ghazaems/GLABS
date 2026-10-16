const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../web'),fresh=require('../web/freshness'),chat=require('../web/chat-core');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8'),nav=fs.readFileSync(path.join(root,'phone-nav.js'),'utf8');
for(const day of ['2026-02-30','2026-13-01','2026-1-01','',null,undefined])assert.equal(fresh.validDate(day),false);
assert.equal(fresh.validDate('2024-02-29'),true);assert.equal(fresh.validDate('2026-02-29'),false);
const data={screening_session_date:'2026-10-16',market_data_date:'2026-10-15'};
assert.equal(fresh.isCurrent({last_price_date:'2026-10-16'},data),true);
for(const day of [undefined,'2026-10-15','2026-10-17','invalid'])assert.equal(fresh.isCurrent({last_price_date:day},data),false);
assert.equal(fresh.isCurrent({last_price_date:'2026-10-16'},{market_data_date:'2026-10-16'}),false);
assert.ok(html.includes('const tp = sortedWl.find(isCurrentRow)'));
assert.ok(html.includes('accum.filter(isCurrentRow)'));
assert.ok((html.match(/freshnessLabel\(r\)/g)||[]).length>=4);
const rows=Array.from({length:879},(_,i)=>({ticker:'X'+i,score_daily:i,score:879-i}));
const before=JSON.stringify(rows);rows.push({ticker:'ANTM',score_daily:-30});
assert.equal(chat.select(rows,'ANTM').rows[0].ticker,'ANTM');
assert.equal(chat.select(rows,'halo ANTM').rows[0].ticker,'ANTM');
assert.equal(chat.select(rows,'halo').rows.length,0);
assert.equal(chat.select(rows,'Ringkas pasar','daily').rows[0].ticker,'X878');
assert.equal(chat.select(rows,'Ringkas pasar','weekly').rows[0].ticker,'X0');
assert.equal(chat.select(rows,'Ringkas pasar').rows.length,40);
assert.equal(JSON.stringify(rows.slice(0,879)),before);
assert.throws(()=>chat.serialize({file:'é'.repeat(2_000_000)}),/4 MB/);
assert.ok(chat.serialize({file:'a'.repeat(1000)}).length<2000);
// Actual chat UI failure/success: preserve draft + attachment and send bounded context.
const chatStart=html.indexOf('let aiRequestPending ='),chatEnd=html.indexOf('\ndocument.addEventListener("DOMContentLoaded"',chatStart);
async function checkChat(){
 const elements=[],input={value:'Analisis ANTM'},log={appendChild(e){elements.push(e)}};
 function el(){return {children:[],appendChild(c){this.children.push(c)},scrollIntoView(){},addEventListener(t,fn){this[t]=fn}}}
 const file={name:'test.pdf',mimeType:'application/pdf',base64:'YQ=='},payloads=[];
 let fail=true,cleared=0;
 const ctx={window:{dashboardData:{watchlist:rows,screening_session_date:'2026-10-16'},GlabsChatCore:chat},currentStyle:'daily',
 pendingFile:file,filePreparing:false,AbortController,setTimeout,clearTimeout,TypeError,
 document:{getElementById:id=>id==='chat-input'?input:log,createElement:el},
 chatMarketSummary:()=>({processed:rows.length}),buildWatchlistContext:q=>chat.select(rows,q).rows,escapeHtml:s=>s,renderMarkdown:s=>s,
 clearPendingFile(){ctx.pendingFile=null;cleared++},
 fetch:async(url,opts)=>{payloads.push(JSON.parse(opts.body));return {ok:!fail,status:fail?503:200,json:async()=>fail?{error:'Provider sibuk'}:{answer:'Skor -30'}}},
 };
 vm.createContext(ctx);vm.runInContext(html.slice(chatStart,chatEnd),ctx);
 await ctx.askAI(input.value);assert.equal(input.value,'Analisis ANTM');assert.equal(ctx.pendingFile,file);assert.equal(cleared,0);
 assert.ok(elements.at(-1).children.some(b=>b.textContent==='Coba lagi'));
 assert.equal(payloads[0].watchlist.length,1);assert.equal(payloads[0].scope.total_rows,880);
 fail=false;await ctx.askAI(input.value);assert.equal(input.value,'');assert.equal(ctx.pendingFile,null);assert.equal(cleared,1);
 // Edits typed during an in-flight request must survive success.
 ctx.fetch=async()=>{input.value='pertanyaan baru';ctx.pendingFile={name:'baru.txt'};return {ok:true,json:async()=>({answer:'ok'})}};
 input.value='lama';await ctx.askAI('lama');assert.equal(input.value,'pertanyaan baru');assert.equal(ctx.pendingFile.name,'baru.txt');
}
// Actual navigation code with phone/tablet mocked media; verify history and routing.
function checkNav(phone){
 const nodes={};function node(dataset={}){return {dataset,hidden:true,attrs:{},setAttribute(k,v){this.attrs[k]=v},addEventListener(k,f){this[k]=f},contains(){return false}}}
 const buttons=['overview','screener','watchlist'].map(v=>node({phoneView:v})),extra=['radar','rotation','riwayat','laporan'].map(v=>node({phoneView:v})),support=node(),toggle=node();
 nodes['phone-nav']={querySelectorAll:()=>buttons,contains:()=>false};
 nodes['phone-more']={...node(),querySelectorAll:()=>extra,querySelector:()=>support};nodes['phone-more-toggle']=toggle;
 const events={},changes=[],history={state:{},replaceState(s){this.state=s},pushState(s){this.state=s;changes.push(s.glabsView)}},win={};
 const ctx={window:win,matchMedia:()=>({matches:phone,addEventListener(){}}),history,document:{getElementById:id=>nodes[id],addEventListener(){}},
 addEventListener:(name,fn)=>events[name]=fn,showView:name=>win.GlabsPhoneNav.changed(name)};
 vm.runInNewContext(nav,ctx);buttons[1].click();assert.equal(changes.length,phone?1:0);
 if(phone){events.popstate({state:{glabsView:'overview'}});assert.equal(changes.length,1);assert.equal(buttons[0].attrs['aria-current'],'page')}
 toggle.click();assert.equal(nodes['phone-more'].hidden,false);extra[0].click();assert.equal(nodes['phone-more'].hidden,true);
}
const css=fs.readFileSync(path.join(root,'phone-nav.css'),'utf8');
assert.ok(css.includes('@media(max-width:599px)'));assert.ok(!css.includes('max-width:900'));
assert.ok(html.includes('Math.min(screen.width,screen.height)<600'));
assert.ok(html.indexOf('phone-nav.js')<html.indexOf('support.js'));
(async()=>{await checkChat();checkNav(true);checkNav(false);console.log('Freshness, bounded UTF-8 payload, selection, draft/retry and phone-only navigation tests passed.');})().catch(e=>{console.error(e);process.exitCode=1});
