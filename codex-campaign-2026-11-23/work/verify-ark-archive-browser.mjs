import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as sleep} from 'node:timers/promises';

const profile = await fs.mkdtemp(path.resolve('work/nova-concurrent-browser-'));
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
  assert.match(address, /^http:\/\/127\.0\.0\.1:\d+$/);
  const current = (await fetch(address+'/api/live').then(r=>r.json())).cloud_hyperstack_ark;
  assert.equal(current.vm_id,1178271);
  assert.equal(current.ark_running,true);
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:970,deviceScaleFactor:1,mobile:false});
  await cdp('Page.navigate',{url:address+'/'});
  await until(()=>evaluate("document.querySelector('#ongoing-jobs')?.textContent?.includes('Ark SP1 prover')"));
  const values = await until(async()=>{
    const result=await evaluate(`(() => {
      const storage=document.getElementById('overview-storage');
      if(!storage || storage.hidden)return null;
      return {storage:storage.textContent,proofHidden:document.getElementById('overview-proof-release').hidden,
        checkpointHidden:document.getElementById('overview-checkpoint-release').hidden,
        gates:document.getElementById('overview-gates').textContent,
        overflow:document.documentElement.scrollWidth>innerWidth};
    })()`);
    return result?.storage.includes('17.58 GB')?result:null;
  });
  assert.match(values.storage,/3,856 objects/);
  assert.equal(values.proofHidden,true);
  assert.equal(values.checkpointHidden,true);
  assert.equal(values.overflow,false);
  assert.match(values.gates,/Proof gates/);
  const shot=await cdp('Page.captureScreenshot',{format:'png'});
  await fs.writeFile('outputs/Ark-Desktop-Checkpoint-Storage.png',Buffer.from(shot.data,'base64'));
  console.log(JSON.stringify(values));
  await Promise.race([cdp('Browser.close'),sleep(1000)]);
} finally {
  socket?.close();
  if (chrome.exitCode === null) chrome.kill();
}

