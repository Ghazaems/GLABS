// Phone-only navigation. No history or layout changes at tablet/desktop widths.
(function(){
  const media=matchMedia('(max-width:599px)');
  const nav=document.getElementById('phone-nav'),more=document.getElementById('phone-more');
  if(!nav||!more)return;
  const allowed=new Set(['overview','screener','watchlist','radar','rotation','riwayat','laporan']);
  let active='overview',fromHistory=false,initialized=false;
  function close(){more.hidden=true;document.getElementById('phone-more-toggle').setAttribute('aria-expanded','false')}
  function mark(){nav.querySelectorAll('[data-phone-view]').forEach(b=>b.setAttribute('aria-current',b.dataset.phoneView===active?'page':'false'))}
  function initialize(){if(media.matches&&!initialized){history.replaceState({...history.state,glabsView:active},'');initialized=true}}
  window.GlabsPhoneNav={changed(name){
    active=name;close();mark();
    if(media.matches){initialize();if(!fromHistory&&history.state?.glabsView!==name)history.pushState({...history.state,glabsView:name},'')}
  }};
  nav.querySelectorAll('[data-phone-view]').forEach(b=>b.addEventListener('click',()=>showView(b.dataset.phoneView)));
  more.querySelectorAll('[data-phone-view]').forEach(b=>b.addEventListener('click',()=>showView(b.dataset.phoneView)));
  document.getElementById('phone-more-toggle').addEventListener('click',()=>{
    more.hidden=!more.hidden;document.getElementById('phone-more-toggle').setAttribute('aria-expanded',String(!more.hidden));
  });
  more.querySelector('.support-trigger').addEventListener('click',close);
  document.addEventListener('click',e=>{if(!more.contains(e.target)&&!nav.contains(e.target))close()});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')close()});
  media.addEventListener('change',()=>{close();initialize()});
  addEventListener('popstate',e=>{
    if(!media.matches||!allowed.has(e.state?.glabsView))return;
    fromHistory=true;try{showView(e.state.glabsView)}finally{fromHistory=false}
  });
  initialize();mark();
})();
