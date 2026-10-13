/* Bklit Stat Card Area inspired; standalone SVG, real completed-session IHSG. */
(function(root) {
  "use strict";
  const number = v => typeof v === "number" && Number.isFinite(v) && v > 0;
  function model(payload, session) {
    if (!payload || payload.schema_version !== 1 || payload.symbol !== "^JKSE" || payload.market_data_date !== session ||
        !payload.source || payload.source.session !== session ||
        !["purbayasadewa.id","Yahoo Finance"].includes(payload.source.provider)) throw Error("Sumber/tanggal IHSG tidak sesuai");
    const rows = payload.history;
    if (!Array.isArray(rows) || rows.length < 2 || rows.length > 40) throw Error("Riwayat IHSG tidak cukup");
    let lastDate = "";
    for (const row of rows) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(row.date) || row.date <= lastDate || row.date > session || !number(row.close)) throw Error("Riwayat IHSG tidak valid");
      const date = new Date(row.date + "T00:00:00Z");
      if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0,10) !== row.date || [0,6].includes(date.getUTCDay())) throw Error("Tanggal IHSG tidak valid");
      lastDate = row.date;
    }
    if (lastDate !== session) throw Error("IHSG belum diperbarui");
    const latest = rows[rows.length-1], previous = rows[rows.length-2];
    const change = latest.close - previous.close;
    return {rows,close:latest.close,previous:previous.close,change,pct:change/previous.close*100,
            tone:change>0?"up":change<0?"down":"flat",date:session,source:payload.source.provider};
  }
  function points(rows) {
    const values = rows.map(r=>r.close), min = Math.min(...values), max = Math.max(...values);
    const span = Math.max(max-min, max*.002), low = min-span*.1, high = max+span*.1;
    return rows.map((r,i)=>({x:600*i/(rows.length-1),y:12+72*(high-r.close)/(high-low)}));
  }
  if (typeof module !== "undefined" && module.exports) module.exports = {model,points};
  if (typeof document === "undefined") return;
  const format = new Intl.NumberFormat("id-ID",{minimumFractionDigits:2,maximumFractionDigits:2});
  const dateLabel = s => new Date(s+"T12:00:00+07:00").toLocaleDateString("id-ID",{day:"numeric",month:"short",year:"numeric",timeZone:"Asia/Jakarta"});
  let version = 0;
  function display(el, value, previous) {
    const text = format.format(value), before = format.format(previous);
    el.replaceChildren();
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    [...text].forEach((char,i)=>{
      if (!/\d/.test(char)) { el.append(document.createTextNode(char)); return; }
      const digit = document.createElement("span"); digit.className="ihsg-digit";
      const track = document.createElement("span"); track.className="ihsg-digit-track";
      for(let n=0;n<20;n++) { const cell=document.createElement("span"); cell.textContent=String(n%10); track.append(cell); }
      const target=Number(char), from=/\d/.test(before[i]||"")?Number(before[i]):target;
      const end=target<from?target+10:target;
      track.style.transform="translateY("+(-end*1.15)+"em)";
      digit.append(track); el.append(digit);
      if (!reduced && track.animate) track.animate([{transform:"translateY("+(-from*1.15)+"em)"},{transform:"translateY("+(-end*1.15)+"em)"}],{duration:650,easing:"cubic-bezier(.2,.7,.2,1)"});
    });
    el.setAttribute("aria-label",text);
  }
  async function render(dashboard) {
    const token=++version, card=document.getElementById("ihsg-card");
    if(!card) return;
    const value=card.querySelector(".ihsg-value"), caption=card.querySelector(".ihsg-caption"), badge=card.querySelector(".ihsg-trend"),
          chart=card.querySelector(".ihsg-sparkline"), source=card.querySelector(".ihsg-source");
    const session=dashboard?.market_data_date;
    card.dataset.tone="flat"; value.textContent="—"; badge.textContent="—"; chart.replaceChildren();
    caption.textContent="Memuat penutupan IHSG…"; source.textContent="";
    try {
      if (!session || dashboard.screening_session_date!==session) throw Error("Sesi screening belum terverifikasi");
      const response=await fetch("ihsg_card_data.json",{cache:"no-store"});
      if(!response.ok) throw Error("Penutupan IHSG belum tersedia");
      const data=model(await response.json(),session);
      if(token!==version) return;
      card.dataset.tone=data.tone;
      const prefix=data.change>0?"+":"";
      badge.textContent=(data.change>0?"↗ ":data.change<0?"↘ ":"→ ")+prefix+data.pct.toLocaleString("id-ID",{minimumFractionDigits:2,maximumFractionDigits:2})+"%";
      badge.title="Dibanding penutupan sesi sebelumnya";
      const closeCaption="Penutupan · "+dateLabel(data.date);
      caption.textContent=closeCaption;
      display(value,data.close,data.previous);
      source.textContent=data.rows.length+" sesi";
      const coordinates=points(data.rows);
      const path=coordinates.map((p,i)=>{
        if(!i)return "M"+p.x.toFixed(2)+","+p.y.toFixed(2);
        const prev=coordinates[i-1], mid=(prev.x+p.x)/2;
        return "C"+mid.toFixed(2)+","+prev.y.toFixed(2)+" "+mid.toFixed(2)+","+p.y.toFixed(2)+" "+p.x.toFixed(2)+","+p.y.toFixed(2);
      }).join(" ");
      const area=path+" L600,100 L0,100 Z";
      chart.innerHTML='<svg viewBox="0 0 600 100" preserveAspectRatio="none" role="img" aria-label="Riwayat penutupan IHSG"><defs><linearGradient id="ihsg-card-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="currentColor" stop-opacity=".38"/><stop offset="100%" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs><path class="ihsg-area" d="'+area+'" fill="url(#ihsg-card-fill)"/><path class="ihsg-line" d="'+path+'" fill="none" stroke="currentColor" stroke-width="2.5" vector-effect="non-scaling-stroke" pathLength="1"/><g class="ihsg-hover" visibility="hidden"><line y1="0" y2="100" stroke="currentColor" stroke-opacity=".3"/><circle r="4" fill="var(--bg-card)" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/></g></svg>';
      const group=chart.querySelector(".ihsg-hover"), line=group.querySelector("line"), dot=group.querySelector("circle");
      let selected=-1,shown=data.close;
      function hover(index) {
        if(index===selected)return; selected=index;
        const p=coordinates[index]; group.setAttribute("visibility","visible");
        line.setAttribute("x1",p.x);line.setAttribute("x2",p.x);dot.setAttribute("cx",p.x);dot.setAttribute("cy",p.y);
        display(value,data.rows[index].close,shown);shown=data.rows[index].close;
        caption.textContent="Penutupan · "+dateLabel(data.rows[index].date);
      }
      chart.onpointermove=e=>{if(e.pointerType==="touch")return;const rect=chart.getBoundingClientRect();hover(Math.max(0,Math.min(data.rows.length-1,Math.round((e.clientX-rect.left)/rect.width*(data.rows.length-1)))));};
      chart.onpointerleave=()=>{selected=-1;group.setAttribute("visibility","hidden");display(value,data.close,shown);shown=data.close;caption.textContent=closeCaption;};
      chart.tabIndex=0;chart.setAttribute("aria-label","Grafik IHSG; tombol panah untuk menelusuri penutupan");
      chart.onkeydown=e=>{if(e.key==="ArrowRight"||e.key==="ArrowLeft"){e.preventDefault();hover(Math.max(0,Math.min(data.rows.length-1,(selected<0?data.rows.length-1:selected)+(e.key==="ArrowRight"?1:-1))));}else if(e.key==="Escape"){chart.onpointerleave();}};
      chart.onblur=chart.onpointerleave;
    } catch(error) {
      if(token!==version)return;
      caption.textContent=session?"Data IHSG sesi "+dateLabel(session)+" belum tersedia":"Sesi screening belum tersedia";
      source.textContent="Tidak memakai angka atau tanggal pengganti.";
    }
  }
  window.addEventListener("dashboard-ready",e=>render(e.detail));
  if(window.dashboardData)render(window.dashboardData);
})(typeof window==="undefined"?this:window);
