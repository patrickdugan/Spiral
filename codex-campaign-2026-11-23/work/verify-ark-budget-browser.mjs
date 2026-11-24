import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as sleep} from 'node:timers/promises';

const profile = await fs.mkdtemp(path.resolve('work/ark-budget-browser-'));
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--disable-background-networking',
  '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0',
  '--user-data-dir=' + profile, 'about:blank',
], {windowsHide: true, stdio: 'ignore'});

async function until(read, timeout = 15000) {
  const end = Date.now() + timeout;
  let last;
  while (Date.now() < end) {
    try {
      const result = await read();
      if (result) return result;
    } catch (error) { last = error; }
    await sleep(120);
  }
  throw new Error('Browser check timed out', {cause: last});
}

let socket;
try {
  const devTools = await until(() => fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8'));
  const endpoint = 'http://127.0.0.1:' + devTools.trim().split('\n')[0].trim();
  const tabs = await (await fetch(endpoint + '/json/list')).json();
  socket = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, {once: true});
    socket.addEventListener('error', reject, {once: true});
  });
  const requests = new Map();
  let id = 0;
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (!requests.has(message.id)) return;
    const {resolve, reject} = requests.get(message.id);
    requests.delete(message.id);
    if (message.error) reject(new Error(JSON.stringify(message.error)));
    else resolve(message.result);
  });
  const cdp = (method, params = {}) => new Promise((resolve, reject) => {
    requests.set(++id, {resolve, reject});
    socket.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const result = await cdp('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description);
    return result.result.value;
  };

  const address = process.argv[2];
  assert.match(address, /^http:\/\/127\.0\.0\.1:[0-9]+$/);
  const live = (await fetch(address+'/api/live').then(r=>r.json())).cloud_hyperstack_ark;
  assert.equal(live.vm_id,1178271);
  assert.equal(live.spot,true);
  assert.ok(Math.abs(live.rate_usd_per_hour-1.08672043)<1e-8);
  const raw=await fs.readFile('work/ark-a100-overnight-samples.jsonl','utf8');
  const history=raw.trim().split(/\r?\n/).map(JSON.parse).filter(row=>row.vm_id===live.vm_id).map(row=>({
    t:row.timestamp_unix,core:row.core_fresh,recursion:row.recursion_fresh,
    replayed:row.core_replayed,replayedRecursion:row.recursion_replayed,
  }));
  assert.ok(history.length>12);
  const key='rbzk.checkpoints.'+live.vm_id+'.'+live.started_at_unix;
  await cdp('Runtime.enable');
  socket.addEventListener('message',event=>{
    const eventData=JSON.parse(event.data);
    if(eventData.method==='Runtime.exceptionThrown')console.log(eventData.params.exceptionDetails?.exception?.description);
  });
  await cdp('Page.navigate',{url:address+'/'});
  await until(()=>evaluate("document.getElementById('budget-basis')?.textContent?.startsWith('Live lease price')"));
  await evaluate("localStorage.setItem("+JSON.stringify(key)+","+JSON.stringify(JSON.stringify(history))+")");
  await cdp('Page.reload', {ignoreCache:true});
  let measured;
  try {
    measured=await until(()=>evaluate("(() => { const text=document.getElementById('budget-basis')?.textContent;return text?.startsWith('Live lease price')&&text.includes('fresh cores/min over')?text:null;})()"));
  } catch (error) {
    console.log(await evaluate("({basis:document.getElementById('budget-basis')?.textContent,poll:document.getElementById('poll-label')?.textContent,storage:Object.keys(localStorage).filter(key=>key.startsWith('rbzk.checkpoints')).map(key=>[key,JSON.parse(localStorage.getItem(key)).length]),now:Date.now()/1000})"));
    throw error;
  }
  assert.match(measured,/\$1\.0867\/h/);
  await evaluate("(() => {const field=document.getElementById('budget-rate');field.value='1.5';field.dispatchEvent(new Event('input',{bubbles:true}));})()");
  const manual=await until(()=>evaluate("(() => {const text=document.getElementById('budget-basis').textContent;return text.startsWith('Entered price')?text:null;})()"));
  assert.match(manual,/Entered price · \$1\.5\/h/);
  console.log(JSON.stringify({measured,manual,samples:history.length}));
  await Promise.race([cdp('Browser.close'),sleep(1000)]);
} finally {
  socket?.close();
  if (chrome.exitCode === null) chrome.kill();
}
