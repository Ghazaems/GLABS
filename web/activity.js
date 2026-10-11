(() => {
  let dataset=null,loading=false,error=false;
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=n=>Number.isFinite(n)?n.toLocaleString('id-ID',{maximumFractionDigits:2}):'—';
  const compact=n=>Math.abs(n)>=1e9?fmt(n/1e9)+' miliar':Math.abs(n)>=1e6?fmt(n/1e6)+' jt':Math.abs(n)>=1e3?fmt(n/1e3)+' rb':fmt(n);
  function record(ticker,session){
    const item=dataset?.stocks?.[ticker];
    return dataset?.provider==='purbayasadewa.id'&&dataset.method_version===1&&dataset.market_data_date===session&&item?.status==='ok'&&item.source?.provider==='purbayasadewa.id'&&item.source.session===session&&item.latest?.date===session&&Array.isArray(item.history)&&item.history.length?item:null;
  }
  async function load(session){
    if(loading)return;
    if(dataset?.market_data_date===session)return;
    loading=true;error=false;
    try{
      const response=await fetch('purbaya_activity_data.json',{cache:'no-store'});
      if(!response.ok)throw Error('unavailable');
      const data=await response.json();
      if(data.provider!=='purbayasadewa.id'||data.method_version!==1)throw Error('invalid_source');
      dataset=data;
    }catch(_){error=true;}finally{loading=false;window.dispatchEvent(new Event('activity-ready'));}
  }
  function series(history,key,color,bars=false){
    const rows=history.slice(-100),width=820,height=106,left=12,right=68,top=12,bottom=22;
    const values=rows.map(r=>r[key]).filter(Number.isFinite);
    if(!values.length)return '<p class="empty-event">Data indikator belum cukup.</p>';
    let min=Math.min(0,...values),max=Math.max(0,...values);
    if(key==='pressure'){min=-100;max=100;}
    if(key==='intensity')max=Math.max(max,1);
    if(max===min)max=min+1;
    const x=i=>left+(i+.5)*(width-left-right)/rows.length;
    const y=v=>top+(max-v)/(max-min)*(height-top-bottom);
    let svg='<svg class="activity-svg" viewBox="0 0 '+width+' '+height+'" role="img" aria-label="'+escape(key)+'">';
    svg+='<line x1="'+left+'" y1="'+y(0)+'" x2="'+(width-right)+'" y2="'+y(0)+'" stroke="#444" stroke-dasharray="3 4"/>';
    if(key==='intensity')svg+='<line x1="'+left+'" y1="'+y(1)+'" x2="'+(width-right)+'" y2="'+y(1)+'" stroke="#777" stroke-dasharray="3 4"/>';
    if(bars){
      const w=Math.max(1,(width-left-right)/rows.length*.65);
      rows.forEach((row,i)=>{const v=row[key];if(!Number.isFinite(v))return;svg+='<rect x="'+(x(i)-w/2)+'" y="'+Math.min(y(0),y(v))+'" width="'+w+'" height="'+Math.abs(y(v)-y(0))+'" fill="'+(key==='intensity'?color:v>=0?'#4ade80':'#f87171')+'" opacity=".75"/>';});
    }else{
      let path='',segment=false;
      rows.forEach((row,i)=>{if(!Number.isFinite(row[key])){segment=false;return;}path+=(segment?' L':' M')+x(i)+','+y(row[key]);segment=true;});
      svg+='<path d="'+path+'" fill="none" stroke="'+color+'" stroke-width="1.8"/>';
    }
    svg+='<text x="'+(width-right+8)+'" y="'+(top+8)+'" fill="#888" font-size="10">'+escape(compact(max))+'</text><text x="'+(width-right+8)+'" y="'+(height-bottom)+'" fill="#888" font-size="10">'+escape(compact(min))+'</text>';
    svg+='<text x="'+left+'" y="'+(height-5)+'" fill="#777" font-size="10">'+escape(rows[0].date)+'</text><text x="'+(width-right)+'" y="'+(height-5)+'" text-anchor="end" fill="#777" font-size="10">'+escape(rows.at(-1).date)+'</text></svg>';
    return svg;
  }
  function panel(stock,session){
    const item=record(stock.ticker,session);
    if(!item)return '<div class="activity-unavailable"><h4>Data Purbaya belum tersedia</h4><p class="empty-event">'+(loading?'Sedang memuat hasil indikator.':error?'Hasil indikator belum dapat dimuat.':'Belum ada hasil yang cocok dengan screening terakhir untuk saham ini.')+'</p><p class="empty-event">Tidak memakai pengganti Yahoo atau data buatan.</p></div>';
    const last=item.latest;
    const card=(title,value,note,chart)=>'<section class="activity-block"><div class="activity-heading"><h4>'+title+'</h4><b>'+escape(value)+'</b><span class="activity-hint" title="'+escape(note)+'">ⓘ</span></div>'+chart+'</section>';
    return '<div class="activity-stack" aria-label="Indikator tambahan harga dan volume">'+
      card('Tekanan Likuiditas GLABS',fmt(last.pressure),'CMF 20 sesi, skala −100 hingga +100. Bukan LPM Bandarmetrics.',series(item.history,'pressure','#2dd4bf'))+
      card('Money Flow · line',compact(last.money_flow_line)+' lembar','ADL sejak '+item.history_start+'. Bukan kepemilikan bandar.',series(item.history,'money_flow_line','#fb923c'))+
      card('Intensity GLABS',fmt(last.intensity)+'×','Volume / rata-rata 20 sesi sebelumnya. 1× = aktivitas rata-rata.',series(item.history,'intensity','#a78bfa',true))+
      card('Money Flow · bar',compact(last.money_flow_bar)+' lembar','Money Flow Volume per sesi; bukan arus uang dalam rupiah.',series(item.history,'money_flow_bar','#4ade80',true))+
      '<details class="activity-method"><summary>Sumber & cara baca · indikator tambahan</summary><p>Harian · '+escape(session)+' · '+item.bars+' sesi · <a href="'+escape(item.source.url)+'" target="_blank" rel="noopener noreferrer">Purbaya</a>. Tidak masuk skor komposit.</p><p>Tekanan Likuiditas = CMF20 × 100; bukan LPM Bandarmetrics. Money Flow bar = tekanan per sesi dalam lembar; line = ADL kumulatif sejak '+escape(item.history_start)+'. Bukan transaksi atau kepemilikan bandar, bukan arus uang rupiah. Intensity = volume dibanding rata-rata 20 sesi sebelumnya, bukan arah beli/jual.</p></details></div>';
  }

  window.GlabsActivity={load,record,panel};
})();