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
    const rows=history.slice(-100),width=760,height=136,left=8,right=95,top=12,bottom=24;
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
    if(!item)return '<div class="panel activity-panel"><h3>ARUS & AKTIVITAS</h3><h4>Data Purbaya belum tersedia</h4><p class="empty-event">'+(loading?'Sedang memuat hasil indikator.':error?'Hasil indikator belum dapat dimuat.':'Belum ada hasil yang cocok dengan screening terakhir untuk saham ini.')+'</p><p class="empty-event">Tidak memakai pengganti Yahoo atau data buatan.</p></div>';
    const last=item.latest,p=last.pressure,intensity=last.intensity;
    const direction=!Number.isFinite(p)?'Tekanan belum dapat dihitung':p>0?'Tekanan harga–volume condong beli':p<0?'Tekanan harga–volume condong jual':'Tekanan harga–volume seimbang';
    const card=(title,value,note,chart)=>'<section class="activity-block"><div class="activity-heading"><h4>'+title+'</h4><b>'+escape(value)+'</b></div><p>'+escape(note)+'</p>'+chart+'</section>';
    return '<div class="panel activity-panel"><h3>INTINYA · '+escape(session)+'</h3><h4>'+escape(direction)+'</h4><p class="empty-event">'+(Number.isFinite(intensity)?'Volume '+fmt(intensity)+'× rata-rata 20 sesi sebelumnya.':'Pembanding aktivitas volume belum cukup.')+' Ini estimasi dari candle, bukan identitas atau transaksi bandar.</p>'+
      card('Tekanan Likuiditas GLABS',fmt(p),'CMF 20 sesi · skala −100 sampai +100. Bukan LPM Bandarmetrics.',series(item.history,'pressure','#2dd4bf'))+
      card('Money Flow · bar',compact(last.money_flow_bar)+' lembar','Tekanan per sesi (Money Flow Volume), bukan uang masuk/keluar dalam rupiah.',series(item.history,'money_flow_bar','#4ade80',true))+
      card('Money Flow · line',compact(last.money_flow_line)+' lembar','Akumulasi ADL sejak '+item.history_start+'. Nilai bergantung awal histori; bukan kepemilikan bandar.',series(item.history,'money_flow_line','#fb923c'))+
      card('Intensity GLABS',fmt(intensity)+'×','Volume dibanding rata-rata 20 sesi sebelumnya. 1× = aktivitas rata-rata; tidak menentukan arah beli/jual.',series(item.history,'intensity','#a78bfa',true))+
      '<p class="activity-source">Sumber harga dan volume: <a href="'+escape(item.source.url)+'" target="_blank" rel="noopener noreferrer">Purbaya</a> · Harian · '+item.bars+' sesi. Tidak masuk skor komposit.</p></div>';
  }
  window.GlabsActivity={load,record,panel};
})();