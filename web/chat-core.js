// Pure, bounded chat selection shared with offline regression tests.
(function(root){
  const MAX_BODY_BYTES=4_000_000,MAX_ROWS=40;
  function select(rows,question,style='daily'){
    const words=new Set(String(question).toUpperCase().match(/[A-Z0-9]+/g)||[]);
    const matched=rows.filter(r=>words.has(String(r.ticker).toUpperCase().replace(/\.JK$/,'')));
    const greeting=/^(halo|hai|hi|hello|tes|test)\s*[!.?]*$/i.test(String(question).trim());
    const key=style==='swing'?'score_swing':style==='weekly'?'score':'score_daily';
    const candidates=greeting?[]:matched.length?matched:[...rows].sort((a,b)=>
      Number(b[key]??-Infinity)-Number(a[key]??-Infinity)||String(a.ticker).localeCompare(String(b.ticker)));
    return {rows:candidates.slice(0,MAX_ROWS),scope:{total_rows:rows.length,selected_rows:Math.min(candidates.length,MAX_ROWS),
      selection:greeting?'tanpa data saham':matched.length?'ticker yang disebut':'sampel skor tertinggi horizon terpilih, bukan seluruh pasar',
      truncated:candidates.length>MAX_ROWS}};
  }
  function serialize(payload){
    const body=JSON.stringify(payload);
    if(new TextEncoder().encode(body).byteLength>MAX_BODY_BYTES)
      throw new Error('Lampiran dan konteks melebihi batas aman 4 MB. Gunakan file lebih kecil; PDF tidak dipotong otomatis.');
    return body;
  }
  const api={select,serialize,MAX_BODY_BYTES};
  root.GlabsChatCore=api;
  if(typeof module==='object')module.exports=api;
})(typeof window==='object'?window:globalThis);
