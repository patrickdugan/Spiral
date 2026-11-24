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

  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp('Page.navigate',{url:address+'/'});
  const basis=await until(()=>evaluate("document.getElementById('budget-basis')?.textContent?.startsWith('Lease price') && document.getElementById('budget-basis').textContent"));
  assert.match(basis,/\$1\.0867\/h/);
  assert.match(basis,/Waiting for a recent fresh-core rate/);
  const forecast=await evaluate("({ heading:document.getElementById('eta-heading').textContent, label:document.getElementById('eta-target-label').textContent, clock:document.getElementById('eta-clock').textContent, last:document.getElementById('eta-last-proof').textContent, stream:document.documentElement.dataset.stream })");
  assert.match(forecast.heading,/Hyperstack/);
  assert.match(forecast.label,new RegExp((live.core_replayed+live.core_new).toLocaleString('en-US')));
  assert.equal(forecast.clock,'Learning pace');
  assert.match(forecast.last,/Last server checkpoint/);
  assert.equal(forecast.stream,'live');
  const held=await evaluate(`(() => {
    document.getElementById('overview-budget').click();
    const cache=document.getElementById('budget-cache');
    cache.value='published';
    const credit=document.getElementById('budget-credit');
    credit.value='7';
    credit.dispatchEvent(new Event('input',{bubbles:true}));
    document.getElementById('cloud-budget').scrollIntoView({block:'center',behavior:'instant'});
    return {published:cache.selectedOptions[0].textContent,
      result:document.getElementById('budget-result').textContent,
      runway:document.getElementById('budget-runway').textContent};
  })()`);
  assert.match(held.published,/3,646 cores/);
  assert.match(held.result,/Core cost and ETA are on hold/);
  assert.match(held.runway,/6\.44 A100 hours/);
  assert.doesNotMatch(held.runway,/new cores/);
  await sleep(300);
  const capture=await cdp('Page.captureScreenshot',{format:'png'});
  await fs.writeFile('outputs/Ark-A100-budget-pause.png',Buffer.from(capture.data,'base64'));
  console.log(JSON.stringify({basis,...held,forecast}));
  await Promise.race([cdp('Browser.close'),sleep(1000)]);
} finally {
  socket?.close();
  if (chrome.exitCode === null) chrome.kill();
}
