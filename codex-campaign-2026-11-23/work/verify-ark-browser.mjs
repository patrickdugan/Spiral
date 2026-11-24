import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as sleep} from 'node:timers/promises';

const profile = await fs.mkdtemp(path.resolve('work/ark-browser-'));
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

  const endpointArgument = process.argv[2];
  assert.match(endpointArgument, /^http:\/\/127\.0\.0\.1:[0-9]+$/);
  await cdp('Emulation.setDeviceMetricsOverride', {width:1440,height:1180,deviceScaleFactor:1,mobile:false});
  await cdp('Emulation.setEmulatedMedia', {features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
  await cdp('Page.navigate', {url:endpointArgument + '/'});
  await until(() => evaluate("document.getElementById('ongoing-jobs')?.textContent.includes('Hyperstack · A100 GPU') && document.querySelector('.mosaic-next') !== null"));
  const read = () => evaluate("(async () => { const ark=(await fetch('/api/live',{cache:'no-store'}).then(r=>r.json())).cloud_hyperstack_ark; const next=document.querySelector('.mosaic-next'); return {ark,animation:next?getComputedStyle(next).animationName:null,caption:document.getElementById('mosaic-caption').textContent,replayed:document.querySelectorAll('#mosaic-tiles .mosaic-cell.replay').length,fresh:document.querySelectorAll('#mosaic-tiles .mosaic-cell:not(.replay):not(.mosaic-next)').length,overview:document.getElementById('ongoing-jobs').textContent.replace(/\\s+/g,' ').trim()}; })()");
  const first = await read();
  const second = await until(async () => {
    const next = await read();
    return next.ark.sampled_at_unix>first.ark.sampled_at_unix &&
      (next.ark.core_new>first.ark.core_new || next.ark.recursion_new>first.ark.recursion_new) &&
      (next.replayed>0 || (next.ark.core_replayed>0 && next.overview.includes('Replayed core shards'))) &&
      next.fresh>0 ? next : null;
  }, 42000);
  assert.equal(second.ark.vm_id, 1178271);
  assert.equal(second.ark.ark_running, true);
  assert.equal(second.animation, 'mosaic-awaiting');
  assert.match(second.overview, /Ark SP1 prover/);
  assert.match(second.overview, /Running/);
  assert.match(second.caption, /grouped by heartbeat/);
  const hardware = await evaluate("document.getElementById('hardware-ribbon').textContent");
  assert.match(hardware, /A100 spot VM/);
  const capture = await cdp('Page.captureScreenshot', {format:'png'});
  await fs.writeFile(path.resolve('outputs/Ark-A100-live-console.png'), Buffer.from(capture.data,'base64'));
  await cdp('Emulation.setEmulatedMedia', {features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  const reduced = await until(async () => {
    const sample = await read();
    return sample.animation === 'none' ? sample : null;
  });
  console.log(JSON.stringify({before:{core:first.ark.core_new,recursion:first.ark.recursion_new},
    after:{core:second.ark.core_new,recursion:second.ark.recursion_new},
    replayedTiles:second.replayed,freshTiles:second.fresh,overview:second.overview,
    liveAnimation:second.animation,reducedMotionAnimation:reduced.animation,spotLabelVerified:true}));
  await Promise.race([cdp('Browser.close'), sleep(1000)]);
} finally {
  socket?.close();
  if (chrome.exitCode === null) chrome.kill();
}
