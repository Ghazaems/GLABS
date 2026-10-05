(function () {
  'use strict';
  const ENDPOINT = 'https://api.web3forms.com/submit';
  function preparePayload(data) {
    const name = String(data.name || '').trim(), email = String(data.email || '').trim(), message = String(data.message || '').trim();
    const token = String(data['h-captcha-response'] || '').trim();
    if (data.botcheck) throw new Error('Pengiriman diblokir proteksi spam.');
    if (!name || name.length > 80) throw new Error('Isi nama, maksimal 80 karakter.');
    if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('Masukkan email yang valid.');
    if (message.length < 10 || message.length > 4000) throw new Error('Pesan harus berisi 10–4000 karakter.');
    if (!token) throw new Error('Selesaikan verifikasi CAPTCHA terlebih dahulu.');
    return {access_key:'2d1273ee-d35c-4059-90da-95d2539b5b70',subject:'Pesan GLABS Support',from_name:'GLABS Support',name,email,replyto:email,message,'h-captcha-response':token};
  }
  async function sendMessage(data, fetcher, signal) {
    const payload = preparePayload(data);
    const response = await fetcher(ENDPOINT,{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},body:JSON.stringify(payload),signal,credentials:'omit',redirect:'error'});
    let result;
    try { result = await response.json(); } catch (_) { throw new Error('Respons layanan tidak valid. Pengiriman belum dapat dikonfirmasi.'); }
    if (!response.ok || result.success !== true) throw new Error(response.status === 429 ? 'Batas layanan tercapai. Coba lagi nanti.' : 'Layanan menolak pengiriman. Periksa CAPTCHA atau coba lagi nanti.');
    return true;
  }
  if (typeof module === 'object' && module.exports) { module.exports={preparePayload,sendMessage}; return; }
  const dialog=document.getElementById('support-dialog'), form=document.getElementById('support-form');
  if (!dialog || !form) return;
  const status=document.getElementById('support-status'), send=document.getElementById('support-send'), message=document.getElementById('support-message'), count=document.getElementById('support-count');
  let busy=false, captchaLoading=false;
  function report(text,state) { status.textContent=text; status.dataset.state=state || ''; }
  function resetCaptcha() { try { window.hcaptcha?.reset(); } catch (_) {} }
  function loadCaptcha() {
    if(captchaLoading) return;
    captchaLoading=true;
    const script=document.createElement('script');
    script.src='https://web3forms.com/client/script.js'; script.async=true;
    script.onerror=()=>{captchaLoading=false;script.remove();report('CAPTCHA gagal dimuat. Periksa koneksi lalu tutup dan buka Support lagi.','error');};
    document.head.appendChild(script);
  }
  // showModal() puts the dialog in the browser top layer, above hCaptcha's
  // body-mounted challenge. Use a normal fixed dialog instead; only the
  // GLABS shell is inert, leaving the provider's challenge interactive.
  const backdrop=document.getElementById('support-backdrop');
  const shell=document.querySelector('.shell');
  let returnFocus=null, previousOverflow='', previousInert=false;
  function openSupport(button) {
    if(dialog.open) return;
    returnFocus=button;
    previousOverflow=document.body.style.overflow;
    previousInert=shell ? shell.inert : false;
    if(shell) shell.inert=true;
    backdrop.hidden=false;
    document.body.style.overflow='hidden';
    dialog.show();
    document.getElementById('support-close').focus();
    loadCaptcha();
  }
  function restoreSupport() {
    backdrop.hidden=true;
    if(shell) shell.inert=previousInert;
    document.body.style.overflow=previousOverflow;
    if(returnFocus?.isConnected) returnFocus.focus();
  }
  document.querySelectorAll('.support-trigger').forEach(button=>button.addEventListener('click',()=>openSupport(button)));
  document.getElementById('support-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',restoreSupport);
  dialog.addEventListener('keydown',event=>{
    if(event.key==='Escape') { event.preventDefault(); dialog.close(); }
  });
  message.addEventListener('input',()=>{count.textContent=message.value.length+'/4000';});
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    if(busy || !form.reportValidity())return;
    const data=Object.fromEntries(new FormData(form));
    try{preparePayload(data);}catch(error){report(error.message,'error');return;}
    busy=true;send.disabled=true;form.setAttribute('aria-busy','true');report('Mengirim pesan…');
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),20000);
    try{
      await sendMessage(data,window.fetch.bind(window),controller.signal);
      form.reset();count.textContent='0/4000';
      report('Pesan diterima layanan untuk diteruskan ke pengelola. Balasan melalui email; ini belum memastikan pesan masuk Inbox.','success');
    }catch(error){
      report(error.name==='AbortError' || error instanceof TypeError ? 'Koneksi terputus atau waktu habis. Status pengiriman belum pasti; periksa sebelum mengirim ulang agar tidak duplikat.' : error.message,'error');
    }finally{
      clearTimeout(timer);resetCaptcha();busy=false;send.disabled=false;form.removeAttribute('aria-busy');
    }
  });
})();
