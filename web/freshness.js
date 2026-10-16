// A price is current only for a valid, explicitly matching screening session.
(function(root){
  function validDate(value){
    if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
    const date=new Date(value+'T00:00:00Z');
    return Number.isFinite(date.getTime())&&date.toISOString().slice(0,10)===value;
  }
  function isCurrent(row,data){
    return validDate(row?.last_price_date)&&validDate(data?.screening_session_date)
      &&row.last_price_date===data.screening_session_date;
  }
  const api={validDate,isCurrent};
  root.GlabsFreshness=api;
  if(typeof module==='object')module.exports=api;
})(typeof window==='object'?window:globalThis);
