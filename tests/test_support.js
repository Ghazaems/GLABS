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
  assert.ok(js.includes('if(busy || !form.reportValidity())return;'));assert.ok(js.includes('status.textContent=text'));assert.ok(!js.includes('localStorage'));assert.ok(!js.includes('innerHTML'));
  console.log('Support payload, rejection, HTML wiring and safety checks passed.');
}
module.exports=run();
