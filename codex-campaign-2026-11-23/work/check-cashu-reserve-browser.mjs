import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import fs from 'node:fs/promises';
import {createServer} from 'node:http';
import path from 'node:path';
import {setTimeout as sleep} from 'node:timers/promises';

const app = path.resolve('../../2026-11-15/new-chat/outputs/ark-cashu-proofdesk');
const fixture = path.join(app, '.runtime/cdk-e2e-dac53217f8');
const bytes = name => fs.readFile(path.join(fixture, name));
const planBytes = await bytes('reserve-plan.json');
const plan = JSON.parse(planBytes);
const preparedBytes = await bytes('reserve-prepared.json');
const prepared = JSON.parse(preparedBytes);
const bundleBytes = await bytes('reserve-bundle.json');
const bundle = JSON.parse(bundleBytes);
const hash = data => createHash('sha256').update(data).digest('hex');
const receipt = {status:'timelock_wait', maturity_height:bundle.funding_height + bundle.timeout_blocks,
  payout_sat:bundle.value_sat - plan.payout_fee_sats, fee_sat:plan.payout_fee_sats, txid:prepared.txid};
let ready = false;
let submitted = 0;
let handlerError;
const serve = createServer(async (req, res) => {
  const reply = data => {res.setHeader('Content-Type','application/json'); res.end(JSON.stringify(data));};
  const url = new URL(req.url, 'http://localhost').pathname;
  const assets = {'/':['index.html','text/html'], '/styles.css':['styles.css','text/css'],
    '/app.js':['app.js','text/javascript'], '/reserve.js':['reserve.js','text/javascript'], '/icon.svg':['icon.svg','image/svg+xml']};
  try {
    if (assets[url]) {
      res.setHeader('Content-Type', assets[url][1]);
      res.end(await fs.readFile(path.join(app, 'web', assets[url][0])));
    } else if (url === '/api/status') reply({mode:'regtest',cashu_reserve_available:true,cashu_reserve_broadcast:true,intents:[]});
    else if (url === '/api/cases') reply({cases:[]});
    else if (url === '/api/vtxos') reply({vtxos:[],plans:[]});
    else if (url === '/api/sources') reply({integrations:[],sources:[]});
    else if (url.startsWith('/api/cashu/reserve/')) {
      assert.equal(req.headers['x-proof-grove'], '1');
      const data = JSON.parse((await Array.fromAsync(req)).map(chunk => chunk.toString()).join(''));
      const action = url.split('/').at(-1);
      if (action === 'plan') {
        assert.deepEqual(data, Object.fromEntries(Object.keys(data).map(key => [key, plan[key]])));
        reply({plan,id:hash(planBytes)});
      } else if (action === 'prepare') {
        assert.equal(data.id,hash(planBytes)); assert.deepEqual(data.plan,plan);
        assert.equal(data.melt_status.outpoint,prepared.melt_binding.outpoint);
        reply({prepared,id:hash(preparedBytes)});
      } else if (action === 'seal') {
        assert.equal(data.id,hash(preparedBytes)); assert.equal(data.signed_tx,bundle.fallback_tx);
        reply({bundle,id:hash(bundleBytes),receipt});
      } else if (action === 'redeem') {
        assert.equal(data.id,hash(bundleBytes)); assert.equal(data.max_fee_sats,receipt.fee_sat);
        assert.deepEqual(data.bundle,bundle);
        if (data.broadcast) submitted++;
        reply({...receipt,status:data.broadcast ? 'submitted' : ready ? 'ready' : 'timelock_wait'});
      }
    } else {res.statusCode=404; reply({error:'not found'});}
  } catch (error) {handlerError=error; res.statusCode=500; reply({error:error.message});}
});
await new Promise(resolve => serve.listen(0, '127.0.0.1', resolve));

const profile = await fs.mkdtemp(path.resolve('work/reserve-browser-'));
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new','--disable-gpu','--disable-background-networking','--remote-debugging-port=0',
  '--no-first-run','--user-data-dir=' + profile,'about:blank',
], {windowsHide:true,stdio:'ignore'});

async function until(test) {
  const end = Date.now() + 10000;
  let last;
  while (Date.now() < end) {
    try {const value = await test(); if (value) return value;} catch (error) {last = error;}
    if (handlerError) throw handlerError;
    await sleep(100);
  }
  throw new Error('Browser check timed out', {cause:last});
}

let socket;
try {
  const portFile = await until(() => fs.readFile(path.join(profile,'DevToolsActivePort'), 'utf8'));
  const devtools = `http://127.0.0.1:${portFile.trim().split('\n')[0].trim()}`;
  const tabs = await (await fetch(devtools + '/json/list')).json();
  socket = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve,reject) => {socket.onopen=resolve; socket.onerror=reject;});
  let nextId = 0;
  const calls = new Map();
  socket.onmessage = event => {
    const {id,result,error} = JSON.parse(event.data);
    if (!calls.has(id)) return;
    const {resolve,reject} = calls.get(id);
    calls.delete(id);
    if (error) reject(Error(JSON.stringify(error))); else resolve(result);
  };
  const cdp = (method, params={}) => new Promise((resolve,reject) => {
    calls.set(++nextId,{resolve,reject}); socket.send(JSON.stringify({id:nextId,method,params}));
  });
  const evaluate = async expression => {
    const result = await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description);
    return result.result.value;
  };
  const assign = (query, name, content) => evaluate(`(() => {
    const file=new File([${JSON.stringify(content)}],${JSON.stringify(name)});
    const transfer=new DataTransfer();transfer.items.add(file);
    document.querySelector(${JSON.stringify(query)}).files=transfer.files;
    return true;
  })()`);
  const confirmed = [];
  for (const width of [1440,390]) {
    ready=false;
    const downloads = path.join(profile,'downloads-'+width);
    await fs.mkdir(downloads);
    await cdp('Page.setDownloadBehavior',{behavior:'allow',downloadPath:downloads});
    await cdp('Emulation.setDeviceMetricsOverride',{width,height:width===1440?1260:844,deviceScaleFactor:1,mobile:false});
    await cdp('Page.navigate',{url:`http://127.0.0.1:${serve.address().port}/?width=${width}#reserve`});
    await until(() => evaluate("document.querySelector('#reserve')?.hidden === false"));
    await evaluate(`(() => {
      const form=document.getElementById('reserve-plan');
      for(const [key,value] of Object.entries(${JSON.stringify(plan)})) if(form.elements[key]) form.elements[key].value=value;
      form.requestSubmit();return true;
    })()`);
    await until(() => evaluate("!document.getElementById('reserve-save-plan').hidden"));
    await assign('#reserve-prepare input[name=melt_status]','melt-status.json',await bytes('reserve-melt-status.json').then(buffer=>buffer.toString()));
    await evaluate("document.getElementById('reserve-prepare').requestSubmit();true");
    await until(() => evaluate("!document.getElementById('reserve-save-psbt').hidden"));
    await evaluate("document.getElementById('reserve-save-psbt').click();true");
    const psbt = await until(() => fs.readFile(path.join(downloads,'cashu-reserve-fallback.psbt')));
    assert.deepEqual(psbt, Buffer.from(prepared.psbt,'base64'));
    await assign('#reserve-seal input[name=signed_tx]','signed.hex',bundle.fallback_tx);
    await evaluate("document.getElementById('reserve-seal').requestSubmit();true");
    await until(() => evaluate("document.getElementById('reserve-sealed-status').textContent.includes('23,750 sats')"));
    await evaluate("document.getElementById('reserve-redeem').requestSubmit();true");
    await until(() => evaluate("document.getElementById('reserve-redeem-status').textContent.includes('Waiting for block')"));
    assert.equal(await evaluate("document.getElementById('reserve-broadcast').hidden"),true);
    ready=true;
    await evaluate("document.getElementById('reserve-redeem').requestSubmit();true");
    await until(() => evaluate("!document.getElementById('reserve-broadcast').hidden"));
    assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'),true);
    if (width === 1440) {
      const shot = await cdp('Page.captureScreenshot',{format:'png'});
      await fs.writeFile(path.resolve('outputs/Cashu-Holder-Reserve-Dashboard.png'),Buffer.from(shot.data,'base64'));
    }
    await evaluate("document.getElementById('reserve-broadcast').click();true");
    await until(() => evaluate("document.getElementById('reserve-redeem-status').textContent.includes('Payout submitted')"));
    confirmed.push(width);
  }
  assert.equal(submitted,2);
  console.log(JSON.stringify({widths:confirmed,binary_psbt_verified:true,ready_required_before_broadcast:true}));
  await Promise.race([cdp('Browser.close'),sleep(1000)]);
} finally {
  socket?.close();
  serve.close();
  if (chrome.exitCode === null) chrome.kill();
}
