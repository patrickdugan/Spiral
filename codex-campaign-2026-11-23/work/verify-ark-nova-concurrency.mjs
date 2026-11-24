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

  const worker = spawn('wsl.exe', [
    '-u','root','--','systemd-run','--unit=shz-mnr04-desktop-key-check-20261124',
    '--wait','--pipe','--collect','-p','CPUQuota=100%','-p','MemoryMax=2G','-p','MemorySwapMax=4G',
    '-p','RuntimeMaxSec=100','--setenv=RAYON_NUM_THREADS=1','--setenv=CUDA_VISIBLE_DEVICES=',
    '/usr/bin/nice','-n','12','/var/tmp/shz-mnr04-target/release/shz',
    'mnr04-route-key-hash','/var/tmp/shz-mnr04-routes.DRDHJbsC/replay/core-archive.json',
  ],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  let workerOutput='', workerError='';
  worker.stdout.setEncoding('utf8').on('data',chunk=>{workerOutput+=chunk;});
  worker.stderr.setEncoding('utf8').on('data',chunk=>{workerError+=chunk;});
  const workerResult=new Promise(resolve=>{
    worker.on('error',error=>resolve({code:1,error}));
    worker.on('close',code=>resolve({code}));
  });

  const read = () => evaluate(`(() => {
    const rows=[...document.querySelectorAll('#ongoing-jobs article')];
    const row=rows.find(el=>el.querySelector('h3')?.textContent==='MNR-04 clearing proof');
    const ark=rows.find(el=>el.querySelector('h3')?.textContent==='Ark SP1 prover');
    if(!row||!ark)return null;
    const metric=label=>[...row.querySelectorAll('dt')].find(el=>el.textContent===label)?.nextElementSibling;
    const cpu=metric('CPU seconds');
    return {summary:document.querySelector('#ongoing-summary').textContent,
      phase:row.querySelector('.ongoing-work p')?.textContent,
      ark:ark.querySelector('.status-pill')?.textContent,
      cpu:Number(cpu?.textContent), ram:Number(metric('Process RAM MiB')?.textContent),
      stepped:cpu?.classList.contains('worker-increment')===true,
      animation:cpu?getComputedStyle(cpu).animationName:null};
  })()`);
  const visible = await until(async()=>{
    const data=await read();
    return data?.stepped&&data.animation==='checkpoint-arrive'?data:null;
  },25000);
  assert.equal(visible.summary,'2 running');
  assert.equal(visible.ark,'Running');
  assert.equal(visible.phase,'Deriving the routed Nova verification key');
  assert.ok(visible.cpu>0 && visible.ram>0);
  await evaluate("document.querySelector('#ongoing-jobs').scrollIntoView({block:'center',behavior:'instant'})");
  const capture = await cdp('Page.captureScreenshot',{format:'png'});
  await fs.writeFile('outputs/Ark-and-Nova-live-workers.png',Buffer.from(capture.data,'base64'));
  await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  const reduced=await until(async()=>{
    const data=await read();
    return data?.stepped&&data?.cpu>visible.cpu?data:null;
  },12000);
  assert.equal(reduced.animation,'none');
  const result=await workerResult;
  assert.equal(result.code,0,workerError);
  assert.equal(JSON.parse(workerOutput).vk_sha256,'e92e08dafafd66304914f136910fba8942ad8b16faadf9973c85c064962e606d');
  await until(()=>evaluate("document.querySelector('#ongoing-summary').textContent==='1 running'"));
  console.log(JSON.stringify({visible,reduced,afterExit:'1 running',realVerificationKeyMatched:true}));
  await Promise.race([cdp('Browser.close'),sleep(1000)]);
} finally {
  socket?.close();
  if (chrome.exitCode === null) chrome.kill();
}
