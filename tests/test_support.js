'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {preparePayload,sendMessage}=require('../web/support.js');
const valid={name:' Ghaza ',email:'ghazaerland@gmail.com',message:'Tes integrasi GLABS support.','h-captcha-response':'test-only-token'};
async function run(){
  const payload=preparePayload({...valid,to:'attacker@example.com',access_key:'bad',subject:'bad'});
  assert.equal(payload.name,'Ghaza');assert.equal(payload.replyto,valid.email);assert.equal(payload.to,undefined);assert.equal(payload.access_key,'2d1273ee-d35c-4059-90da-95d2539b5b70');assert.equal(payload.subject,'Pesan GLABS Support');
  for(const invalid of [{name:''},{name:'x'.repeat(81)},{email:'bad'},{message:'short'},{message:'x'.repeat(4001)},{'h-captcha-response':''},{botcheck:'on'}]){
    assert.throws(()=>preparePayload({...valid,...invalid}));
  }
  let calls=0;
  const accepted=async(url,options)=>{
    calls++;assert.equal(url,'https://api.web3forms.com/submit');assert.equal(options.credentials,'omit');assert.equal(options.method,'POST');assert.equal(options.redirect,'error');
    const body=JSON.parse(options.body);assert.equal(body.message,valid.message);
    return {ok:true,status:200,json:async()=>({success:true})};
  };
  assert.equal(await sendMessage(valid,accepted),true);assert.equal(calls,1);
  for(const res of [{ok:false,status:429,json:async()=>({success:false})},{ok:true,status:200,json:async()=>({success:false})},{ok:true,status:200,json:async()=>({success:'true'})},{ok:false,status:500,json:async()=>({success:true})},{ok:true,status:200,json:async()=>{throw Error('bad JSON');}}]){
    await assert.rejects(()=>sendMessage(valid,async()=>res));
  }
  calls=0;await assert.rejects(()=>sendMessage({...valid,email:'bad'},async()=>{calls++;}));assert.equal(calls,0);
  await assert.rejects(()=>sendMessage(valid,async()=>{throw new TypeError('network');}));
  const html=fs.readFileSync('web/index.html','utf8'),js=fs.readFileSync('web/support.js','utf8');
  for(const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))if(match[1].trim())new Function(match[1]);
  assert.ok(html.includes('id="support-dialog"'));assert.ok(html.includes('src="support.js"'));assert.ok(html.includes('href="support.css"'));assert.ok(html.includes('aria-live="polite"'));assert.ok(html.includes('name="botcheck"'));assert.ok(html.includes('data-captcha="true"'));
  assert.ok(!html.includes('name="attachment"'));
  assert.equal((html.match(/class="icon-btn support-trigger"/g)||[]).length,1);
  assert.ok(!html.includes('support-trigger support-shortcut'));
  assert.ok(!html.includes('<span class="tip">Pengaturan</span>'));
  assert.ok(js.includes('if(busy || !form.reportValidity())return;'));assert.ok(js.includes('status.textContent=text'));assert.ok(!js.includes('localStorage'));assert.ok(!js.includes('innerHTML'));
  assert.ok(!js.includes('dialog.showModal('));assert.ok(js.includes('dialog.show()'));
  assert.ok(html.includes('id="support-backdrop"'));assert.ok(html.includes('aria-modal="true"'));
  assert.ok(js.includes('shell.inert=true'));assert.ok(js.includes('shell.inert=previousInert'));
  const css=fs.readFileSync('web/support.css','utf8');
  assert.ok(css.includes('position:fixed'));assert.ok(css.includes('.support-backdrop[hidden]{display:none}'));

  // Simulate the browser submit flow without CAPTCHA or external messages.
  const vm=require('node:vm');
  async function browserSubmit(response){
    const events={},dialogEvents={};
    let closed=0,resets=0;
    const dialog={open:true,addEventListener:(name,fn)=>{dialogEvents[name]=fn;},close(){closed++;this.open=false;dialogEvents.close?.();}};
    const form={addEventListener:(name,fn)=>{events[name]=fn;},reportValidity:()=>true,setAttribute(){},removeAttribute(){},reset(){resets++;}};
    const nodes={'support-dialog':dialog,'support-form':form,'support-status':{textContent:'',dataset:{}},'support-send':{disabled:false},'support-message':{value:valid.message,addEventListener(){}},'support-count':{textContent:''},'support-backdrop':{hidden:false},'support-close':{addEventListener(){},focus(){}}};
    const sandbox={document:{getElementById:id=>nodes[id],querySelector:()=>({inert:false}),querySelectorAll:()=>[],body:{style:{overflow:''}}},window:{fetch:async()=>response},FormData:class{[Symbol.iterator](){return Object.entries(valid)[Symbol.iterator]();}},AbortController,setTimeout,clearTimeout};
    vm.runInNewContext(js,sandbox);
    await events.submit({preventDefault(){}});
    return {closed,resets,nodes};
  }
  let browser=await browserSubmit({ok:true,status:200,json:async()=>({success:true})});
  assert.equal(browser.closed,1);assert.equal(browser.resets,1);assert.equal(browser.nodes['support-dialog'].open,false);assert.equal(browser.nodes['support-send'].disabled,false);
  for(const response of [{ok:false,status:500,json:async()=>({success:false})},{ok:true,status:200,json:async()=>({success:false})}]){
    browser=await browserSubmit(response);
    assert.equal(browser.closed,0);assert.equal(browser.resets,0);assert.equal(browser.nodes['support-dialog'].open,true);assert.equal(browser.nodes['support-message'].value,valid.message);
  }
  console.log('Support payload, rejection, HTML wiring and CAPTCHA layer checks passed.');
}
module.exports=run();
